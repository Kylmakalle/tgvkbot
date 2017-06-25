import vk
import time
import requests
import wget
import os
import ujson
import redis

tokens_pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
vk_tokens = redis.StrictRedis(connection_pool=tokens_pool)


class VkPolling:
    def __init__(self):
        self._running = True

    def terminate(self):
        self._running = False

    def run(self, vk_user, bot, chat_id):
        while self._running:
            updates = []
            try:
                updates = vk_user.get_new_messages()
            except Exception as e:
                print('Error: {}'.format(e))
            if updates:
                handle_updates(vk_user, bot, chat_id, updates)
            for i in range(45):
                if self._running:
                    time.sleep(0.1)
                else:
                    break


def handle_messages(m, vk_user, bot, chat_id, mainmessage=None):
    user = vk.API(vk_user.session).users.get(user_ids=m["uid"], fields=[])[0]
    if 'body' in m and not 'attachment' in m and not 'geo' in m and not 'fwd_messages' in m:
        data = add_user_info(m, user["first_name"], user["last_name"])[:-1] + add_reply_info(m)
        bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                         disable_notification=check_notification(m), reply_to_message_id=mainmessage).wait()
    if 'attachment' in m:
        attachment_handler(m, user, bot, chat_id, mainmessage)
    if 'geo' in m:
        data = add_user_info(m, user["first_name"], user["last_name"]) + '<i>Местоположение</i>' + add_reply_info(m)
        geo = bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                               disable_notification=check_notification(m), reply_to_message_id=mainmessage).wait()
        if 'place' in m['geo']:
            bot.send_venue(chat_id, m['geo']['coordinates'].split(' ')[0], m['geo']['coordinates'].split(' ')[1],
                           m['geo']['place']['title'], m['geo']['place']['city'],
                           disable_notification=check_notification(m),
                           reply_to_message_id=geo.message_id).wait()
        else:
            bot.send_location(chat_id, m['geo']['coordinates'].split(' ')[0], m['geo']['coordinates'].split(' ')[1],
                              disable_notification=check_notification(m),
                              reply_to_message_id=geo.message_id).wait()
    if 'fwd_messages' in m:
        data = add_user_info(m, user["first_name"],
                             user["last_name"]) + '<i>Пересланные сообщения</i>' + add_reply_info(m)
        reply = bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                                 disable_notification=check_notification(m),
                                 reply_to_message_id=mainmessage).wait().message_id
        for forwared in m['fwd_messages']:
            handle_messages(forwared, vk_user, bot, chat_id, reply)


def handle_updates(vk_user, bot, chat_id, updates):
    for m in updates:
        if not m['out']:
            handle_messages(m, vk_user, bot, chat_id)


def attachment_handler(m, user, bot, chat_id, mainmessage=None):
    for attach in m['attachments']:
        if attach['type'] == 'photo':
            try:
                data = add_user_info(m, user['first_name'], user['last_name']) + '<a href="{}">Фото</a>'.format(
                    get_max_src(attach['photo'])) + add_reply_info(m)
                bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                                 disable_notification=check_notification(m), reply_to_message_id=mainmessage).wait()
            except:
                send_doc_link(attach, m, user, bot, chat_id, mainmessage)

        elif attach['type'] == 'video':
            try:
                link = 'https://vk.com/video{}_{}'.format(attach['video']['owner_id'],
                                                          attach['video']['vid'])
                data = add_user_info(m, user['first_name'], user['last_name']) + '<a href="{}">Видео</a>'.format(
                    link) + add_reply_info(m)
                bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                                 disable_notification=check_notification(m), reply_to_message_id=mainmessage).wait()
            except:
                send_doc_link(attach, m, user, bot, chat_id, mainmessage)

        elif attach['type'] == 'audio':
            data = add_user_info(m, user['first_name'], user[
                'last_name']) + '🎵 <a href="https://m.vk.com/audio?q={}%20-%20{}">{} - {}</a>'.format(
                attach['audio']['artist'].replace(' ', '%20'),
                attach['audio']['title'].replace(' ', '%20'), attach['audio']['artist'],
                attach['audio']['title']) + add_reply_info(m)
            bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                             disable_notification=check_notification(m), reply_to_message_id=mainmessage).wait()

        elif attach['type'] == 'doc':
            if attach['doc']['ext'] == 'gif':
                try:
                    link = attach['doc']['url']
                    data = add_user_info(m, user["first_name"], user["last_name"]) + '<a href="{}">GIF</a>'.format(
                        link) + add_reply_info(m)
                    bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                                     disable_notification=check_notification(m),
                                     reply_to_message_id=mainmessage).wait()
                except:
                    send_doc_link(attach, m, user, bot, chat_id, mainmessage)

            elif attach['doc']['ext'] == 'pdf' or attach['doc']['ext'] == 'zip':
                try:
                    link = attach['doc']['url']
                    data = add_user_info(m, user["first_name"],
                                         user["last_name"]) + '<a href="{}">Документ</a>'.format(
                        link) + add_reply_info(m)
                    bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                                     disable_notification=check_notification(m),
                                     reply_to_message_id=mainmessage).wait()
                except:
                    send_doc_link(attach, m, user, bot, chat_id, mainmessage)

            elif attach['doc']['ext'] == 'jpg' or attach['doc']['ext'] == 'png':
                try:
                    link = attach['doc']['url']
                    data = add_user_info(m, user["first_name"],
                                         user["last_name"], ) + '<i>Документ</i>' + add_reply_info(m)
                    notification = bot.send_message(chat_id, data, parse_mode='HTML',
                                                    disable_notification=check_notification(m),
                                                    reply_to_message_id=mainmessage).wait()
                    uploading = bot.send_chat_action(chat_id, 'upload_document')
                    bot.send_document(chat_id, link, reply_to_message_id=notification.message_id,
                                      disable_notification=check_notification(m)).wait()
                    uploading.wait()
                except:
                    send_doc_link(attach, m, user, bot, chat_id, mainmessage)

            elif attach['doc']['ext'] == 'ogg':
                try:
                    link = attach['doc']['url']
                    data = add_user_info(m, user["first_name"], user["last_name"], ) + \
                           '<a href="{}">Аудио</a>'.format(link) + add_reply_info(m)
                    bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                                     disable_notification=check_notification(m),
                                     reply_to_message_id=mainmessage).wait()
                except:
                    send_doc_link(attach, m, user, bot, chat_id, mainmessage)

            elif attach['doc']['ext'] == 'doc' or attach['doc']['ext'] == 'docx':
                try:
                    data = add_user_info(m, user["first_name"],
                                         user["last_name"], ) + '<i>Документ</i>' + add_reply_info(m)
                    notification = bot.send_message(chat_id, data, parse_mode='HTML',
                                                    disable_notification=check_notification(m),
                                                    reply_to_message_id=mainmessage).wait()
                    uploading = bot.send_chat_action(chat_id, 'upload_document')
                    file = wget.download(requests.get(attach['doc']['url']).url)
                    openedfile = open(file, 'rb')
                    bot.send_document(chat_id, openedfile,
                                      reply_to_message_id=notification.message_id,
                                      disable_notification=check_notification(m)).wait()
                    uploading.wait()
                    openedfile.close()
                    os.remove(file)
                except:
                    send_doc_link(attach, m, user, bot, chat_id, mainmessage)
            else:
                send_doc_link(attach, m, user, bot, chat_id, mainmessage)

        elif attach['type'] == 'sticker':
            link = attach['sticker']['photo_512']
            data = add_user_info(m, user["first_name"], user["last_name"]) + '<a href="{}">Стикер</a>'.format(
                link) + add_reply_info(m)
            bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                             disable_notification=check_notification(m), reply_to_message_id=mainmessage).wait()
        elif attach['type'] == 'wall':
            link = 'https://vk.com/wall{}_{}'.format(attach['wall']['from_id'], attach['wall']['id'])
            data = add_user_info(m, user["first_name"], user["last_name"]) + '<a href="{}">Запись на стене</a>'.format(
                link) + add_reply_info(m)
            bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                             disable_notification=check_notification(m), reply_to_message_id=mainmessage).wait()
        elif attach['type'] == 'wall_reply':
            data = add_user_info(m, user["first_name"],
                                 user["last_name"]) + '<i>Комментарий на стене</i>' + add_reply_info(m)
            comment = bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                                       disable_notification=check_notification(m),
                                       reply_to_message_id=mainmessage).wait()
            try:
                user = vk.API(get_session(vk_tokens.get(str(chat_id)))).users.get(user_ids=attach['wall_reply']["uid"],
                                                                                  fields=[])[0]
                if attach['wall_reply']['text']:
                    data = add_user_info(m, user["first_name"], user["last_name"]) + \
                           attach['wall_reply']['text'].replace('<br>', '\n') + add_reply_info(m)
                    bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                                     disable_notification=check_notification(m),
                                     reply_to_message_id=comment.message_id).wait()
                if 'attachments' in attach['wall_reply']:
                    attachment_handler(attach['wall_reply'], user, bot, chat_id, mainmessage=comment.message_id)
            except:
                link = 'https://vk.com/wall{}_{}'.format(attach['wall']['owner_id'], attach['wall']['cid'])
                data = add_user_info(m, user["first_name"],
                                     user["last_name"]) + '<a href="{}">Комментарий</a>'.format(
                    link) + add_reply_info(m)
                bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                                 disable_notification=check_notification(m),
                                 reply_to_message_id=comment.message_id).wait()


def check_expansion(document):
    if len(document['doc']['title'].split('.')) - 1:
        return document['doc']['title']
    else:
        return document['doc']['title'] + '.' + document['doc']['ext']


def send_doc_link(doc, m, user, bot, chat_id, mainmessage=None):
    link = doc['doc']['url']
    data = add_user_info(m, user["first_name"], user["last_name"]) + \
           '<i>Документ</i>\n<a href="{}">{}</a>'.format(link, check_expansion(doc)) + add_reply_info(m)
    bot.send_message(chat_id, data, parse_mode='HTML', disable_web_page_preview=False,
                     disable_notification=check_notification(m), reply_to_message_id=mainmessage).wait()


def check_forward_id(msg):
    if 'mid' in msg:
        return msg['mid']
    else:
        return None


def add_reply_info(m):
    if 'chat_id' in m:
        return '<a href="x{}.{}.{}">&#8203;</a>'.format(m['uid'], m['chat_id'], check_forward_id(m))
    else:
        return '<a href="x{}.{}.0">&#8203;</a>'.format(m['uid'], check_forward_id(m))


def add_user_info(m, first_name, last_name):
    if 'body' in m and m['body']:
        if 'chat_id' in m:
            return '<b>{} {} @ {}:</b>\n{}\n'.format(first_name, last_name, m['title'], m['body'].replace('<br>', '\n'))
        else:
            return '<b>{} {}:</b>\n{}\n'.format(first_name, last_name, m['body'].replace('<br>', '\n'))
    else:
        if 'chat_id' in m:
            return '<b>{} {} @ {}:</b>\n'.format(first_name, last_name, m['title'])
        else:
            return '<b>{} {}:</b>\n'.format(first_name, last_name)


def check_notification(value):
    if 'push_settings' in value:
        return True
    else:
        return False


def get_max_src(attachment):
    if 'src_xxbig' in attachment:
        return attachment['src_xxbig']
    if 'src_xbig' in attachment:
        return attachment['src_xbig']
    if 'src_big' in attachment:
        return attachment['src_big']
    if 'src' in attachment:
        return attachment['src']


class VkMessage:
    def __init__(self, token):
        self.session = get_session(token)
        self.ts, self.pts = get_tses(self.session)

    def get_new_messages(self):

        api = vk.API(self.session)
        new = api.messages.getLongPollHistory(ts=self.ts, pts=self.pts)
        msgs = new['messages']
        self.pts = new["new_pts"]
        count = msgs[0]

        res = []
        if count == 0:
            pass
        else:
            messages = msgs[1:]
            for m in messages:
                res.append(m)
        return res


def get_session(token):
    return vk.Session(access_token=token)


def get_tses(session):
    api = vk.API(session)

    ts = api.messages.getLongPollServer(need_pts=1)
    return ts['ts'], ts['pts']
