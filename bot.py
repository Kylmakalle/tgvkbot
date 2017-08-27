import logging
import os
import re
import requests
import telebot
import threading
import time
import traceback
import ujson
from telebot import types

import redis
import vk
import wget
from PIL import Image
from credentials import token, vk_app_id
from vk_messages import VkMessage, VkPolling

vk_threads = {}

vk_dialogs = {}

FILE_URL = 'https://api.telegram.org/file/bot{0}/{1}'

vk_tokens = redis.from_url(os.environ.get("REDIS_URL"))

currentchat = {}

bot = telebot.AsyncTeleBot(token)
bot.remove_webhook()

link = 'https://oauth.vk.com/authorize?client_id={}&' \
       'display=page&redirect_uri=https://oauth.vk.com/blank.html&scope=friends,messages,offline,docs,photos,video' \
       '&response_type=token&v=5.65'.format(vk_app_id)


def get_pages_switcher(markup, page, pages):
    if page != 0:
        leftbutton = types.InlineKeyboardButton('◀', callback_data='page{}'.format(page - 1))  # callback
    else:
        leftbutton = types.InlineKeyboardButton('Поиск 🔍', callback_data='search')
    if page + 1 < len(pages):
        rightbutton = types.InlineKeyboardButton('▶', callback_data='page{}'.format(page + 1))
    else:
        rightbutton = None

    if rightbutton:
        markup.row(leftbutton, rightbutton)
    else:
        markup.row(leftbutton)


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
    group_ids = []
    positive_group_ids = []
    dialogs = vk.API(session).messages.getDialogs(count=200)
    for chat in dialogs[1:]:
        if 'chat_id' in chat:
            chat['title'] = replace_shields(chat['title'])
            order.append({'title': chat['title'], 'id': 'group' + str(chat['chat_id'])})
        elif chat['uid'] > 0:
            order.append({'title': None, 'id': chat['uid']})
            users_ids.append(chat['uid'])
        elif chat['uid'] < 0:
            order.append({'title': None, 'id': chat['uid']})
            group_ids.append(chat['uid'])

    for g in group_ids:
        positive_group_ids.append(str(g)[1:])

    if users_ids:
        users = vk.API(session).users.get(user_ids=users_ids, fields=['first_name', 'last_name', 'uid'])
    else:
        users = []

    if positive_group_ids:
        groups = vk.API(session).groups.getById(group_ids=positive_group_ids, fields=[])
    else:
        groups = []

    for output in order:
        if output['title'] == ' ... ' or not output['title']:
            if output['id'] > 0:
                for x in users:
                    if x['uid'] == output['id']:
                        output['title'] = '{} {}'.format(x['first_name'], x['last_name'])
                        break

            else:
                for f in groups:
                    if str(f['gid']) == str(output['id'])[1:]:
                        output['title'] = '{}'.format(f['name'])
                        break
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
        bot.send_message(message.from_user.id,
                         '<b>Выберите Диалог:</b> <code>{}/{}</code> стр.'.format(page + 1, len(vk_dialogs[str(user)])),
                         parse_mode='HTML', reply_markup=markup).wait()


def search_users(message, text):
    session = VkMessage(vk_tokens.get(str(message.from_user.id))).session
    markup = types.InlineKeyboardMarkup(row_width=1)
    result = vk.API(session).messages.searchDialogs(q=text, limit=10, fields=[])
    for chat in result:
        if chat['type'] == 'profile':
            markup.add(types.InlineKeyboardButton('{} {}'.format(chat['first_name'], chat['last_name']),
                                                  callback_data=str(chat['uid'])))
        elif chat['type'] == 'chat':
            markup.add(
                types.InlineKeyboardButton(replace_shields(chat['title']),
                                           callback_data='group' + str(chat['chat_id'])))
    if markup.keyboard:
        markup.add(types.InlineKeyboardButton('Поиск 🔍', callback_data='search'))
        bot.send_message(message.from_user.id, '<b>Результат поиска по</b> <i>{}</i>'.format(text),
                         reply_markup=markup, parse_mode='HTML')
    else:
        markup.add(types.InlineKeyboardButton('Поиск 🔍', callback_data='search'))
        bot.send_message(message.from_user.id, '<b>Ничего не найдено по запросу</b> <i>{}</i>'.format(text),
                         parse_mode='HTML', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: True)
def callback_buttons(call):
    if call.message:
        if 'page' in call.data:
            try:
                create_markup(call.message, call.from_user.id, int(call.data.split('page')[1]), True)
            except:
                session = VkMessage(vk_tokens.get(str(call.from_user.id))).session
                request_user_dialogs(session, call.from_user.id)
                create_markup(call.message, call.from_user.id, int(call.data.split('page')[1]), True)
            bot.answer_callback_query(call.id).wait()
        elif 'search' in call.data:
            markup = types.ForceReply(selective=False)
            bot.answer_callback_query(call.id, 'Поиск беседы 🔍').wait()
            bot.send_message(call.from_user.id, '<b>Поиск беседы</b> 🔍',
                             parse_mode='HTML', reply_markup=markup).wait()
        elif 'group' in call.data:
            session = VkMessage(vk_tokens.get(str(call.from_user.id))).session
            chat = vk.API(session).messages.getChat(chat_id=call.data.split('group')[1], fields=[])
            bot.answer_callback_query(call.id,
                                      'Вы в беседе {}'.format(replace_shields(chat['title']))).wait()
            bot.send_message(call.from_user.id,
                             '<i>Вы в беседе {}</i>'.format(chat['title']),
                             parse_mode='HTML').wait()
            currentchat[str(call.from_user.id)] = call.data
        elif call.data.lstrip('-').isdigit():
            session = VkMessage(vk_tokens.get(str(call.from_user.id))).session
            if '-' in call.data:
                user = vk.API(session).groups.getById(group_id=call.data.lstrip('-'), fields=[])[0]
                user = {'first_name': user['name'], 'last_name': ''}
            else:
                user = vk.API(session).users.get(user_ids=call.data, fields=[])[0]
            bot.answer_callback_query(call.id,
                                      'Вы в чате с {} {}'.format(user['first_name'], user['last_name'])).wait()
            bot.send_message(call.from_user.id,
                             '<i>Вы в чате с {} {}</i>'.format(user['first_name'], user['last_name']),
                             parse_mode='HTML').wait()
            currentchat[str(call.from_user.id)] = {'title': user['first_name'] + ' ' + user['last_name'],
                                                   'id': call.data}


def create_thread(uid, vk_token):
    a = VkPolling()
    longpoller = VkMessage(vk_token)
    t = threading.Thread(name='vk' + str(uid), target=a.run, args=(longpoller, bot, uid,))
    t.setDaemon(True)
    t.start()
    vk_threads[str(uid)] = a
    vk_tokens.set(str(uid), vk_token)
    vk.API(longpoller.session).account.setOffline()


def check_thread(uid):
    for th in threading.enumerate():
        if th.getName() == 'vk' + str(uid):
            return False
    return True


# Creating VkPolling threads and dialogs info after bot's reboot/exception using existing tokens
def thread_reviver(uid):
    tries = 0
    while check_thread(uid.decode("utf-8")):
        if tries < 4:
            try:
                create_thread(uid.decode("utf-8"), vk_tokens.get(uid))
            except:
                time.sleep(10)
                tries = tries + 1
        else:
            mark = types.InlineKeyboardMarkup()
            login = types.InlineKeyboardButton('ВХОД', url=link)
            mark.add(login)
            bot.send_message(uid.decode("utf-8"), '<b>Непредвиденная ошибка, требуется повторный логин ВК!</b>',
                             parse_mode='HTML', reply_markup=mark).wait()
            break


def thread_supervisor():
    while True:
        for uid in vk_tokens.scan_iter():
            reviver_thread = threading.Thread(name='reviver' + str(uid.decode('utf-8')), target=thread_reviver,
                                              args=(uid,))
            reviver_thread.setDaemon(True)
            reviver_thread.start()
        time.sleep(60)


supervisor = threading.Thread(name='supervisor', target=thread_supervisor)
supervisor.setDaemon(True)
supervisor.start()


def stop_thread(message):
    for th in threading.enumerate():
        if th.getName() == 'vk' + str(message.from_user.id):
            t = vk_threads[str(message.from_user.id)]
            t.terminate()
            th.join()
            vk_tokens.delete(str(message.from_user.id))
            vk_dialogs.pop(str(message.from_user.id), None)
            currentchat.pop(str(message.from_user.id), None)


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


@bot.message_handler(commands=['chat'])
def chat_command(message):
    if logged(message):
        if str(message.from_user.id) in currentchat:
            if 'group' in currentchat[str(message.from_user.id)]['id']:
                chat = currentchat[str(message.from_user.id)]
                bot.send_message(message.from_user.id,
                                 '<i>Вы в беседе {}</i>'.format(chat['title']),
                                 parse_mode='HTML').wait()
            else:
                chat = currentchat[str(message.from_user.id)]
                bot.send_message(message.from_user.id,
                                 '<i>Вы в чате с {}</i>'.format(chat['title']),
                                 parse_mode='HTML').wait()
        else:
            bot.send_message(message.from_user.id,
                             '<i>Вы не находитесь в чате</i>',
                             parse_mode='HTML').wait()


@bot.message_handler(commands=['leave'])
def leave_command(message):
    if logged(message):
        if str(message.from_user.id) in currentchat:
            currentchat.pop(str(message.from_user.id), None)
            bot.send_message(message.from_user.id,
                             '<i>Вы вышли из чата</i>',
                             parse_mode='HTML').wait()
        else:
            bot.send_message(message.from_user.id,
                             '<i>Вы не находитесь в чате</i>',
                             parse_mode='HTML').wait()


@bot.message_handler(commands=['dialogs'])
def dialogs_command(message):
    if logged(message):
        session = VkMessage(vk_tokens.get(str(message.from_user.id))).session
        request_user_dialogs(session, message.from_user.id)
        create_markup(message, message.from_user.id, 0)


@bot.message_handler(commands=['search'])
def search_command(message):
    if logged(message):
        markup = types.ForceReply(selective=False)
        if telebot.util.extract_arguments(message.text):
            search_users(message, telebot.util.extract_arguments(message.text))
        else:
            bot.send_message(message.from_user.id, '<b>Поиск беседы</b> 🔍',
                             parse_mode='HTML', reply_markup=markup).wait()


@bot.message_handler(commands=['stop'])
def stop_command(message):
    if not check_thread(message.from_user.id):
        stop_thread(message)
        bot.send_message(message.from_user.id, 'Успешный выход!').wait()
    else:
        bot.send_message(message.from_user.id, 'Вход не был выполнен!').wait()


@bot.message_handler(commands=['start'])
def start_command(message):
    if check_thread(message.from_user.id):
        mark = types.InlineKeyboardMarkup()
        login = types.InlineKeyboardButton('ВХОД', url=link)
        mark.add(login)
        bot.send_message(message.from_user.id,
                         'Привет, этот бот поможет тебе общаться ВКонтакте, войди по кнопке ниже'
                         ' и отправь мне то, что получишь в адресной строке.',
                         reply_markup=mark).wait()
    else:
        bot.send_message(message.from_user.id, 'Вход уже выполнен!\n/stop для выхода.').wait()


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
        bot.send_message(message.from_user.id, 'Вход не выполнен! /start для входа').wait()
        return False


def vk_sender(message, method):
    if logged(message):
        if message.reply_to_message:
            info = info_extractor(message.reply_to_message.entities)
            if info is not None:
                form_request(message, method, info)

        elif str(message.from_user.id) in currentchat:
            info = []
            if 'group' in currentchat[str(message.from_user.id)]['id']:
                info.append('0')
                info.append(currentchat[str(message.from_user.id)]['id'].split('group')[1])
                info.append('1')
            else:
                info.append(currentchat[str(message.from_user.id)]['id'])
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
    if filetype == 'document' and 'video' not in message.document.mime_type:
        file = wget.download(
            FILE_URL.format(token, bot.get_file(getattr(message, filetype).file_id).wait().file_path))
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
        file = wget.download(
            FILE_URL.format(token, bot.get_file(getattr(message, filetype).file_id).wait().file_path))
        openedfile = open(file, 'rb')
        files = {'file': openedfile}
        fileonserver = ujson.loads(
            requests.post(vk.API(session).docs.getUploadServer(type='audio_message')['upload_url'],
                          files=files).text)
        attachment = vk.API(session).docs.save(file=fileonserver['file'], title='Аудиосообщение',
                                               tags='')
        openedfile.close()
        os.remove(file)

    elif filetype == 'document' and 'video' in message.document.mime_type:
        vk_sender(message, send_video)
        return

    else:  # filetype == 'audio':
        file = wget.download(
            FILE_URL.format(token, bot.get_file(getattr(message, filetype).file_id).wait().file_path))
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
        bot.send_message(message.from_user.id, 'Фото слишком большое, максимально допустимый размер *20мб*!',
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
                user = verifycode(code)
                create_thread(message.from_user.id, code)
                bot.send_message(message.from_user.id,
                                 'Вход выполнен в аккаунт {} {}!'.format(user['first_name'], user['last_name'])).wait()

                bot.send_message(message.from_user.id, '[Использование](https://asergey.me/tgvkbot/usage/)',
                                 parse_mode='Markdown').wait()
            except:
                bot.send_message(message.from_user.id, 'Неверная ссылка, попробуй ещё раз!').wait()
        else:
            bot.send_message(message.from_user.id, 'Вход уже выполнен!\n/stop для выхода.').wait()

    elif message.reply_to_message and message.reply_to_message.text == 'Поиск беседы 🔍':
        search_users(message, message.text)

    else:
        try:
            vk_sender(message, send_text)
        except Exception:
            bot.reply_to(message, 'Произошла неизвестная ошибка при отправке',
                         parse_mode='Markdown').wait()


bot.polling(none_stop=True)
"""class WebhookServer(object):
    # index равнозначно /, т.к. отсутствию части после ip-адреса (грубо говоря)
    @cherrypy.expose
    def index(self):
        length = int(cherrypy.request.headers['content-length'])
        json_string = cherrypy.request.body.read(length).decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''


if __name__ == '__main__':
    logging.basicConfig(format='%(levelname)-8s [%(asctime)s] %(message)s', level=logging.WARNING, filename='vk.log')
    bot.remove_webhook()
    bot.set_webhook('https://{}/{}/'.format(bot_url, token))
    cherrypy.config.update(
        {'server.socket_host': '127.0.0.1', 'server.socket_port': local_port, 'engine.autoreload.on': False,
         'log.screen': False})
    cherrypy.quickstart(WebhookServer(), '/', {'/': {}})"""
