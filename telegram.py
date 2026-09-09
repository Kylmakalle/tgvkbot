from aiogram import types
from aiogram.bot.api import FILE_URL
from aiogram.utils import executor, json
from aiohttp.client_exceptions import ContentTypeError

from bot import *
from config import *
from vk_messages import vk_polling_tasks, vk_polling
from vk_oauth import parse_oauth_token

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

async def get_pages_switcher(markup, page, pages):
    if page != 0:
        leftbutton = InlineKeyboardButton('◀', callback_data='page{}'.format(page - 1))  # callback
    else:
        leftbutton = InlineKeyboardButton('Поиск 🔍', callback_data='search')
    if page + 1 < len(pages):
        rightbutton = InlineKeyboardButton('▶', callback_data='page{}'.format(page + 1))
    else:
        rightbutton = None

    if rightbutton:
        markup.row(leftbutton, rightbutton)
    else:
        markup.row(leftbutton)


async def logged(uid, reply_to_message_id=None, to_chat=None):
    vk_user = VkUser.objects.filter(owner__uid=uid).first()
    if vk_user:
        return True
    else:
        await bot.send_message(to_chat or uid, 'Вход не выполнен! /start для входа',
                               reply_to_message_id=reply_to_message_id)
        return False


async def update_user_info(from_user: types.User):
    return TgUser.objects.update_or_create(uid=from_user.id,
                                           defaults={'first_name': from_user.first_name,
                                                     'last_name': from_user.last_name,
                                                     'username': from_user.username
                                                     })


async def update_chat_info(from_chat: types.Chat):
    if from_chat.type == 'private':
        return None, False
    return TgChat.objects.update_or_create(cid=from_chat.id)


async def is_forwarding(text):
    if not text:
        return False, None
    if text == '!':
        return True, None
    if text.startswith('!'):
        return True, text[1:]
    return False, text


async def is_bot_in_iterator(msg: types.Message):
    iterator = msg.new_chat_members or [msg.left_chat_member] or []
    me = await bot.me
    for i in iterator:
        if me.id == i.id:
            return True
    return False


import secrets


def generate_random_id():
    return secrets.randbelow(2_147_483_647)


async def vk_sender(token, tg_message, **kwargs):
    session = VkSession(access_token=token, driver=await get_driver(token))
    kwargs['random_id'] = generate_random_id()
    try:
        api = API(session)
        vk_msg_id = await api('messages.send', **kwargs)
    except ContentTypeError:
        kwargs['v'] = session.API_VERSION
        kwargs['access_token'] = session.access_token
        try:
            url, html = await session.driver.post_text(url=session.REQUEST_URL + 'messages.send', data=kwargs)
            response = json.loads(html)
            vk_msg_id = response['response']
        except:
            log.exception(msg='Error in vk sender', exc_info=True)
            return None
    except VkAuthError:
        vk_user = VkUser.objects.filter(token=token).first()
        if vk_user:
            vk_user.delete()
        await bot.send_message(tg_message.chat.id, 'Вход не выполнен! /start для входа',
                               reply_to_message_id=tg_message.message_id)
        return
    except VkAPIError:
        await asyncio.sleep(5)
        if kwargs.get('retries', 0) > 4:
            log.exception(msg='Error in vk sender', exc_info=True)
            return None
        else:
            kwargs['retries'] = kwargs.get('retries', 0) + 1
            await vk_sender(token, tg_message, **kwargs)
    except Exception:
        log.exception(msg='Error in vk sender', exc_info=True)
        return None
    Message.objects.create(
        vk_chat=kwargs['peer_id'],
        vk_id=vk_msg_id,
        tg_chat=tg_message.chat.id,
        tg_id=tg_message.message_id
    )
    return vk_msg_id


async def generate_send_options(msg, forward=None, forward_messages_exists=False, message=None):
    message_options = dict()
    if forward:
        if msg.reply_to_message is not None:
            message_in_db = Message.objects.filter(tg_chat=msg.chat.id,
                                                   tg_id=msg.reply_to_message.message_id).first()
            if message_in_db and message_in_db.vk_id:
                message_options['forward_messages'] = message_in_db.vk_id
        message_options['peer_id'] = forward.vkchat.cid

    elif msg.reply_to_message is not None:
        message_in_db = Message.objects.filter(tg_chat=msg.chat.id, tg_id=msg.reply_to_message.message_id).first()
        if not message_in_db:
            await msg.reply('Не знаю в какой чат ответить, нет информации в базе данных.')
            return message_options
        if forward_messages_exists and message_in_db.vk_id:
            message_options['forward_messages'] = message_in_db.vk_id
        message_options['peer_id'] = message_in_db.vk_chat
    else:
        await msg.reply('Не понимаю что делать. Нужна помощь? Используй команду /help')
        return message_options

    if message:
        message_options['message'] = message
    return message_options


async def send_vk_action(token, peer_id, action='typing'):
    vksession = VkSession(access_token=token, driver=await get_driver(token))
    api = API(vksession)
    return  # await api('messages.setActivity', peer_id=peer_id, activity=action)


async def upload_attachment(msg, vk_user, file_id, peer_id, attachment_type, upload_field, upload_method,
                            on_server_field='file', save_method='', upload_type=None, default_name='tgvkbot.document',
                            title='tgvkbot.document', rewrite_name=False, custom_ext=''):
    try:
        file_info = await bot.get_file(file_id)
        path = file_info['file_path']
        if msg.content_type == 'audio':
            if not custom_ext and '.' in path and path.split('.')[-1] == 'mp3':
                custom_ext = '.aac'
    except NetworkError:
        await msg.reply('Файл слишком большой, максимально допустимый размер <b>20мб!</b>', parse_mode=ParseMode.HTML)
        return

    url = FILE_URL.format(token=bot._BaseBot__token, path=path)
    await send_vk_action(vk_user.token, peer_id)
    content = await get_content(url, default_name, chrome_headers=False, rewrite_name=rewrite_name,
                                custom_ext=custom_ext)
    filename = (content.get('file_name', '') + content.get('custom_ext', '')) or None
    if 'content' in content:
        vksession = VkSession(access_token=vk_user.token, driver=await get_driver(vk_user.token))
        api = API(vksession)
        upload_options = {}
        if attachment_type != 'photo' and upload_type:
            upload_options['type'] = upload_type
        if msg.content_type == 'sticker':
            webp = Image.open(content['content']).convert('RGBA')
            png = io.BytesIO()
            webp.save(png, format='png')
            content['content'] = png.getvalue()
        if attachment_type == 'video':
            upload_options['is_private'] = 1
        upload_server = await api(upload_method, **upload_options)
        with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            field_data = {}
            if filename:
                field_data['filename'] = filename
            data.add_field(upload_field, content['content'], content_type='multipart/form-data', **field_data)
            async with session.post(upload_server['upload_url'], data=data) as upload:
                file_on_server = json.loads(await upload.text())
        if msg.content_type != 'sticker':
            content['content'].close()
            try:
                os.remove(os.path.join(content['temp_path'], content['file_name'] + content['custom_ext']))
            except:
                pass
        if attachment_type == 'photo':
            save_options = {'server': file_on_server['server'], on_server_field: file_on_server[on_server_field],
                            'hash': file_on_server['hash']}
        elif attachment_type == 'video':
            return f'{attachment_type}{upload_server["owner_id"]}_{upload_server["video_id"]}_{upload_server["access_key"]}'
        else:
            if 'file' not in file_on_server:
                await msg.reply('<b>Ошибка</b> Не удалось загрузить файл. Файл не должен быть исполняемым.',
                                parse_mode=ParseMode.HTML)
                return
            save_options = dict({'file': file_on_server['file']})
            save_options['title'] = title
        attachment = await api(save_method, **save_options)
        if 'type' not in attachment:
            attachment = attachment[0]
        else:
            attachment = attachment[attachment['type']]
        return f'{attachment_type}{attachment["owner_id"]}_{attachment["id"]}'


async def get_dialogs(token, exclude=None):
    if not exclude:
        exclude = []
    session = VkSession(access_token=token, driver=await get_driver(token))
    api = API(session)
    dialogs = await api('messages.getDialogs', count=200)
    order = []
    users_ids = []
    group_ids = []
    for chat in dialogs.get('items'):
        chat = chat.get('message', '')
        if chat:
            if 'chat_id' in chat:
                if 2000000000 + chat['chat_id'] not in exclude:
                    chat['title'] = chat['title']
                    order.append({'title': chat['title'], 'id': 2000000000 + chat['chat_id']})
            elif chat['user_id'] > 0:
                if chat['user_id'] not in exclude:
                    order.append({'title': 'Диалог ' + str(chat['user_id']), 'id': chat['user_id']})
                    users_ids.append(chat['user_id'])
            elif chat['user_id'] < 0:
                if chat['user_id'] not in exclude:
                    order.append({'title': 'Диалог ' + str(chat['user_id']), 'id': chat['user_id']})
                    group_ids.append(chat['user_id'])

    if users_ids:
        users = await api('users.get', user_ids=', '.join(str(x) for x in users_ids))
    else:
        users = []

    if group_ids:
        groups = await api('groups.getById', group_ids=', '.join(str(abs(x)) for x in group_ids))
    else:
        groups = []

    for output in order:
        if output['id'] > 0:
            u = next((i for i in users if i['id'] == output['id']), None)
            if u:
                output['title'] = f'{u["first_name"]} {u["last_name"]}'
        else:
            g = next((i for i in groups if -i['id'] == output['id']), None)
            if g:
                output['title'] = g["name"]

    for button in range(len(order)):
        order[button] = InlineKeyboardButton(order[button]['title'], callback_data=f'chat{order[button]["id"]}')

    rows = [order[x:x + 2] for x in range(0, len(order), 2)]
    pages = [rows[x:x + 4] for x in range(0, len(rows), 4)]

    return pages


async def search_dialogs(msg: types.Message, user=None):
    if not user:
        user, created = await update_user_info(msg.from_user)
    vkuser = VkUser.objects.filter(owner=user).first()
    vksession = VkSession(access_token=vkuser.token, driver=await get_driver(vkuser.token))
    api = API(vksession)
    markup = InlineKeyboardMarkup(row_width=1)
    await bot.send_chat_action(msg.chat.id, 'typing')
    result = await api('messages.searchDialogs', q=msg.text, limit=10)
    for chat in result:
        title = None
        data = None
        if chat['type'] == 'profile':
            title = f'{chat["first_name"]} {chat["last_name"]}'
            data = f'chat{chat["id"]}'
        elif chat['type'] == 'chat':
            title = chat['title']
            data = f'chat{2000000000 + chat["id"]}'
        elif chat['type'] == 'page':
            title = await chat['name']
            data = f'chat{-chat["id"]}'
        if title and data:
            markup.add(InlineKeyboardButton(text=title, callback_data=data))
    markup.add(InlineKeyboardButton('Поиск 🔍', callback_data='search'))
    if markup.inline_keyboard:
        text = f'<b>Результат поиска по</b> <i>{msg.text}</i>'
    else:
        text = f'<b>Результат поиска по</b> <i>{msg.text}</i>'
    await bot.send_message(msg.chat.id, text, reply_markup=markup, parse_mode=ParseMode.HTML)


async def refresh_token(vkuser):
    try:
        with aiohttp.ClientSession() as session:
            r = await session.request('GET', TOKEN_REFRESH_URL, params={'token': vkuser.token})
            data = await r.json()
            if data['ok']:
                vkuser.token = data['token']
                vkuser.save()
                session.close()
            else:
                return False
        return True
    except:
        pass


@dp.callback_query_handler(func=lambda call: call and call.message and call.data and call.data.startswith('logged'))
async def check_logged(call: types.CallbackQuery):
    vkuser = VkUser.objects.filter(owner__uid=call.from_user.id).count()
    if vkuser:
        await handle_join(call.message, edit=True, chat_id=call.message.chat.id, message_id=call.message.message_id,
                          exclude=True)
    else:
        await bot.answer_callback_query(call.id, 'Вход не выполнен! Сперва нужно выполнить вход в ВК через бота',
                                        show_alert=True)


@dp.callback_query_handler(func=lambda call: call and call.message and call.data and call.data.startswith('page'))
async def page_switcher(call: types.CallbackQuery):
    # user, created = await update_user_info(call.from_user)
    # tgchat, tgchat_created = await update_chat_info(call.message.chat)
    page = int(call.data.split('page')[-1])
    message_markup = MessageMarkup.objects.filter(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    ).first()
    if message_markup:
        pages = json.loads(message_markup.buttons)
        markup = InlineKeyboardMarkup()
        for row in pages[page]:
            markup.row(*[InlineKeyboardButton(**button) for button in row])
        await get_pages_switcher(markup, page, pages)
        await bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
        await bot.answer_callback_query(call.id)
    else:
        await bot.answer_callback_query(call.id, 'Нет данных в Базе Данных', show_alert=True)


async def get_dialog_info(api, vk_chat_id, name_case='nom'):
    title = ''
    photo = ''
    dialog_type = ''
    if vk_chat_id >= 2000000000:
        dialog_info = await api('messages.getChat', chat_id=vk_chat_id - 2000000000)
        title = dialog_info['title']
        max_photo = get_max_photo(dialog_info)
        if max_photo:
            photo = dialog_info[max_photo]
        else:
            photo = None
        dialog_type = 'chat'
    elif vk_chat_id > 0:
        dialog_info = await api('users.get', user_ids=vk_chat_id, fields='photo_max', name_case=name_case)
        first_name = dialog_info[0]['first_name']
        last_name = dialog_info[0]['last_name'] or ''
        title = first_name + ' ' + last_name
        photo = dialog_info[0]['photo_max']
        dialog_type = 'user'
    elif vk_chat_id < 0:
        dialog_info = await api('groups.getById', group_ids=abs(vk_chat_id))
        title = dialog_info[0]['name']
        max_photo = get_max_photo(dialog_info[0])
        if max_photo:
            photo = dialog_info[0][max_photo]
        else:
            photo = None
        dialog_type = 'group'

    return {'title': title, 'photo': photo, 'type': dialog_type}


@dp.callback_query_handler(func=lambda call: call and call.message and call.data and call.data.startswith('ping'))
async def ping_button(call: types.CallbackQuery):
    tg_chat_id = int(call.data.split('ping')[-1])
    try:
        await bot.send_message(tg_chat_id, f'<a href="tg://user?id={call.from_user.id}">Ping!</a>',
                               parse_mode=ParseMode.HTML)
        await bot.answer_callback_query(call.id, 'Ping!')
    except BadRequest:
        await bot.answer_callback_query(call.id, 'Нет доступа к чату, бот кикнут или чат удалён!', show_alert=True)


@dp.callback_query_handler(
    func=lambda call: call and call.message and call.data and call.data.startswith('deleteforward'))
async def delete_forward(call: types.CallbackQuery):
    forward_id = int(call.data.split('deleteforward')[-1])
    forward_in_db = Forward.objects.filter(id=forward_id).first()
    if forward_in_db:
        forward_in_db.delete()

    markup = InlineKeyboardMarkup()

    message_markup = MessageMarkup.objects.filter(
        message_id=call.message.message_id,
        chat_id=call.message.chat.id
    ).first()

    buttons = json.loads(message_markup.buttons)

    for row in buttons:
        if row[1]['callback_data'] == call.data:
            buttons.remove(row)
        else:
            markup.row(*[InlineKeyboardButton(**button) for button in row])
    if message_markup:
        if buttons:
            message_markup.buttons = json.dumps(buttons)
            message_markup.save()
            await bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
        else:
            await bot.edit_message_text(
                'У Вас нет связанных чатов. Чтобы привязать чат, добавьте бота в группу, а если бот уже добавлен - используйте команду /dialogs',
                call.message.chat.id, call.message.message_id)
        await bot.answer_callback_query(call.id, 'Успешно удалено!')
    else:
        await bot.edit_message_text('<b>Что-то пошло не так, нет информации в Базе Данных</b>',
                                    message_id=call.message.message_id, chat_id=call.message.chat.id, reply_markup=None)
        await bot.answer_callback_query(call.id, 'Ошибка!')


@dp.callback_query_handler(func=lambda call: call and call.message and call.data and call.data.startswith('setinfo'))
async def set_info(call: types.CallbackQuery):
    user, created = await update_user_info(call.from_user)
    tgchat, tgchat_created = await update_chat_info(call.message.chat)
    vk_chat_id = int(call.data.split('setinfo')[-1])
    vkuser = VkUser.objects.filter(owner=user).first()
    if vkuser:
        ME = await bot.me
        can_edit = False
        if not call.message.chat.all_members_are_administrators and (
                (await bot.get_chat_member(call.message.chat.id, ME.id)).status == 'administrator'):
            can_edit = True
        if not can_edit:
            admins = await bot.get_chat_administrators(call.message.chat.id)
            for admin in admins:
                if admin.user.id == ME.id and admin.can_change_info:
                    can_edit = True
                    break
        if can_edit:
            vksession = VkSession(access_token=vkuser.token, driver=await get_driver(vkuser.token))
            api = API(vksession)
            dialog_info = await get_dialog_info(api, vk_chat_id, name_case='nom')
            if dialog_info.get('title', ''):
                await bot.set_chat_title(call.message.chat.id, dialog_info['title'])
            if dialog_info.get('photo', ''):
                content = await get_content(dialog_info['photo'])
                await bot.set_chat_photo(call.message.chat.id, content['content'])
                content['content'].close()
                try:
                    os.remove(os.path.join(content['temp_path'], content['file_name'] + content['custom_ext']))
                except:
                    pass

            if dialog_info['type'] == 'user':
                dialog_info = await get_dialog_info(api, vk_chat_id, name_case='ins')
                text = f'Чат успешно привязан к диалогу c <i>{dialog_info["title"]}</i>'
            elif dialog_info['type'] == 'group':
                text = f'Чат успешно привязан к диалогу с сообществом <i>{dialog_info["title"]}</i>'
            else:
                text = f'Чат успешно привязан к диалогу <i>{dialog_info["title"]}</i>'

            await bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode=ParseMode.HTML)
            await bot.answer_callback_query(call.id)
        else:
            await bot.answer_callback_query(call.id,
                                            'Недостаточно прав для редактирования информации о группе или бот не администратор!',
                                            show_alert=True)

    else:
        await bot.answer_callback_query(call.id, 'Вход не выполнен! Сперва нужно выполнить вход в ВК через бота',
                                        show_alert=True)


@dp.callback_query_handler(func=lambda call: call and call.message and call.data and call.data.startswith('chat'))
async def choose_chat(call: types.CallbackQuery):
    user, created = await update_user_info(call.from_user)
    tgchat, tgchat_created = await update_chat_info(call.message.chat)
    vk_chat_id = int(call.data.split('chat')[-1])
    vkuser = VkUser.objects.filter(owner=user).first()
    if vkuser:
        if call.message.chat.type == 'private':
            vksession = VkSession(access_token=vkuser.token, driver=await get_driver(vkuser.token))
            api = API(vksession)
            dialog_info = await get_dialog_info(api, vk_chat_id, name_case='gen')
            markup = types.ForceReply(selective=False)
            if dialog_info['type'] == 'user':
                text = f'Сообщение для <i>{dialog_info["title"]}</i>'
            elif dialog_info['type'] == 'group':
                text = f'Сообщение сообществу <i>{dialog_info["title"]}</i>'
            else:
                text = f'Сообщение в диалог <i>{dialog_info["title"]}</i>'

            tg_message = await bot.send_message(call.message.chat.id, text, reply_markup=markup,
                                                parse_mode=ParseMode.HTML)
            Message.objects.create(
                tg_chat=tg_message.chat.id,
                tg_id=tg_message.message_id,
                vk_chat=vk_chat_id
            )
            await bot.answer_callback_query(call.id)
        else:
            forward = Forward.objects.filter(tgchat=tgchat).first()
            vkchat = (await get_vk_chat(int(vk_chat_id)))[0]
            if forward:
                forward.vkchat = vkchat
                forward.save()
            else:
                Forward.objects.create(
                    tgchat=tgchat,
                    vkchat=vkchat,
                    owner=user
                )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton('Установить аватар и название', callback_data=f'setinfo{vkchat.cid}'))
            text = 'Чат успешно привязан. Я могу автоматически изменить название и установить аватар, сделай бота администратором и убедись в наличии прав на редактирование информации группы'
            if call.message.chat.type == 'group':
                text += '\n<b>Внимание!</b> Параметр <i>"All Members Are Administrators"</i> должен быть отключён и боту должна быть присвоена админка в отдельном порядке!'
            try:
                await bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup,
                                            parse_mode=ParseMode.HTML)
            except MessageNotModified:
                pass
            await bot.answer_callback_query(call.id)
    else:
        await bot.answer_callback_query(call.id, 'Вход не выполнен! Сперва нужно выполнить вход в ВК через бота',
                                        show_alert=True)


@dp.callback_query_handler(func=lambda call: call and call.message and call.data and call.data == 'search')
async def search_callback(call: types.CallbackQuery):
    vkuser = VkUser.objects.filter(owner__uid=call.from_user.id).count()
    if vkuser:
        markup = types.ForceReply(selective=False)
        await bot.send_message(call.message.chat.id, '<b>Поиск беседы 🔍</b>', parse_mode=ParseMode.HTML,
                               reply_markup=markup)
        await bot.answer_callback_query(call.id, 'Поиск беседы 🔍')
    else:
        await bot.answer_callback_query(call.id, 'Вход не выполнен! Сперва нужно выполнить вход в ВК через бота',
                                        show_alert=True)


@dp.message_handler(commands=['start'])
async def send_welcome(msg: types.Message):
    if ALLOWED_USER_IDS:
        if str(msg.from_user.id) not in ALLOWED_USER_IDS.replace(' ','').split(','):
            await msg.reply('⛔️ Бот недоступен для Вашего аккаунта.\nУзнать Telegram ID - /id')
            return
    user, created = await update_user_info(msg.from_user)
    tgchat, tgchat_created = await update_chat_info(msg.chat)
    if not tgchat:
        existing_vkuser = VkUser.objects.filter(owner=user).count()
        if not existing_vkuser:
            link = 'https://oauth.vk.com/authorize?client_id={}&' \
                   'display=page&redirect_uri=https://oauth.vk.com/blank.html&scope=friends,messages,offline,docs,photos,video,stories,audio' \
                   '&response_type=token&v={}'.format(VK_APP_ID, API_VERSION)
            mark = InlineKeyboardMarkup()
            login = InlineKeyboardButton('ВХОД', url=link)
            mark.add(login)
            await msg.reply('Привет, этот бот поможет тебе общаться ВКонтакте, войди по кнопке ниже'
                            ' и отправь мне то, что получишь в адресной строке.',
                            reply_markup=mark)
        else:
            await msg.reply('Вход уже выполнен!\n/stop для выхода.')
    else:
        markup = InlineKeyboardMarkup()
        me = await bot.me
        markup.add(InlineKeyboardButton('Перейти в бота', url=f'https://t.me/{me.username}?start=login'))
        await msg.reply('Залогиниться можно только через личный чат с ботом', reply_markup=markup)


@dp.message_handler(commands=['stop'])
async def stop_command(msg: types.Message):
    user, created = await update_user_info(msg.from_user)
    tgchat, tgchat_created = await update_chat_info(msg.chat)

    existing_vkuser = VkUser.objects.filter(owner=user).first()
    if not existing_vkuser:
        await msg.reply('Вход не выполнен! Используй команду /start для входа')
    else:
        polling = next((task for task in TASKS if task['token'] == existing_vkuser.token), None)
        if polling:
            polling['task'].cancel()
        driver = DRIVERS.get(existing_vkuser.token, '')
        if driver:
            driver.close()
            del DRIVERS[existing_vkuser.token]
        existing_vkuser.delete()
        await msg.reply('Успешный выход!')


@dp.message_handler(commands=['dialogs', 'd'])
async def dialogs_command(msg: types.Message):
    if msg.chat.type == 'private':
        await handle_join(msg, text='Выберите диалог для быстрого ответа')
    else:
        await handle_join(msg, exclude=True)


@dp.message_handler(commands=['read', 'r'])
async def read_command(msg: types.Message):
    user, created = await update_user_info(msg.from_user)
    tgchat, tgchat_created = await update_chat_info(msg.chat)
    if await logged(msg.from_user.id, msg.message_id, msg.chat.id):
        vk_user = VkUser.objects.filter(owner=user).first()
        if msg.chat.type == 'private':
            if msg.reply_to_message:
                message_in_db = Message.objects.filter(tg_chat=msg.chat.id,
                                                       tg_id=msg.reply_to_message.message_id).first()
                if message_in_db:
                    vksession = VkSession(access_token=vk_user.token, driver=await get_driver(vk_user.token))
                    api = API(vksession)
                    await api('messages.markAsRead', peer_id=message_in_db.vk_chat)
                    await bot.send_message(msg.chat.id, '<i>Диалог прочитан</i>', parse_mode=ParseMode.HTML)
                else:
                    await msg.reply('Не знаю какой чат прочесть, нет информации в базе данных')
        else:
            forward = Forward.objects.filter(tgchat=tgchat).first()
            if forward:
                vksession = VkSession(access_token=vk_user.token, driver=await get_driver(vk_user.token))
                api = API(vksession)
                await api('messages.markAsRead', peer_id=forward.vkchat.cid)
                await bot.send_message(msg.chat.id, '<i>Диалог прочитан</i>', parse_mode=ParseMode.HTML)
            else:
                await msg.reply('Этот чат не привязан к диалогу ВКонтакте, для привязки используй команду /dialogs')


@dp.message_handler(commands=['search', 's'])
async def search_command(msg: types.Message):
    user, created = await update_user_info(msg.from_user)
    vkuser = VkUser.objects.filter(owner=user).count()
    if vkuser:
        markup = types.ForceReply(selective=False)
        await bot.send_message(msg.chat.id, '<b>Поиск беседы 🔍</b>', parse_mode=ParseMode.HTML,
                               reply_markup=markup)
    else:
        await bot.answer_callback_query(msg, 'Вход не выполнен! Сперва нужно выполнить вход в ВК через бота',
                                        show_alert=True)


@dp.message_handler(commands=['chat', 'chats'])
async def chat_command(msg: types.Message):
    user, created = await update_user_info(msg.from_user)
    tgchat, tgchat_created = await update_chat_info(msg.chat)
    forwards = Forward.objects.filter(owner=user)
    if await logged(msg.from_user.id, msg.message_id, msg.chat.id):
        if forwards:
            vk_user = VkUser.objects.filter(owner=user).first()
            vksession = VkSession(access_token=vk_user.token, driver=await get_driver(vk_user.token))
            api = API(vksession)
            markup = InlineKeyboardMarkup()
            for forward in forwards:
                chat = await get_dialog_info(api, forward.vkchat.cid)
                markup.row(*[InlineKeyboardButton(chat['title'], callback_data=f'ping{forward.tgchat.cid}'),
                             InlineKeyboardButton('❌', callback_data=f'deleteforward{forward.pk}')])
            msg_with_markup = await bot.send_message(msg.chat.id,
                                                     'Список привязанных диалогов\nНажав на имя диалога, бот пинганёт Вас в соответствующем чате Telegram.\nНажав на "❌", привязка чата будет удалена и все сообщение из диалога ВКонтакте будут попадать напрямую к боту',
                                                     reply_markup=markup)
            for row in markup.inline_keyboard:
                for button in range(len(row)):
                    row[button] = row[button].to_python()
            MessageMarkup.objects.create(
                message_id=msg_with_markup.message_id,
                chat_id=msg_with_markup.chat.id,
                buttons=json.dumps(markup.inline_keyboard)
            )
        else:
            await bot.send_message(msg.chat.id,
                                   'У Вас нет связанных чатов. Чтобы привязать чат, добавьте бота в группу, а если бот уже добавлен - используйте команду /dialogs')


@dp.message_handler(commands=['help'])
async def help_command(msg: types.Message):
    user, created = await update_user_info(msg.from_user)
    tgchat, tgchat_created = await update_chat_info(msg.chat)
    HELP_MESSAGE = '/start - Логин в Вконтакте\n' \
                   '/dialogs /d - Список диалогов\n' \
                   '/read /r - Прочесть диалог ВКонтакте\n' \
                   '/search /s - Поиск по диалогам\n' \
                   '/chat - Список связанных чатов с диалогами ВКонтакте, привязать чат к диалогу можно добавив бота в группу\n' \
                   '/stop - Выход из ВКонтакте\n' \
                   '/help - Помощь' \
                   '/id - Узнать Telegram ID'

    await bot.send_message(msg.chat.id, HELP_MESSAGE, parse_mode=ParseMode.HTML)

@dp.message_handler(commands=['id'])
async def id_command(msg: types.Message):
    user, created = await update_user_info(msg.from_user)
    await bot.send_message(msg.chat.id, 'Ваш ID: <code>{}</code>'.format(msg.from_user.id), parse_mode=ParseMode.HTML)

@dp.message_handler(content_types=['text'])
async def handle_text(msg: types.Message):
    user, created = await update_user_info(msg.from_user)
    tgchat, tgchat_created = await update_chat_info(msg.chat)
    if msg.chat.type == 'private':
        token = parse_oauth_token(msg.text)
        if token:
            if ALLOWED_USER_IDS:
                if str(msg.from_user.id) not in ALLOWED_USER_IDS.replace(' ', '').split(','):
                    await msg.reply('⛔️ Бот недоступен для Вашего аккаунта.\nУзнать Telegram ID - /id')
                    return
            await bot.send_chat_action(msg.from_user.id, ChatActions.TYPING)
            if not VkUser.objects.filter(token=token).exists():
                try:
                    session = VkSession(access_token=token, driver=await get_driver(token))
                    api = API(session)
                    vkuserinfo = await api('account.getProfileInfo', name_case='gen')
                    vkuser, vkuser_created = VkUser.objects.update_or_create(
                        defaults={'token': token, 'is_polling': True}, owner=user)
                    existing_polling = next((task for task in TASKS if task['token'] == vkuser.token), None)
                    if existing_polling:
                        existing_polling['task'].cancel()
                    driver = DRIVERS.get(vkuser.token, '')
                    if driver:
                        driver.close()
                        del DRIVERS[vkuser.token]
                    refreshed_token = await refresh_token(vkuser)
                    TASKS.append({'token': vkuser.token, 'task': asyncio.ensure_future(vk_polling(vkuser))})
                    logged_in = await msg.reply(
                        'Вход выполнен в аккаунт {} {}!\n[Использование](https://akentev.com/tgvkbot/usage/)'.format(
                            vkuserinfo['first_name'], vkuserinfo.get('last_name', '')), parse_mode='Markdown')
                    if refreshed_token:
                        await logged_in.reply('*Вам доступна музыка 🎵*', parse_mode='Markdown')
                except VkAuthError:
                    await msg.reply('Неверная ссылка, попробуйте ещё раз!')
            else:
                await msg.reply('Вход уже выполнен!\n/stop для выхода.')
            return
    if await logged(msg.from_user.id, msg.message_id, msg.chat.id):
        if msg.reply_to_message and msg.reply_to_message.text == 'Поиск беседы 🔍':
            if msg.chat.type == 'private' or not Message.objects.filter(tg_id=msg.reply_to_message.message_id,
                                                                        tg_chat=msg.reply_to_message.chat.id).exists():
                await search_dialogs(msg, user)
                return
        vk_user = VkUser.objects.filter(owner=user).first()
        forward = Forward.objects.filter(tgchat=tgchat).first()
        forward_messages_exists, message = await is_forwarding(msg.text)
        message_options = await generate_send_options(msg, forward, forward_messages_exists, message)
        if message_options != {}:
            vk_message = await vk_sender(vk_user.token, msg, **message_options)
            if not vk_message:
                await msg.reply('<b>Произошла ошибка при отправке</b>', parse_mode=ParseMode.HTML)


@dp.message_handler(content_types=['contact'])
async def handle_contact(msg: types.Message):
    new_text = msg.contact.first_name
    if msg.contact.last_name:
        new_text += ' ' + msg.contact.last_name
    new_text += '\n'
    new_text += msg.contact.phone_number
    msg.text = new_text
    await handle_text(msg)


@dp.message_handler(content_types=['photo', 'sticker'])
async def handle_photo(msg: types.Message):
    user, user_created = await update_user_info(msg.from_user)
    tgchat, tgchat_created = await update_chat_info(msg.chat)
    if await logged(msg.from_user.id, msg.message_id, msg.chat.id):
        vk_user = VkUser.objects.filter(owner=user).first()
        forward = Forward.objects.filter(tgchat=tgchat).first()
        forward_messages_exists, message = await is_forwarding(msg.caption)
        message_options = await generate_send_options(msg, forward, forward_messages_exists, message)
        if msg.content_type == 'photo':
            file_id = msg.photo[-1].file_id
        elif msg.content_type == 'sticker':
            if msg.sticker.to_python()['is_animated']:
                file_id = msg.sticker.thumb.file_id
            else:
                file_id = msg.sticker.file_id
        if message_options:
            message_options['attachment'] = await upload_attachment(msg, vk_user, file_id, message_options['peer_id'],
                                                                    attachment_type='photo',
                                                                    upload_field='photo',
                                                                    upload_method='photos.getMessagesUploadServer',
                                                                    on_server_field='photo',
                                                                    save_method='photos.saveMessagesPhoto')
            if message_options['attachment']:
                vk_message = await vk_sender(vk_user.token, msg, **message_options)
                if not vk_message:
                    await msg.reply('<b>Произошла ошибка при отправке</b>', parse_mode=ParseMode.HTML)
            else:
                await msg.reply('<b>Ошибка при загрузке файла. Сообщение не отправлено!</b>', parse_mode=ParseMode.HTML)


@dp.message_handler(content_types=['document', 'voice', 'audio'])
async def handle_documents(msg: types.Message):
    user, user_created = await update_user_info(msg.from_user)
    tgchat, tgchat_created = await update_chat_info(msg.chat)
    if await logged(msg.from_user.id, msg.message_id, msg.chat.id):
        vk_user = VkUser.objects.filter(owner=user).first()
        if tgchat:
            forward = Forward.objects.filter(tgchat=tgchat).first()
        else:
            forward = None
        forward_messages_exists, message = await is_forwarding(msg.caption)
        message_options = await generate_send_options(msg, forward, forward_messages_exists, message)
        file_id = getattr(msg, msg.content_type).file_id
        if message_options:
            upload_attachment_options = {
                'attachment_type': 'doc',
                'upload_field': 'file',
                'upload_method': 'docs.getUploadServer',
                'on_server_field': 'file',
                'save_method': 'docs.save',
            }
            if hasattr(getattr(msg, msg.content_type), 'file_name') and getattr(msg, msg.content_type).file_name:
                upload_attachment_options['title'] = getattr(msg, msg.content_type).file_name

            if msg.content_type == 'voice':
                upload_attachment_options['upload_type'] = 'audio_message'

            # https://vk.com/wall-1_395554
            # if msg.content_type == 'sticker':
            #     if msg.sticker.to_python()['is_animated']:
            #         file_id = msg.sticker.thumb.file_id
            #     upload_attachment_options['upload_type'] = 'graffiti'
            #     upload_attachment_options['rewrite_name'] = True
            #     upload_attachment_options['default_name'] = 'graffiti.png'

            if msg.content_type == 'audio':
                audioname = ''
                if msg.audio.performer and msg.audio.title:
                    audioname += msg.audio.performer + ' - ' + msg.audio.title
                elif msg.audio.performer:
                    audioname += msg.audio.performer
                elif msg.audio.title:
                    audioname += msg.audio.title
                else:
                    audioname = f'tgvkbot_audio_{file_id}'
                upload_attachment_options['title'] = audioname

            message_options['attachment'] = await upload_attachment(msg, vk_user, file_id, message_options['peer_id'],
                                                                    **upload_attachment_options)
            if message_options['attachment']:
                vk_message = await vk_sender(vk_user.token, msg, **message_options)
                if not vk_message:
                    await msg.reply('<b>Произошла ошибка при отправке</b>', parse_mode=ParseMode.HTML)
            else:
                await msg.reply('<b>Ошибка при загрузке файла. Сообщение не отправлено!</b>', parse_mode=ParseMode.HTML)


@dp.message_handler(content_types=['video', 'video_note'])
async def handle_videos(msg: types.Message):
    user, user_created = await update_user_info(msg.from_user)
    tgchat, tgchat_created = await update_chat_info(msg.chat)
    if await logged(msg.from_user.id, msg.message_id, msg.chat.id):
        vk_user = VkUser.objects.filter(owner=user).first()
        if tgchat:
            forward = Forward.objects.filter(tgchat=tgchat).first()
        else:
            forward = None
        forward_messages_exists, message = await is_forwarding(msg.caption)
        message_options = await generate_send_options(msg, forward, forward_messages_exists, message)
        file_id = getattr(msg, msg.content_type).file_id
        if message_options:
            upload_attachment_options = {
                'attachment_type': 'video',
                'upload_field': 'video_file',
                'upload_method': 'video.save',
            }
            if hasattr(getattr(msg, msg.content_type), 'file_name') and getattr(msg, msg.content_type).file_name:
                upload_attachment_options['title'] = getattr(msg, msg.content_type).file_name

            message_options['attachment'] = await upload_attachment(msg, vk_user, file_id, message_options['peer_id'],
                                                                    **upload_attachment_options)
            if message_options['attachment']:
                vk_message = await vk_sender(vk_user.token, msg, **message_options)
                if not vk_message:
                    await msg.reply('<b>Произошла ошибка при отправке</b>', parse_mode=ParseMode.HTML)
            else:
                await msg.reply('<b>Ошибка при загрузке файла. Сообщение не отправлено!</b>', parse_mode=ParseMode.HTML)


@dp.message_handler(content_types=['new_chat_members'], func=is_bot_in_iterator)
async def handle_join(msg: types.Message, edit=False, chat_id=None, message_id=None, text='', exclude=False):
    user, user_created = await update_user_info(msg.from_user)
    tgchat, tgchat_created = await update_chat_info(msg.chat)
    forward = Forward.objects.filter(tgchat=tgchat).first()
    try:
        await bot.send_chat_action(msg.chat.id, 'typing')
    except:
        return
    vk_user = VkUser.objects.filter(owner=user).first()
    pages = None
    reply_to_message_id = None
    markup = None
    if vk_user:
        if forward:
            text = text or '<i>Этот чат уже привязан к диалогу ВКонтакте, Вы можете выбрать новый диалог</i>'
        else:
            text = text or '<i>Выберите диалог ВКонтакте к которому будет привязан этот чат</i>'
        markup = InlineKeyboardMarkup()
        excluded_ids = []
        if exclude:
            excluded_ids = [forward.vkchat.cid for forward in Forward.objects.filter(owner=user)]
        pages = await get_dialogs(vk_user.token, excluded_ids)
        if pages:
            for buttons_row in pages[0]:
                markup.row(*buttons_row)
            await get_pages_switcher(markup, 0, pages)
    else:
        me = await bot.me
        if msg.chat.type == 'private':
            text = 'Вход не выполнен! /start для входа'
            reply_to_message_id = msg.message_id
        else:
            text = '<i>Вход не выполнен! Сперва нужно выполнить вход в ВК через бота</i>'
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton('ВХОД', url=f'https://t.me/{me.username}?start=login'),
                       InlineKeyboardButton('✅ Я залогинился', callback_data=f'logged-{msg.from_user.id}'))
    if edit:
        msg_with_markup = await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id,
                                                      reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        msg_with_markup = await bot.send_message(msg.chat.id, text=text, reply_markup=markup, parse_mode=ParseMode.HTML,
                                                 reply_to_message_id=reply_to_message_id)
    if pages:
        for page in pages:
            for row in page:
                for button in range(len(row)):
                    row[button] = row[button].to_python()

        MessageMarkup.objects.create(
            message_id=msg_with_markup.message_id,
            chat_id=msg_with_markup.chat.id,
            buttons=json.dumps(pages)
        )


@dp.message_handler(content_types=types.ContentType.ANY, func=lambda msg: msg.group_chat_created is True)
async def handle_new_group(msg: types.Message):
    await handle_join(msg)


@dp.message_handler(content_types=types.ContentType.ANY, func=lambda message: message.migrate_to_chat_id)
async def handle_chat_migration(msg: types.Message):
    # Юзеру сначала нужно выбрать чат для привязки, а уже ПОТОМ делать миграцию. Иначе старый chatid останется на иналйнкнопках
    forwards = Forward.objects.filter(tgchat__cid=msg.chat.id)
    for forward in forwards:
        forward.tgchat.cid = msg.migrate_to_chat_id
        forward.tgchat.save()

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton('Установить аватар и название', callback_data=f'setinfo{forward.vkchat.cid}'))
        await bot.send_message(msg.migrate_to_chat_id,
                               text='Отлично! Теперь можно установить аватар и название. Если кнопка выше не работает, то воспользуйтесь этой.',
                               reply_markup=markup)


if __name__ == '__main__':
    TASKS = vk_polling_tasks()
    asyncio.gather(*[task['task'] for task in TASKS])

    executor.start_polling(dp)
