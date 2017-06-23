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
from PIL import Image
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
       'display=page&redirect_uri=https://oauth.vk.com/blank.html&scope=friends,messages,offline,docs,photos,video' \
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


def audio_title_creator(message, performer=None, title=None):
    if not performer and not title:
        return 'Аудио_{}'.format(str(message.date)[5:])
    else:
        return '{} - {}'.format(performer, title)


def send_text(message, userid, group):
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session
    if group:
        vk.API(session).messages.send(chat_id=userid, message=message.text)
    else:
        vk.API(session).messages.send(user_id=userid, message=message.text)


def send_doc(message, userid, group):
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

    if filetype == 'voice':
        openedfile = open(file, 'rb')
        files = {'file': openedfile}
        fileonserver = ujson.loads(requests.post(vk.API(session).docs.getUploadServer()['upload_url'],
                                                 files=files).text)
        attachment = vk.API(session).docs.save(file=fileonserver['file'], title='Аудиосообщение',
                                               tags='')
        openedfile.close()
        os.remove(file)

    if filetype == 'audio':
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
                                                                       attachment[0]['did']))
        else:
            vk.API(session).messages.send(chat_id=userid,
                                          attachment='doc{}_{}'.format(attachment[0]['owner_id'],
                                                                       attachment[0]['did']))
    else:
        if message.caption:
            vk.API(session).messages.send(user_id=userid, message=message.caption,
                                          attachment='doc{}_{}'.format(attachment[0]['owner_id'],
                                                                       attachment[0]['did']))
        else:
            vk.API(session).messages.send(user_id=userid,
                                          attachment='doc{}_{}'.format(attachment[0]['owner_id'],
                                                                       attachment[0]['did']))


def send_photo(message, userid, group):
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
            vk.API(session).messages.send(chat_id=userid, message=message.caption, attachment=attachment[0]['id'])
        else:
            vk.API(session).messages.send(chat_id=userid, attachment=attachment[0]['id'])
    else:
        if message.caption:
            vk.API(session).messages.send(user_id=userid, message=message.caption, attachment=attachment[0]['id'])
        else:
            vk.API(session).messages.send(user_id=userid, attachment=attachment[0]['id'])
    openedfile.close()
    os.remove(file)


def send_sticker(message, userid, group):
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
            vk.API(session).messages.send(chat_id=userid, message=message.caption, attachment=attachment[0]['id'])
        else:
            vk.API(session).messages.send(chat_id=userid, attachment=attachment[0]['id'])
    else:
        if message.caption:
            vk.API(session).messages.send(user_id=userid, message=message.caption, attachment=attachment[0]['id'])
        else:
            vk.API(session).messages.send(user_id=userid, attachment=attachment[0]['id'])
    openedfile.close()
    os.remove('{}.png'.format(file))
    os.remove(file)


def send_video(message, userid, group):
    filetype = message.content_type
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session

    file = wget.download(
        FILE_URL.format(token, bot.get_file(getattr(message, filetype).file_id).wait().file_path))
    openedfile = open(file, 'rb')
    files = {'video_file': openedfile}

    if group:
        attachment = vk.API(session).video.save(privacy_view='all')
        fileonserver = ujson.loads(requests.post(attachment['upload_url'],
                                                 files=files).text)
        video = 'video{}_{}'.format(attachment['owner_id'], attachment['owner_id']['video_id'])
        if message.caption:
            vk.API(session).messages.send(chat_id=userid, message=message.caption, attachment=video)
        else:
            vk.API(session).messages.send(chat_id=userid, attachment=video)
    else:
        try:
            attachment = vk.API(session).video.save(privacy_view=userid)
        except:
            attachment = vk.API(session).video.save(privacy_view='all')
        fileonserver = ujson.loads(requests.post(attachment['upload_url'],
                                                 files=files).text)
        video = 'video{}_{}'.format(attachment['owner_id'], attachment['vid'])
        if message.caption:
            vk.API(session).messages.send(user_id=userid, message=message.caption, attachment=video)
        else:
            vk.API(session).messages.send(user_id=userid, attachment=video)
    openedfile.close()
    os.remove(file)


def send_contact(message, userid, group):
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session
    if message.contact.last_name:
        text = 'Контакт: {} {}'.format(message.contact.first_name, message.contact.last_name)
    else:
        text = 'Контакт: {}'.format(message.contact.first_name)
    if group:
        vk.API(session).messages.send(chat_id=userid, message=text)
        vk.API(session).messages.send(chat_id=userid, message=message.contact)
    else:
        vk.API(session).messages.send(user_id=userid, message=text)
        vk.API(session).messages.send(chat_id=userid, message=message.contact)


@bot.message_handler(content_types=['document', 'voice', 'audio'])
def reply_document(message):
    if message.reply_to_message:
        try:
            vk_sender(message, send_doc)
        except Exception as e:
            bot.reply_to(message, 'Файл слишком большой, максимально допустимый размер *20мб*!',
                         parse_mode='Markdown').wait()
            print('Error: {}'.format(e))


@bot.message_handler(content_types=['sticker'])
def reply_sticker(message):
    if message.reply_to_message:
        try:
            vk_sender(message, send_sticker)
        except Exception as e:
            bot.reply_to(message, 'Произошла неизвестная ошибка при отправке',
                         parse_mode='Markdown').wait()
            print('Error: {}'.format(e))


@bot.message_handler(content_types=['photo'])
def reply_photo(message):
    if message.reply_to_message:
        try:
            vk_sender(message, send_photo)
        except Exception as e:
            bot.send_message(message.chat.id, 'Фото слишком большое, максимально допустимый размер *20мб*!',
                             parse_mode='Markdown').wait()
            print('Error: {}'.format(e))


@bot.message_handler(content_types=['video', 'video_note'])
def reply_video(message):
    if message.reply_to_message:
        try:
            vk_sender(message, send_video)
        except Exception as e:
            bot.reply_to(message, 'Файл слишком большой, максимально допустимый размер *20мб*!',
                         parse_mode='Markdown').wait()
            print('Error: {}'.format(e))


@bot.message_handler(content_types=['contact'])
def reply_contact(message):
    if message.reply_to_message:
        vk_sender(message, send_contact)


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
        try:
            vk_sender(message, send_text)
        except Exception as e:
            bot.reply_to(message, 'Произошла неизвестная ошибка при отправке',
                         parse_mode='Markdown').wait()
            print('Error: {}'.format(e))


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
