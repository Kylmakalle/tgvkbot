import logging
import os
import re
import redis
import requests
import telebot
import threading
import traceback
import ujson
import vk
import wget
from PIL import Image
from telebot import types

import cherrypy

from credentials import token, vk_app_id, local_port, bot_url
from vk_messages import VkMessage, VkPolling

logging.basicConfig(format='%(levelname)-8s [%(asctime)s] %(message)s', level=logging.WARNING, filename='vk.log')

vk_threads = {}

vk_dialogs = {}

FILE_URL = 'https://api.telegram.org/file/bot{0}/{1}'

tokens_pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
vk_tokens = redis.StrictRedis(connection_pool=tokens_pool)

currentchat = {}

bot = telebot.AsyncTeleBot(token)
# bot.remove_webhook()

link = 'https://oauth.vk.com/authorize?client_id={}&' \
       'display=page&redirect_uri=https://oauth.vk.com/blank.html&scope=friends,messages,offline,docs,photos,video' \
       '&response_type=token&v=5.65'.format(vk_app_id)
mark = types.InlineKeyboardMarkup()
yes = types.InlineKeyboardButton('ВХОД', url=link)
mark.add(yes)


def get_pages_switcher(markup, page, pages):
    if page != 0:
        leftbutton = types.InlineKeyboardButton('◀', callback_data='page{}'.format(page - 1))  # callback
    else:
        leftbutton = None
    if page + 1 < len(pages):
        rightbutton = types.InlineKeyboardButton('▶', callback_data='page{}'.format(page + 1))
    else:
        rightbutton = None

    if leftbutton and rightbutton:
        markup.row(leftbutton, rightbutton)
        return
    if leftbutton:
        markup.row(leftbutton)
    else:
        markup.row(rightbutton)


def replace_shields(text):
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&amp;', '&')
    text = text.replace('&copy;', '©')
    text = text.replace('&reg;', '®')
    text = text.replace('&laquo;', '«')
    text = text.replace('&raquo;', '«')
    text = text.replace('&deg;', '°')
    text = text.replace('&trade;', '™')
    text = text.replace('&plusmn;', '±')
    return text


def request_user_dialogs(session, userid):
    order = []
    users_ids = []
    dialogs = vk.API(session).messages.getDialogs(count=200)
    for chat in dialogs[1:]:
        if 'chat_id' in chat:
            if chat['title'].replace('\\', ''):
                chat['title'] = chat['title'].replace('\\', '')
            chat['title'] = replace_shields(chat['title'])
            order.append({'title': chat['title'], 'id': 'group' + str(chat['chat_id'])})
        elif chat['uid'] > 0:
            order.append({'title': None, 'id': chat['uid']})
            users_ids.append(chat['uid'])
    users = vk.API(session).users.get(user_ids=users_ids, fields=['first_name', 'last_name', 'uid'])
    for output in order:
        if output['title'] == ' ... ' or not output['title']:
            for x in users:
                if x['uid'] == output['id']:
                    current_user = x
                    break
            output['title'] = '{} {}'.format(current_user['first_name'], current_user['last_name'])
    for button in range(len(order)):
        order[button] = types.InlineKeyboardButton(order[button]['title'], callback_data=str(order[button]['id']))
    rows = [order[x:x + 2] for x in range(0, len(order), 2)]
    pages = [rows[x:x + 4] for x in range(0, len(rows), 4)]
    vk_dialogs[str(userid)] = pages


def create_markup(message, user, page, edit=False):
    markup = types.InlineKeyboardMarkup(row_width=2)
    for i in vk_dialogs[str(user)][page]:
        markup.row(*i)
    get_pages_switcher(markup, page, vk_dialogs[str(user)])
    if edit:
        bot.edit_message_text(
            '<b>Выберите Диалог:</b> <code>{}/{}</code> стр.'.format(page + 1, len(vk_dialogs[str(user)])),
            message.chat.id, message.message_id,
            parse_mode='HTML', reply_markup=markup).wait()
    else:
        bot.send_message(message.chat.id,
                         '<b>Выберите Диалог:</b> <code>{}/{}</code> стр.'.format(page + 1, len(vk_dialogs[str(user)])),
                         parse_mode='HTML', reply_markup=markup).wait()


@bot.callback_query_handler(func=lambda call: True)
def callback_buttons(call):
    if call.message:
        if 'page' in call.data:
            bot.answer_callback_query(call.id).wait()
            create_markup(call.message, call.from_user.id, int(call.data.split('page')[1]), True)
        elif 'group' in call.data:
            session = VkMessage(vk_tokens.get(str(call.from_user.id))).session
            chat = vk.API(session).messages.getChat(chat_id=call.data.split('group')[1], fields=[])
            bot.answer_callback_query(call.id,
                                      'Вы в беседе {}'.format(replace_shields(chat['title']))).wait()
            if chat['title'].replace('\\', ''):
                chat['title'] = chat['title'].replace('\\', '')
            bot.send_message(call.message.chat.id,
                             '<i>Вы в беседе {}</i>'.format(chat['title']),
                             parse_mode='HTML').wait()
            currentchat[str(call.from_user.id)] = call.data

        elif call.data.isdigit():
            session = VkMessage(vk_tokens.get(str(call.from_user.id))).session
            user = vk.API(session).users.get(user_ids=call.data, fields=[])[0]
            bot.answer_callback_query(call.id,
                                      'Вы в чате с {} {}'.format(user['first_name'], user['last_name'])).wait()
            bot.send_message(call.message.chat.id,
                             '<i>Вы в чате с {} {}</i>'.format(user['first_name'], user['last_name']),
                             parse_mode='HTML').wait()
            currentchat[str(call.from_user.id)] = call.data


def create_thread(uid, vk_token):
    a = VkPolling()
    t = threading.Thread(name='vk' + str(uid), target=a.run, args=(VkMessage(vk_token), bot, uid,))
    t.setDaemon(True)
    t.start()
    vk_threads[str(uid)] = a
    vk_tokens.set(str(uid), vk_token)


def check_thread(uid):
    for th in threading.enumerate():
        if th.getName() == 'vk' + str(uid):
            return False
    return True


# Creating VkPolling threads and dialogs info after bot reboot using existing tokens
for uid in vk_tokens.scan_iter():
    if check_thread(uid.decode("utf-8")):
        create_thread(uid.decode("utf-8"), vk_tokens.get(uid))
        request_user_dialogs(VkMessage(vk_tokens.get(uid.decode("utf-8"))).session, uid.decode("utf-8"))


def stop_thread(message):
    for th in threading.enumerate():
        if th.getName() == 'vk' + str(message.from_user.id):
            t = vk_threads[str(message.from_user.id)]
            t.terminate()
            th.join()
            vk_tokens.delete(str(message.from_user.id))


def extract_unique_code(text):
    # Extracts the unique_code from the sent /start command.
    try:
        return text[45:].split('&')[0]
    except:
        return None


def verifycode(code):
    session = vk.Session(access_token=code)
    api = vk.API(session)
    return dict(api.account.getProfileInfo(fields=[]))


def info_extractor(info):
    info = info[-1].url[8:-1].split('.')
    return info


@bot.message_handler(commands=['dialogs'])
def dialogs_command(message):
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session
    request_user_dialogs(session, message.from_user.id)
    create_markup(message, message.from_user.id, 0)


@bot.message_handler(commands=['stop'])
def stop_command(message):
    if not check_thread(message.from_user.id):
        stop_thread(message)
        bot.send_message(message.chat.id, 'Успешный выход!').wait()
    else:
        bot.send_message(message.chat.id, 'Вход не был выполнен!').wait()


@bot.message_handler(commands=['start'])
def start_command(message):
    if check_thread(message.from_user.id):
        bot.send_message(message.chat.id,
                         'Привет, этот бот поможет тебе общаться ВКонтакте, войди по кнопке ниже'
                         ' и отправь мне то, что получишь в адресной строке.',
                         reply_markup=mark).wait()
    else:
        bot.send_message(message.chat.id, 'Вход уже выполнен!\n/stop для выхода.').wait()


def form_request(message, method, info):
    if int(info[2]):
        if message.text and message.text.startswith('!'):
            if len(message.text) - 1:
                message.text = message.text[1:]
            if info[2] != 'None':
                method(message, info[1], group=True, forward_messages=info[2])
            else:
                method(message, info[1], group=True)
        elif message.caption and message.caption.startswith('!'):
            if len(message.caption) - 1:
                message.caption = message.caption[1:]
            if info[2] != 'None':
                method(message, info[1], group=True, forward_messages=info[2])
        else:
            method(message, info[1], group=True)
    else:
        if message.text and message.text.startswith('!'):
            if len(message.text) - 1:
                message.text = message.text[1:]
            if info[1] != 'None':
                method(message, info[0], group=False, forward_messages=info[1])
            else:
                method(message, info[0], group=False)
        elif message.caption and message.caption.startswith('!'):
            if len(message.caption) - 1:
                message.caption = message.caption[1:]
            if info[1] != 'None':
                method(message, info[0], group=False, forward_messages=info[1])
            else:
                method(message, info[0], group=False)
        else:
            method(message, info[0], group=False)


def logged(message):
    if vk_tokens.get(str(message.from_user.id)):
        return True
    else:
        bot.send_message(message.chat.id, 'Вход не выполнен! /start для входа').wait()
        return False


def vk_sender(message, method):
    if logged(message):
        if message.reply_to_message:
            info = info_extractor(message.reply_to_message.entities)
            if info is not None:
                form_request(message, method, info)

        elif str(message.from_user.id) in currentchat:
            info = []
            if 'group' in currentchat[str(message.from_user.id)]:
                info.append('0')
                info.append(currentchat[str(message.from_user.id)].split('group')[1])
                info.append('1')
            else:
                info.append(currentchat[str(message.from_user.id)])
                info.append('0')
                info.append('0')
            form_request(message, method, info)


def audio_title_creator(message, performer=None, title=None):
    if not performer and not title:
        return 'Аудио_{}'.format(str(message.date)[5:])
    else:
        return '{} - {}'.format(performer, title)


def send_text(message, userid, group, forward_messages=None):
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session
    if group:
        vk.API(session).messages.send(chat_id=userid, message=message.text, forward_messages=forward_messages)
    else:
        vk.API(session).messages.send(user_id=userid, message=message.text, forward_messages=forward_messages)


def send_doc(message, userid, group, forward_messages=None):
    filetype = message.content_type
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session
    file = wget.download(
        FILE_URL.format(token, bot.get_file(getattr(message, filetype).file_id).wait().file_path))
    if filetype == 'document':
        openedfile = open(file, 'rb')
        files = {'file': openedfile}
        fileonserver = ujson.loads(requests.post(vk.API(session).docs.getUploadServer()['upload_url'],
                                                 files=files).text)
        attachment = vk.API(session).docs.save(file=fileonserver['file'],
                                               title=getattr(message, filetype).file_name,
                                               tags='')
        openedfile.close()
        os.remove(file)

    elif filetype == 'voice':
        openedfile = open(file, 'rb')
        files = {'file': openedfile}
        fileonserver = ujson.loads(requests.post(vk.API(session).docs.getUploadServer()['upload_url'],
                                                 files=files).text)
        attachment = vk.API(session).docs.save(file=fileonserver['file'], title='Аудиосообщение',
                                               tags='')
        openedfile.close()
        os.remove(file)

    else:  # filetype == 'audio':
        newfile = file.split('.')[0] + '.aac'
        os.rename(file, newfile)
        openedfile = open(newfile, 'rb')
        files = {'file': openedfile}
        fileonserver = ujson.loads(requests.post(vk.API(session).docs.getUploadServer()['upload_url'],
                                                 files=files).text)
        attachment = vk.API(session).docs.save(file=fileonserver['file'],
                                               title=audio_title_creator(message, message.audio.performer,
                                                                         message.audio.title), tags='')
        openedfile.close()
        os.remove(newfile)

    if group:
        if message.caption:

            vk.API(session).messages.send(chat_id=userid, message=message.caption,
                                          attachment='doc{}_{}'.format(attachment[0]['owner_id'],
                                                                       attachment[0]['did']),
                                          forward_messages=forward_messages)
        else:
            vk.API(session).messages.send(chat_id=userid,
                                          attachment='doc{}_{}'.format(attachment[0]['owner_id'],
                                                                       attachment[0]['did']),
                                          forward_messages=forward_messages)
    else:
        if message.caption:
            vk.API(session).messages.send(user_id=userid, message=message.caption,
                                          attachment='doc{}_{}'.format(attachment[0]['owner_id'],
                                                                       attachment[0]['did']),
                                          forward_messages=forward_messages)
        else:
            vk.API(session).messages.send(user_id=userid,
                                          attachment='doc{}_{}'.format(attachment[0]['owner_id'],
                                                                       attachment[0]['did']),
                                          forward_messages=forward_messages)


def send_photo(message, userid, group, forward_messages=None):
    filetype = message.content_type
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session
    file = wget.download(
        FILE_URL.format(token, bot.get_file(getattr(message, filetype)[-1].file_id).wait().file_path))
    openedfile = open(file, 'rb')
    files = {'file': openedfile}
    fileonserver = ujson.loads(requests.post(vk.API(session).photos.getMessagesUploadServer()['upload_url'],
                                             files=files).text)
    attachment = vk.API(session).photos.saveMessagesPhoto(server=fileonserver['server'], photo=fileonserver['photo'],
                                                          hash=fileonserver['hash'])
    if group:
        if message.caption:
            vk.API(session).messages.send(chat_id=userid, message=message.caption, attachment=attachment[0]['id'],
                                          forward_messages=forward_messages)
        else:
            vk.API(session).messages.send(chat_id=userid, attachment=attachment[0]['id'],
                                          forward_messages=forward_messages)
    else:
        if message.caption:
            vk.API(session).messages.send(user_id=userid, message=message.caption, attachment=attachment[0]['id'],
                                          forward_messages=forward_messages)
        else:
            vk.API(session).messages.send(user_id=userid, attachment=attachment[0]['id'],
                                          forward_messages=forward_messages)
    openedfile.close()
    os.remove(file)


def send_sticker(message, userid, group, forward_messages=None):
    filetype = message.content_type
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session
    file = wget.download(
        FILE_URL.format(token, bot.get_file(getattr(message, filetype).file_id).wait().file_path))
    Image.open(file).save("{}.png".format(file))
    openedfile = open('{}.png'.format(file), 'rb')
    files = {'file': openedfile}
    fileonserver = ujson.loads(requests.post(vk.API(session).photos.getMessagesUploadServer()['upload_url'],
                                             files=files).text)
    attachment = vk.API(session).photos.saveMessagesPhoto(server=fileonserver['server'], photo=fileonserver['photo'],
                                                          hash=fileonserver['hash'])
    if group:
        if message.caption:
            vk.API(session).messages.send(chat_id=userid, message=message.caption, attachment=attachment[0]['id'],
                                          forward_messages=forward_messages)
        else:
            vk.API(session).messages.send(chat_id=userid, attachment=attachment[0]['id'],
                                          forward_messages=forward_messages)
    else:
        if message.caption:
            vk.API(session).messages.send(user_id=userid, message=message.caption, attachment=attachment[0]['id'],
                                          forward_messages=forward_messages)
        else:
            vk.API(session).messages.send(user_id=userid, attachment=attachment[0]['id'],
                                          forward_messages=forward_messages)
    openedfile.close()
    os.remove('{}.png'.format(file))
    os.remove(file)


def send_video(message, userid, group, forward_messages=None):
    filetype = message.content_type
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session

    file = wget.download(
        FILE_URL.format(token, bot.get_file(getattr(message, filetype).file_id).wait().file_path))
    openedfile = open(file, 'rb')
    files = {'video_file': openedfile}

    if group:
        attachment = vk.API(session).video.save(is_private=1)
        fileonserver = ujson.loads(requests.post(attachment['upload_url'],
                                                 files=files).text)
        video = 'video{}_{}'.format(attachment['owner_id'], attachment['owner_id']['video_id'])
        if message.caption:
            vk.API(session).messages.send(chat_id=userid, message=message.caption, attachment=video,
                                          forward_messages=forward_messages)
        else:
            vk.API(session).messages.send(chat_id=userid, attachment=video, forward_messages=forward_messages)
    else:
        attachment = vk.API(session).video.save(is_private=1)
        fileonserver = ujson.loads(requests.post(attachment['upload_url'],
                                                 files=files).text)
        video = 'video{}_{}'.format(attachment['owner_id'], attachment['vid'])
        if message.caption:
            vk.API(session).messages.send(user_id=userid, message=message.caption, attachment=video,
                                          forward_messages=forward_messages)
        else:
            vk.API(session).messages.send(user_id=userid, attachment=video, forward_messages=forward_messages)
    openedfile.close()
    os.remove(file)


def send_contact(message, userid, group, forward_messages=None):
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session
    if message.contact.last_name:
        text = 'Контакт: {} {}'.format(message.contact.first_name, message.contact.last_name)
    else:
        text = 'Контакт: {}'.format(message.contact.first_name)
    if group:
        vk.API(session).messages.send(chat_id=userid, message=text, forward_messages=forward_messages)
        vk.API(session).messages.send(chat_id=userid, message=message.contact, forward_messages=forward_messages)
    else:
        vk.API(session).messages.send(user_id=userid, message=text, forward_messages=forward_messages)
        vk.API(session).messages.send(chat_id=userid, message=message.contact, forward_messages=forward_messages)


@bot.message_handler(content_types=['document', 'voice', 'audio'])
def reply_document(message):
    try:
        vk_sender(message, send_doc)
    except:
        bot.reply_to(message, 'Файл слишком большой, максимально допустимый размер *20мб*!',
                     parse_mode='Markdown').wait()


@bot.message_handler(content_types=['sticker'])
def reply_sticker(message):
    try:
        vk_sender(message, send_sticker)
    except Exception:
        bot.reply_to(message, '*Произошла неизвестная ошибка при отправке*',
                     parse_mode='Markdown').wait()  # TODO?: Bugreport system
        print('Error: {}'.format(traceback.format_exc()))


@bot.message_handler(content_types=['photo'])
def reply_photo(message):
    try:
        vk_sender(message, send_photo)
    except:
        bot.send_message(message.chat.id, 'Фото слишком большое, максимально допустимый размер *20мб*!',
                         parse_mode='Markdown').wait()


@bot.message_handler(content_types=['video', 'video_note'])
def reply_video(message):
    try:
        vk_sender(message, send_video)
    except:
        bot.reply_to(message, 'Файл слишком большой, максимально допустимый размер *20мб*!',
                     parse_mode='Markdown').wait()


@bot.message_handler(content_types=['contact'])
def reply_contact(message):
    try:
        vk_sender(message, send_contact)
    except Exception:
        bot.reply_to(message, '*Произошла неизвестная ошибка при отправке*',
                     parse_mode='Markdown').wait()
        print('Error: {}'.format(traceback.format_exc()))


@bot.message_handler(content_types=['text'])
def reply_text(message):
    m = re.search('https://oauth\.vk\.com/blank\.html#access_token=[a-z0-9]*&expires_in=[0-9]*&user_id=[0-9]*',
                  message.text)
    if m:
        code = extract_unique_code(m.group(0))
        if check_thread(message.from_user.id):
            try:
                verifycode(code)
                create_thread(message.from_user.id, code)
                bot.send_message(message.chat.id, 'Вход выполнен!').wait()
                # ---------------- INSTRUCTIONS ---------------- #
                bot.send_message(message.chat.id, 'Бот позволяет получать и отвечать на текстовые сообщения'
                                                  ' из ВКонтакте\nПример личного сообщения:').wait()
                bot.send_message(message.chat.id, '*Иван Петров:*\nПривет, я тут классный мессенджер нашёл,'
                                                  ' попробуешь? telegram.org/download', parse_mode='Markdown').wait()
                bot.send_message(message.chat.id, 'Для сообщений из групповых чатов будет указываться'
                                                  ' чат после имени отправителя:').wait()
                bot.send_message(message.chat.id, '*Ник Невидов @ My English is perfect:*\n'
                                                  'London is the capital of Great Britain',
                                 parse_mode='Markdown').wait()
                bot.send_message(message.chat.id, 'Чтобы ответить, используй Reply на нужное сообщение.'
                                                  ' (нет, на эти не сработает, нужно реальное)',
                                 parse_mode='Markdown').wait()
                # ---------------- INSTRUCTIONS ---------------- #
            except:
                bot.send_message(message.chat.id, 'Неверная ссылка, попробуй ещё раз!').wait()
        else:
            bot.send_message(message.chat.id, 'Вход уже выполнен!\n/stop для выхода.').wait()
            return

    try:
        vk_sender(message, send_text)
    except Exception:
        bot.reply_to(message, 'Произошла неизвестная ошибка при отправке',
                     parse_mode='Markdown').wait()
        print('Error: {}'.format(traceback.format_exc()))


# bot.polling(none_stop=True)
class WebhookServer(object):
    # index равнозначно /, т.к. отсутствию части после ip-адреса (грубо говоря)
    @cherrypy.expose
    def index(self):
        length = int(cherrypy.request.headers['content-length'])
        json_string = cherrypy.request.body.read(length).decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''


if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook('https://{}/{}/'.format(bot_url, token))
    cherrypy.config.update(
        {'server.socket_host': '127.0.0.1', 'server.socket_port': local_port, 'engine.autoreload.on': False})
    cherrypy.quickstart(WebhookServer(), '/', {'/': {}})
