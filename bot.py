import telebot
from telebot import types
from vk_messages import VkMessage, VkPolling
import vk
import threading
import re
from credentials import token, vk_app_id

vk_threads = {}

vk_tokens = {}

bot = telebot.AsyncTeleBot(token)

link = 'https://oauth.vk.com/authorize?client_id={}&' \
       'display=page&redirect_uri=https://oauth.vk.com/blank.html&scope=friends,messages' \
       '&response_type=token&v=5.65'.format(vk_app_id)

mark = types.InlineKeyboardMarkup()
yes = types.InlineKeyboardButton('ВХОД', url=link)
mark.add(yes)


def create_thread(message, vk_token):
    a = VkPolling()
    t = threading.Thread(name='vk' + str(message.from_user.id), target=a.run, args=(vk_token, bot, message.chat.id,))
    t.setDaemon(True)
    t.start()
    vk_threads[str(message.from_user.id)] = a
    vk_tokens[str(message.from_user.id)] = vk_token


def check_thread(message):
    for th in threading.enumerate():
        if th.getName() == 'vk' + str(message.from_user.id):
            return False
    return True


def stop_thread(message):
    for th in threading.enumerate():
        if th.getName() == 'vk' + str(message.from_user.id):
            t = vk_threads[str(message.from_user.id)]
            t.terminate()
            th.join()


def extract_unique_code(text):
    # Extracts the unique_code from the sent /start command.
    try:
        text = text[45:]
        text = text.split('&')
        return text[0]
    except:
        return None


def verifycode(code):
    session = vk.Session(access_token=code)
    api = vk.API(session)
    return dict(api.account.getProfileInfo(fields=[]))


def info_extractor(info):
    info = info[0].url[8:-3].split('.')
    return info


@bot.message_handler(commands=['stop'])
def stop_command(message):
    if not check_thread(message):
        stop_thread(message)
        bot.send_message(message.chat.id, 'Успешный выход!').wait()
    else:
        bot.send_message(message.chat.id, 'Вход не был выполнен!').wait()


@bot.message_handler(commands=['start'])
def start_command(message):
    if check_thread(message):
        bot.send_message(message.chat.id,
                         'Привет, этот бот поможет тебе общаться ВКонтакте, войди по кнопке ниже'
                         ' и отправь мне то, что получишь в адресной строке.',
                         reply_markup=mark).wait()
    else:
        bot.send_message(message.chat.id, 'Вход уже выполнен!\n/stop для выхода.').wait()


@bot.message_handler(content_types=['text'])
def reply(message):
    m = re.search('https://oauth\.vk\.com/blank\.html#access_token=[a-z0-9]*&expires_in=[0-9]*&user_id=[0-9]*',
                  message.text)
    if m:
        code = extract_unique_code(m.group(0))
        if check_thread(message):
            try:
                verifycode(code)
                create_thread(message, VkMessage(code))
                bot.send_message(message.chat.id, 'Вход выполнен!').wait()
                bot.send_message(message.chat.id, 'Бот позволяет получать и отвечать на текстовые сообщения'
                                                  ' из ВКонтакте\nПример личного сообщения:').wait()
                bot.send_message(message.chat.id, '*Иван Петров:*\nПривет, я тут классный мессенджер нашёл,'
                                                  ' попробуешь? telegram.org/download', parse_mode='Markdown').wait()
                bot.send_message(message.chat.id, 'Для сообщений из групповых чатов будет указываться'
                                                  ' чат после имени отправителя:').wait()
                rp = bot.send_message(message.chat.id, '*Ник Невидов @ My English is perfect:*\n'
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
        info = info_extractor(message.reply_to_message.entities)
        if info is not None:
            if len(info) - 1:
                vk.API(vk_tokens[str(message.from_user.id)].session).messages.send(chat_id=info[1],
                                                                                   message=message.text)
            else:
                vk.API(vk_tokens[str(message.from_user.id)].session).messages.send(user_id=info[0],
                                                                                   message=message.text)


bot.polling(none_stop=True)
