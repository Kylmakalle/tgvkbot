import telebot
from telebot import types
from vk_messages import VkMessage, VkPolling
import vk
import threading
import re
import logging
import requests
import ujson
import wget
import os
import cherrypy
import redis

from credentials import token, vk_app_id, local_port

logging.basicConfig(format='%(levelname)-8s [%(asctime)s] %(message)s', level=logging.WARNING, filename='vk.log')

vk_threads = {}

FILE_URL = 'https://api.telegram.org/file/bot{0}/{1}'

tokens_pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
vk_tokens = redis.StrictRedis(connection_pool=tokens_pool)

bot = telebot.AsyncTeleBot(token)
bot.remove_webhook()

link = 'https://oauth.vk.com/authorize?client_id={}&' \
       'display=page&redirect_uri=https://oauth.vk.com/blank.html&scope=friends,messages,offline,docs' \
       '&response_type=token&v=5.65'.format(vk_app_id)
mark = types.InlineKeyboardMarkup()
yes = types.InlineKeyboardButton('ВХОД', url=link)
mark.add(yes)


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


# Creating VkPolling threads after bot reboot using existing tokens
for uid in vk_tokens.scan_iter():
    if check_thread(uid.decode("utf-8")):
        create_thread(uid.decode("utf-8"), vk_tokens.get(uid))


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
    info = info[0].url[8:-1].split('.')
    return info


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


def vk_sender(message, method):
    if message.reply_to_message:
        if vk_tokens.get(str(message.from_user.id)):
            info = info_extractor(message.reply_to_message.entities)
            if info is not None:
                if int(info[1]):
                    method(message, info[1], group=True)
                else:
                    method(message, info[0], group=False)
        else:
            bot.send_message(message.chat.id, 'Вход не выполнен! /start для входа').wait()


def send_doc(message, userid, group):
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session
    file = wget.download(
        FILE_URL.format(token, bot.get_file(message.document.file_id).wait().file_path))
    openedfile = open(file, 'rb')
    files = {'file': openedfile}
    fileonserver = ujson.loads(requests.post(vk.API(session).docs.getUploadServer()['upload_url'],
                                             files=files).text)
    attachment = vk.API(session).docs.save(file=fileonserver['file'], title=message.document.file_name,
                                           tags='')
    if group:
        vk.API(session).messages.send(chat_id=userid,
                                      attachment='doc{}_{}'.format(attachment[0]['owner_id'],
                                                                   attachment[0]['did']))
    else:
        vk.API(session).messages.send(user_id=userid,
                                      attachment='doc{}_{}'.format(attachment[0]['owner_id'],
                                                                   attachment[0]['did']))
    openedfile.close()
    os.remove(file)


@bot.message_handler(content_types=['document'])
def reply_document(message):
    vk_sender(message, send_doc)
    """if message.reply_to_message:
        if vk_tokens.get(str(message.from_user.id)):
            info = info_extractor(message.reply_to_message.entities)
            if info is not None:
                if int(info[1]):
                    send_doc(message, info[1], True)
                else:
                    send_doc(message, info[0], False)
        else:
            bot.send_message(message.chat.id, 'Вход не выполнен! /start для входа').wait()"""


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
            except:
                bot.send_message(message.chat.id, 'Неверная ссылка, попробуй ещё раз!').wait()
        else:
            bot.send_message(message.chat.id, 'Вход уже выполнен!\n/stop для выхода.').wait()
        return

    if message.reply_to_message:
        if vk_tokens.get(str(message.from_user.id)):
            info = info_extractor(message.reply_to_message.entities)
            if info is not None:
                if int(info[1]):
                    vk.API(VkMessage(vk_tokens.get(str(message.from_user.id))).session).messages.send(
                        chat_id=info[1],
                        message=message.text)
                else:
                    vk.API(VkMessage(vk_tokens.get(str(message.from_user.id))).session).messages.send(
                        user_id=info[0],
                        message=message.text)
        else:
            bot.send_message(message.chat.id, 'Вход не выполнен! /start для входа').wait()


# bot.polling()
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
    bot.set_webhook('https://bot.asergey.me/{}/'.format(token))
    cherrypy.config.update(
        {'server.socket_host': '127.0.0.1', 'server.socket_port': local_port, 'engine.autoreload.on': False})
    cherrypy.quickstart(WebhookServer(), '/', {'/': {}})
