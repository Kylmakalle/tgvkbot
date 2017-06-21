import vk
import time
import requests
import wget


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


def handle_messages(m, vk_user, bot, chat_id):
    user = vk.API(vk_user.session).users.get(user_ids=m["uid"], fields=[])[0]
    if 'body' in m and not 'attachment' in m:
        data = add_reply_info(m, user["first_name"], user["last_name"]) + '{}'.format(m["body"].replace('<br>', '\n'))
        bot.send_message(chat_id, data, parse_mode='HTML',
                         disable_notification=check_notification(m)).wait()
    if 'attachment' in m:
        attachment_handler(m, user, bot, chat_id)


def handle_updates(vk_user, bot, chat_id, updates):
    for m in updates:
        if not m['out']:
            handle_messages(m, vk_user, bot, chat_id)


def attachment_handler(m, user, bot, chat_id):
    if m['attachment']['type'] == 'photo':
        for photo in m['attachments']:
            data = add_reply_info(m, user['first_name'], user['last_name']) + '<a href="{}">Фото</a>'.format(
                get_max_src(photo['photo']))
            bot.send_message(chat_id, data, parse_mode='HTML',
                             disable_notification=check_notification(m)).wait()
    if m['attachment']['type'] == 'video':
        for vid in m['attachments']:
            link = 'https://vk.com/video{}_{}'.format(vid['video']['owner_id'],
                                                      vid['video']['vid'])
            data = add_reply_info(m, user['first_name'], user['last_name']) + '<a href="{}">Видео</a>'.format(link)
            bot.send_message(chat_id, data, parse_mode='HTML',
                             disable_notification=check_notification(m)).wait()
    if m['attachment']['type'] == 'audio':
        for audio in m['attachments']:
            data = add_reply_info(m, user['first_name'], user['last_name']) + '🎵 <code>{} - {}</code>'.format(
                audio['audio']['artist'],
                audio['audio']['title'])
            bot.send_message(chat_id, data, parse_mode='HTML',
                             disable_notification=check_notification(m)).wait()
    if m['attachment']['type'] == 'doc':
        for doc in m['attachments']:
            if doc['doc']['ext'] == 'gif':
                link = doc['doc']['url']
                data = add_reply_info(m, user["first_name"], user["last_name"]) + '<a href="{}">GIF</a>'.format(link)
                bot.send_message(chat_id, data, parse_mode='HTML',
                                 disable_notification=check_notification(m)).wait()

            if doc['doc']['ext'] == 'pdf' or doc['doc']['ext'] == 'zip':
                link = doc['doc']['url']
                data = add_reply_info(m, user["first_name"], user["last_name"], ) + '<a href="{}">Документ</a>'.format(
                    link)
                bot.send_message(chat_id, data, parse_mode='HTML',
                                 disable_notification=check_notification(m)).wait()

            if doc['doc']['ext'] == 'jpg' or doc['doc']['ext'] == 'png':
                link = doc['doc']['url']
                data = add_reply_info(m, user["first_name"], user["last_name"], ) + '<i>Документ</i>'
                bot.send_message(chat_id, data, parse_mode='HTML',
                                 disable_notification=check_notification(m)).wait()
                uploading = bot.send_chat_action(chat_id, 'upload_document')
                bot.send_document(chat_id, link).wait()
                uploading.wait()

            if doc['doc']['ext'] == 'doc' or doc['doc']['ext'] == 'docx' or doc['doc']['ext'] == 'rar' or \
                            doc['doc']['ext'] == 'ogg':
                data = add_reply_info(m, user["first_name"], user["last_name"], ) + '<i>Документ</i>'
                bot.send_message(chat_id, data, parse_mode='HTML',
                                 disable_notification=check_notification(m)).wait()
                uploading = bot.send_chat_action(chat_id, 'upload_document')
                bot.send_document(chat_id, wget.download(requests.get(doc['doc']['url']).url)).wait()
                uploading.wait()

            else:
                link = doc['doc']['url']
                data = add_reply_info(m, user["first_name"], user["last_name"]) + \
                       '<i>Документ</i>\n<a href="{}">{}</a>'.format(link, doc['doc']['title'])
                bot.send_message(chat_id, data, parse_mode='HTML',
                                 disable_notification=check_notification(m)).wait()

    if m['attachment']['type'] == 'sticker':
        link = m['attachment']['sticker']['photo_512']
        data = add_reply_info(m, user["first_name"], user["last_name"], ) + '<a href="{}">Стикер</a>'.format(link)
        bot.send_message(chat_id, data, parse_mode='HTML',
                         disable_notification=check_notification(m)).wait()
        # TODO: Wall Posts and comments


def add_reply_info(m, first_name, last_name):
    if 'body' in m:
        if 'chat_id' in m:
            # TODO: Handle forwared messages
            return '<a href="x{}.{}">&#8203;</a><b>{} {} @ {}:</b>\n{}\n'.format(m['uid'], m['chat_id'], first_name,
                                                          last_name, m['title'], m['body'].replace('<br>', '\n'))
        else:
            return '<a href="x{}.0">&#8203;</a><b>{} {}:</b>\n{}\n'.format(m['uid'], first_name, last_name,
                                                                           m['body'].replace('<br>', '\n'))
    else:
        if 'chat_id' in m:
            return '<a href="x{}.{}">&#8203;</a><b>{} {} @ {}:</b>\n'.format(m['uid'], m['chat_id'], first_name,
                                                                             last_name, m['title'])
        else:
            return '<a href="x{}.0">&#8203;</a><b>{} {}:</b>\n'.format(m['uid'], first_name, last_name)


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
