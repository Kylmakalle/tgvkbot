from concurrent.futures._base import CancelledError

from aiovk.longpoll import LongPoll

from bot import *

log = logging.getLogger('vk_messages')


################### Честно взято по лицензии https://github.com/vk-brain/sketal/blob/master/LICENSE ###################

def parse_msg_flags(bitmask, keys=('unread', 'outbox', 'replied', 'important', 'chat',
                                   'friends', 'spam', 'deleted', 'fixed', 'media', 'hidden')):
    """Функция для чтения битовой маски и возврата словаря значений"""

    start = 1
    values = []
    for _ in range(1, 12):
        result = bitmask & start
        start *= 2
        values.append(bool(result))
    return dict(zip(keys, values))


from enum import Enum


class Wait(Enum):
    NO = 0
    YES = 1
    CUSTOM = 2


class EventType(Enum):
    Longpoll = 0
    ChatChange = 1
    Callback = 2


class Event:
    __slots__ = ("api", "type", "reserved_by", "occupied_by", "meta")

    def __init__(self, api, evnt_type):
        self.api = api
        self.type = evnt_type

        self.meta = {}

        self.reserved_by = []
        self.occupied_by = []


# https://vk.com/dev/using_longpoll
class LongpollEvent(Event):
    __slots__ = ("evnt_data", "id")

    def __init__(self, api, evnt_id, evnt_data):
        super().__init__(api, EventType.Longpoll)

        self.id = evnt_id
        self.evnt_data = evnt_data

    def __str__(self):
        return f"LongpollEvent ({self.id}, {self.evnt_data[1] if len(self.evnt_data) > 1 else '_'})"


class MessageEventData(object):
    __slots__ = ("is_multichat", "user_id", "full_text", "full_message_data",
                 "time", "msg_id", "attaches", "is_out", "forwarded", "chat_id",
                 "true_user_id", "is_forwarded", "true_msg_id")

    @staticmethod
    def from_message_body(obj):
        data = MessageEventData()

        data.attaches = {}
        data.forwarded = []

        c = 0
        for a in obj.get("attachments", []):
            c += 1

            data.attaches[f'attach{c}_type'] = a['type']
            try:
                data.attaches[f'attach{c}'] = f'{a[a["type"]]["owner_id"]}_{a[a["type"]]["id"]}'
            except KeyError:
                data.attaches[f'attach{c}'] = ""

        if 'fwd_messages' in obj:
            data.forwarded = MessageEventData.parse_brief_forwarded_messages(obj)

        if "chat_id" in obj:
            data.is_multichat = True
            data.chat_id = int(obj["chat_id"])

        if "id" in obj:
            data.msg_id = obj["id"]
            data.true_msg_id = obj["id"]

        data.user_id = int(obj['user_id'])
        data.true_user_id = int(obj['user_id'])
        data.full_text = obj['body']
        data.time = int(obj['date'])
        data.is_out = obj.get('out', False)
        data.is_forwarded = False
        data.full_message_data = obj

        return data

    @staticmethod
    def parse_brief_forwarded_messages(obj):
        if 'fwd_messages' not in obj:
            return ()

        result = []

        for mes in obj['fwd_messages']:
            result.append((mes.get('id', None), MessageEventData.parse_brief_forwarded_messages(mes)))

        return tuple(result)

    @staticmethod
    def parse_brief_forwarded_messages_from_lp(data):
        result = []

        token = ""
        i = -1
        while True:
            i += 1

            if i >= len(data):
                if token:
                    result.append((token, ()))

                break

            if data[i] in "1234567890_-":
                token += data[i]
                continue

            if data[i] in (",", ")"):
                if not token:
                    continue

                result.append((token, ()))
                token = ""
                continue

            if data[i] == ":":
                stack = 1

                for j in range(i + 2, len(data)):
                    if data[j] == "(":
                        stack += 1

                    elif data[j] == ")":
                        stack -= 1

                    if stack == 0:
                        jump_to_i = j
                        break

                sub_data = data[i + 2: jump_to_i]

                result.append((token, MessageEventData.parse_brief_forwarded_messages_from_lp(sub_data)))

                i = jump_to_i + 1
                token = ""
                continue

        return tuple(result)

    def __init__(self):
        self.is_multichat = False
        self.is_forwarded = False
        self.is_out = False

        self.chat_id = 0
        self.user_id = 0
        self.true_user_id = 0
        self.full_text = ""
        self.time = ""
        self.msg_id = 0
        self.true_msg_id = 0
        self.attaches = None
        self.forwarded = None
        self.full_message_data = None


class Attachment(object):
    __slots__ = ('type', 'owner_id', 'id', 'access_key', 'url', 'ext')

    def __init__(self, attach_type, owner_id, aid, access_key=None, url=None, ext=None):
        self.type = attach_type
        self.owner_id = owner_id
        self.id = aid
        self.access_key = access_key
        self.url = url
        self.ext = ext

    @staticmethod
    def from_upload_result(result, attach_type="photo"):
        url = None

        for k in result:
            if "photo_" in k:
                url = result[k]
            elif "link_" in k:
                url = result[k]
            elif "url" == k:
                url = result[k]

        return Attachment(attach_type, result["owner_id"], result["id"], url=url, ext=result.get("ext"))

    @staticmethod
    def from_raw(raw_attach):
        a_type = raw_attach['type']
        attach = raw_attach[a_type]

        url = None

        for k, v in attach.items():
            if "photo_" in k:
                url = v
            elif "link_" in k:
                url = v
            elif "url" == k:
                url = v

        return Attachment(a_type, attach.get('owner_id', ''), attach.get('id', ''), attach.get('access_key'), url,
                          ext=attach.get("ext"))

    def value(self):
        if self.access_key:
            return f'{self.type}{self.owner_id}_{self.id}_{self.access_key}'

        return f'{self.type}{self.owner_id}_{self.id}'

    def __str__(self):
        return self.value()


MAX_LENGHT = 4000

from math import ceil


class LPMessage(object):
    """Класс, объект которого передаётся в плагин для упрощённого ответа"""

    __slots__ = ('message_data', 'api', 'is_multichat', 'chat_id', 'user_id', 'is_out', 'true_user_id',
                 'timestamp', 'answer_values', 'msg_id', 'text', 'full_text', 'meta', 'is_event',
                 'brief_attaches', 'brief_forwarded', '_full_attaches', '_full_forwarded',
                 'reserved_by', 'occupied_by', 'peer_id', "is_forwarded", 'true_msg_id')

    def __init__(self, vk_api_object, message_data):
        self.message_data = message_data
        self.api = vk_api_object

        self.reserved_by = []
        self.occupied_by = []
        self.meta = {}

        self.is_event = False
        self.is_multichat = message_data.is_multichat
        self.is_forwarded = message_data.is_forwarded

        self.user_id = message_data.user_id
        self.true_user_id = message_data.true_user_id
        self.chat_id = message_data.chat_id
        self.peer_id = (message_data.chat_id or message_data.user_id) + self.is_multichat * 2000000000
        self.full_text = message_data.full_text
        self.text = self.full_text.replace("&quot;", "\"")  # Not need .lower() there # edited by @Kylmakalle

        self.msg_id = message_data.msg_id
        self.true_msg_id = message_data.true_msg_id
        self.is_out = message_data.is_out

        self.timestamp = message_data.time

        self.brief_forwarded = message_data.forwarded
        self._full_forwarded = None
        self.brief_attaches = message_data.attaches
        self._full_attaches = None

        if self.is_multichat:
            self.answer_values = {'chat_id': self.chat_id}

        else:
            self.answer_values = {'user_id': self.user_id}

    async def get_full_attaches(self):
        """Get list of all attachments as `Attachment` for this message"""

        if self._full_attaches is None:
            await self.get_full_data()

        return self._full_attaches

    async def get_full_forwarded(self):
        """Get list of all forwarded messages as `LPMessage` for this message"""

        if self._full_forwarded is None:
            await self.get_full_data()

        return self._full_forwarded

    async def get_full_data(self, message_data=None):
        """Update lists of all forwarded messages and all attachments for this message"""

        self._full_attaches = []
        self._full_forwarded = []

        if not message_data:
            values = {'message_ids': self.msg_id}

            full_message_data = await self.api.messages.getById(**values)

            if not full_message_data or not full_message_data['items']:  # Если пришёл пустой ответ от VK API
                return

            message = full_message_data['items'][0]

        else:
            message = message_data

        if "attachments" in message:
            for raw_attach in message["attachments"]:
                attach = Attachment.from_raw(raw_attach)  # Создаём аттач

                self._full_attaches.append(attach)  # Добавляем к нашему внутреннему списку аттачей

        if 'fwd_messages' in message:
            self._full_forwarded, self.brief_forwarded = await self.parse_forwarded_messages(message)

    async def parse_forwarded_messages(self, im):
        if 'fwd_messages' not in im:
            return (), ()

        result = []
        brief_result = []

        for mes in im['fwd_messages']:
            obj = MessageEventData.from_message_body(mes)

            obj.msg_id = self.msg_id
            obj.chat_id = self.chat_id
            obj.user_id = self.user_id
            obj.is_multichat = self.is_multichat
            obj.is_out = self.is_out
            obj.is_forwarded = True

            m = await LPMessage.create(self.api, obj)

            big_result, small_result = await self.parse_forwarded_messages(mes)

            result.append((m, big_result))
            brief_result.append((m.msg_id, small_result))

        return tuple(result), tuple(brief_result)

    @staticmethod
    def prepare_message(message):
        """Split message to parts that can be send by `messages.send`"""

        message_length = len(message)

        if message_length <= MAX_LENGHT:
            return [message]

        def fit_parts(sep):
            current_length = 0
            current_message = ""

            sep_length = len(sep)
            parts = message.split(sep)
            length = len(parts)

            for j in range(length):
                m = parts[j]
                temp_length = len(m)

                if temp_length > MAX_LENGHT:
                    return

                if j != length - 1 and current_length + temp_length + sep_length <= MAX_LENGHT:
                    current_message += m + sep
                    current_length += temp_length + sep_length

                elif current_length + temp_length <= MAX_LENGHT:
                    current_message += m
                    current_length += temp_length

                elif current_length + temp_length > MAX_LENGHT:
                    yield current_message

                    current_length = temp_length
                    current_message = m

                    if j != length - 1 and current_length + sep_length < MAX_LENGHT:
                        current_message += sep
                        current_length += sep_length

            if current_message:
                yield current_message

        result = list(fit_parts("\n"))

        if not result:
            result = list(fit_parts(" "))

            if not result:
                result = []

                for i in range(int(ceil(message_length / MAX_LENGHT))):
                    result.append(message[i * MAX_LENGHT: (i + 1) * MAX_LENGHT])

                return result

        return result

    @staticmethod
    async def create(vk_api_object, data):
        msg = LPMessage(vk_api_object, data)

        if data.full_message_data:
            await msg.get_full_data(data.full_message_data)

        return msg


class ChatChangeEvent(Event):
    __slots__ = ("source_act", "source_mid", "chat_id", "new_title",
                 "old_title", "changer", "chat_id", "new_cover", "user_id")

    def __init__(self, api, user_id, chat_id, source_act, source_mid, new_title, old_title, new_cover, changer):
        super().__init__(api, EventType.ChatChange)

        self.chat_id = chat_id
        self.user_id = user_id

        self.source_act = source_act
        self.source_mid = source_mid

        self.new_cover = new_cover

        self.new_title = new_title
        self.old_title = old_title
        self.changer = changer


async def check_event(api, user_id, chat_id, attaches):
    if chat_id != 0 and "source_act" in attaches:
        photo = attaches.get("attach1_type") + attaches.get("attach1") if "attach1" in attaches else None

        evnt = ChatChangeEvent(api, user_id, chat_id, attaches.get("source_act"),
                               int(attaches.get("source_mid", 0)), attaches.get("source_text"),
                               attaches.get("source_old_text"), photo, int(attaches.get("from", 0)))

        await process_event(evnt)

        return True

    return False


async def process_longpoll_event(api, new_event):
    if not new_event:
        return

    event_id = new_event[0]

    if event_id != 4 and event_id != 5:
        evnt = LongpollEvent(api, event_id, new_event)

        return  # await process_event(evnt)

    data = MessageEventData()
    data.msg_id = new_event[1]
    data.attaches = new_event[6]
    data.time = int(new_event[4])

    try:
        data.user_id = int(data.attaches['from'])
        data.chat_id = int(new_event[3]) - 2000000000
        data.is_multichat = True

        del data.attaches['from']

    except KeyError:
        data.user_id = int(new_event[3])
        data.is_multichat = False

    # https://vk.com/dev/using_longpoll_2
    flags = parse_msg_flags(new_event[2])

    if flags['outbox']:
        return

        data.is_out = True

    data.full_text = new_event[5].replace('<br>', '\n')

    if "fwd" in data.attaches:
        data.forwarded = MessageEventData.parse_brief_forwarded_messages_from_lp(data.attaches["fwd"])
        del data.attaches["fwd"]

    else:
        data.forwarded = []

    msg = LPMessage(api, data)

    if await check_event(api, data.user_id, data.chat_id, data.attaches):
        msg.is_event = True

    await process_message(msg)


#######################################################################################################################


async def process_message(msg, token=None, is_multichat=None, vk_chat_id=None, user_id=None, forward_settings=None,
                          vkchat=None,
                          full_msg=None, forwarded=False, vk_msg_id=None, main_message=None, known_users=None):
    token = token or msg.api._session.access_token
    is_multichat = is_multichat or msg.is_multichat
    vk_msg_id = vk_msg_id or msg.msg_id
    user_id = user_id or msg.user_id
    known_users = known_users or {}

    vkuser = VkUser.objects.filter(token=token).first()
    if not vkuser:
        return

    if user_id not in known_users or {}:
        peer_id, first_name, last_name = await get_name(user_id, msg.api)
        known_users[user_id] = (peer_id, first_name, last_name)
    else:
        peer_id, first_name, last_name = known_users[user_id]

    if is_multichat:
        vk_chat_id = vk_chat_id or msg.peer_id
    else:
        vk_chat_id = vk_chat_id or peer_id

    if not vkchat:
        vkchat, created_vkchat = await get_vk_chat(vk_chat_id)
    forward_setting = forward_settings or Forward.objects.filter(owner=vkuser.owner, vkchat=vkchat).first()

    full_msg = full_msg or await msg.api('messages.getById', message_ids=', '.join(str(x) for x in [vk_msg_id]))
    if full_msg.get('items'):
        for vk_msg in full_msg['items']:
            disable_notify = bool(vk_msg.get('push_settings', False))
            attaches_scheme = []
            if vk_msg.get('attachments'):
                attaches_scheme = [await process_attachment(attachment) for attachment in
                                   vk_msg['attachments']]
            if vk_msg.get('geo'):
                location = vk_msg['geo']['coordinates'].split(' ')
                is_venue = vk_msg['geo'].get('place')
                if is_venue:
                    attaches_scheme.append({'content': [location[0], location[1], is_venue.get('title', 'Место'),
                                                        is_venue.get('city', 'Город')], 'type': 'venue'})
                else:
                    attaches_scheme.append({'content': [location[0], location[1]], 'type': 'location'})
            name = first_name + ((' ' + last_name) if last_name else '')
            if forward_setting:
                if forwarded or is_multichat:
                    header = f'<b>{name}</b>' + '\n'
                if not forwarded:
                    header = ''
                to_tg_chat = forward_setting.tgchat.cid
            else:
                if forwarded or not is_multichat:
                    header = f'<b>{name}</b>' + '\n'
                elif is_multichat:
                    header = f'<b>{name} @ {vk_msg["title"]}</b>' + '\n'
                to_tg_chat = vkuser.owner.uid

            body_parts = []
            body = vk_msg.get('body', '')
            if body:
                if (len(header) + len(body)) > MAX_MESSAGE_LENGTH:
                    body_parts = safe_split_text(header + body, MAX_MESSAGE_LENGTH)
                    body_parts[-1] = body_parts[-1] + '\n'
                else:
                    body += '\n'

            if attaches_scheme:
                first_text_attach = next((attach for attach in attaches_scheme if attach and attach['type'] == 'text'),
                                         None)
                if first_text_attach:
                    if body_parts and (len(first_text_attach) + len(body_parts[-1])) > MAX_MESSAGE_LENGTH:
                        body_parts.append(first_text_attach['content'])
                    else:
                        body += first_text_attach['content']
                    attaches_scheme.remove(first_text_attach)

            if body_parts:
                for body_part in range(len(body_parts)):
                    await bot.send_chat_action(to_tg_chat, ChatActions.TYPING)
                    tg_message = await bot.send_message(vkuser.owner.uid, body_parts[body_part],
                                                        parse_mode=ParseMode.HTML,
                                                        reply_to_message_id=main_message,
                                                        disable_notification=disable_notify)
                    Message.objects.create(
                        vk_chat=vk_chat_id,
                        vk_id=vk_msg_id,
                        tg_chat=tg_message.chat.id,
                        tg_id=tg_message.message_id
                    )
            elif not body_parts and (header + body):
                await bot.send_chat_action(to_tg_chat, ChatActions.TYPING)
                tg_message = await bot.send_message(to_tg_chat, header + body, parse_mode=ParseMode.HTML,
                                                    reply_to_message_id=main_message,
                                                    disable_notification=disable_notify)
                Message.objects.create(
                    vk_chat=vk_chat_id,
                    vk_id=vk_msg_id,
                    tg_chat=tg_message.chat.id,
                    tg_id=tg_message.message_id
                )

            photo_attachments = [attach for attach in attaches_scheme if attach and attach['type'] == 'photo']

            if len(photo_attachments) > 1:
                media = MediaGroup()
                for photo in photo_attachments:
                    media.attach_photo(photo['content'])
                tg_messages = await tgsend(bot.send_media_group, to_tg_chat, media, reply_to_message_id=main_message,
                                           disable_notification=disable_notify)
                for tg_message in tg_messages:
                    Message.objects.create(
                        vk_chat=vk_chat_id,
                        vk_id=vk_msg_id,
                        tg_chat=tg_message.chat.id,
                        tg_id=tg_message.message_id
                    )

            for attachment in attaches_scheme:
                if attachment:
                    if attachment['type'] == 'text':
                        await bot.send_chat_action(to_tg_chat, ChatActions.TYPING)
                        tg_message = await tgsend(bot.send_message, to_tg_chat, attachment['content'],
                                                  parse_mode=ParseMode.HTML, reply_to_message_id=main_message,
                                                  disable_notification=disable_notify)
                    elif attachment['type'] == 'photo' and len(photo_attachments) == 1:
                        await bot.send_chat_action(to_tg_chat, ChatActions.UPLOAD_PHOTO)
                        tg_message = await  tgsend(bot.send_photo, to_tg_chat, attachment['content'],
                                                   reply_to_message_id=main_message,
                                                   disable_notification=disable_notify)
                    elif attachment['type'] == 'document':
                        await bot.send_chat_action(to_tg_chat, ChatActions.UPLOAD_DOCUMENT)
                        tg_message = await tgsend(bot.send_document, to_tg_chat,
                                                  attachment.get('content', '') or attachment.get('url'),
                                                  reply_to_message_id=main_message, disable_notification=disable_notify)
                        if 'content' in attachment:
                            attachment['content'].close()
                            os.remove(os.path.join(attachment['temp_path'],
                                                   attachment['file_name'] + attachment['custom_ext']))
                    elif attachment['type'] == 'video':
                        await bot.send_chat_action(to_tg_chat, ChatActions.UPLOAD_VIDEO)
                        tg_message = await tgsend(bot.send_video, to_tg_chat, attachment['content'],
                                                  reply_to_message_id=main_message, disable_notification=disable_notify)
                    elif attachment['type'] == 'sticker':
                        await bot.send_chat_action(to_tg_chat, ChatActions.TYPING)
                        tg_message = await tgsend(bot.send_sticker, to_tg_chat, attachment['content'],
                                                  reply_to_message_id=main_message, disable_notification=disable_notify)
                    elif attachment['type'] == 'location':
                        await bot.send_chat_action(to_tg_chat, ChatActions.FIND_LOCATION)
                        tg_message = await tgsend(bot.send_location, to_tg_chat, *attachment['content'],
                                                  reply_to_message_id=main_message, disable_notification=disable_notify)
                    elif attachment['type'] == 'venue':
                        await bot.send_chat_action(to_tg_chat, ChatActions.FIND_LOCATION)
                        tg_message = await tgsend(bot.send_venue, to_tg_chat, *attachment['content'],
                                                  reply_to_message_id=main_message, disable_notification=disable_notify)

                    Message.objects.create(
                        vk_chat=vk_chat_id,
                        vk_id=vk_msg_id,
                        tg_chat=tg_message.chat.id,
                        tg_id=tg_message.message_id
                    )
            if vk_msg.get('fwd_messages'):
                await bot.send_chat_action(to_tg_chat, ChatActions.TYPING)
                fwd_ptr = tg_message = await bot.send_message(vkuser.owner.uid, header + '<i>Пересланные сообщения</i>',
                                                              parse_mode=ParseMode.HTML,
                                                              reply_to_message_id=main_message,
                                                              disable_notification=disable_notify)
                Message.objects.create(
                    vk_chat=vk_chat_id,
                    vk_id=vk_msg_id,
                    tg_chat=tg_message.chat.id,
                    tg_id=tg_message.message_id
                )

                for fwd_message in vk_msg['fwd_messages']:
                    await process_message(msg, token=token, is_multichat=is_multichat, vk_chat_id=vk_chat_id,
                                          user_id=fwd_message['user_id'],
                                          forward_settings=forward_settings, vk_msg_id=vk_msg_id, vkchat=vkchat,
                                          full_msg={'items': [fwd_message]}, forwarded=True,
                                          main_message=fwd_ptr.message_id, known_users=known_users)


async def get_name(identifier, api):
    if identifier > 0:
        peer = await api('users.get', user_ids=identifier)
        first_name = peer[0]['first_name']
        last_name = peer[0]['last_name'] or ''
    else:
        peer = await api('groups.getById', group_ids=abs(identifier))
        first_name = peer[0]['name']
        last_name = ''
        peer[0]['id'] = -peer[0]['id']
    return peer[0]['id'], first_name, last_name


async def tgsend(method, *args, **kwargs):
    try:
        tg_message = await method(*args, **kwargs)
        return tg_message
    except RetryAfter as e:
        asyncio.sleep(e.timeout)
        tgsend(method, *args, **kwargs)
    except Exception:
        log.exception(msg='Error in message sending', exc_info=True)


async def process_event(msg):
    pass


async def process_attachment(attachment):
    atype = attachment.get('type')
    if atype == 'photo':
        photo_url = attachment[atype][await get_max_photo(attachment[atype])]
        return {'content': photo_url, 'type': 'photo'}

    elif atype == 'audio':
        pass

    elif atype == 'video':
        title = attachment[atype]['title']
        owner_id = attachment[atype]['owner_id']
        video_id = attachment[atype]['id']
        access_key = attachment[atype].get('access_key')
        video_url = f'https://vk.com/video{owner_id}_{video_id}' + f'_{access_key}' if access_key else ''
        return {'content': f'<i>🎥 Видеозапись</i> <a href="{video_url}">{title}</a>', 'type': 'text'}

    elif atype == 'doc':
        ext = attachment[atype]['ext']
        if ext == 'gif':
            size = attachment[atype]['preview']['video']['file_size']
            gif_url = attachment[atype]['url'] + '&mp4=1'
            if size > MAX_FILE_SIZE:
                return {'content': f'<a href="{gif_url}">GIF</a>', 'type': 'text'}
            return {'content': gif_url, 'type': 'document'}
        elif 'preview' in attachment[atype] and attachment[atype]['preview'].get('graffiti'):
            graffiti_url = attachment[atype]['preview']['photo']['sizes'][-1]['src']
            with aiohttp.ClientSession() as session:
                img = await (await session.request('GET', graffiti_url)).read()
            imgdata = Image.open(io.BytesIO(img))
            webp = io.BytesIO()
            imgdata.save(webp, format='WebP')
            file_bytes = webp.getvalue()
            return {'content': file_bytes, 'type': 'sticker'}
        else:
            size = attachment[atype]['size']
            doc_url = attachment[atype]['url']  # + f'&{ext}=1'
            docname = attachment[atype].get('title', 'Документ')
            if size > MAX_FILE_SIZE:
                return {'content': f'<a href="{doc_url}">📄 {docname}</a>', 'type': 'text'}
            content = await get_content(doc_url, docname)
            # supported_exts = ['zip', 'pdf', 'jpg', 'png', 'doc', 'docx']
            if 'content' in content:
                content['type'] = 'document'
                return content
            else:
                return {'content': f'<a href="{doc_url}">📄 {content["docname"]}</a>', 'type': 'text'}

    elif atype == 'sticker':
        sticker_url = attachment[atype][await get_max_photo(attachment[atype])]
        with aiohttp.ClientSession() as session:
            img = await (await session.request('GET', sticker_url)).read()
        imgdata = Image.open(io.BytesIO(img))
        webp = io.BytesIO()
        imgdata.save(webp, format='WebP')
        file_bytes = webp.getvalue()
        return {'content': file_bytes, 'type': 'sticker'}

    elif atype == 'gift':
        gift_url = attachment[atype][await get_max_photo(attachment[atype], 'thumb')]
        return {'content': f'<a href="{gift_url}">Подарок</a>', 'type': 'text'}
    elif atype == 'link':
        link_url = attachment[atype]['url']
        link_name = attachment[atype].get('title', '')
        if link_name:
            link_name += '\n'
        link_name += attachment[atype].get('description', '')
        if not link_name:
            if 'button' in attachment[atype] and 'action' in attachment[atype]['button']:
                link_name = attachment[atype]['button']['action'].get('title', '')
                if not link_name:
                    link_name = 'Прикрепленная ссылка'
        elif len(link_name) > 200:
            link_name = link_name[:200] + '...'
        photo_content = ''
        if 'photo' in attachment[atype]:
            photo_url = attachment[atype]['photo'][await get_max_photo(attachment[atype]['photo'])]
            photo_name = attachment[atype]['photo'].get('text', '&#8203;')
            if not photo_name:
                photo_name = '&#8203;'
            photo_content = f'<a href="{photo_url}">{photo_name}</a>'
            if photo_name != '&#8203;':
                photo_content += '\n'
        return {'content': photo_content + f'<a href="{link_url}">🔗 {link_name}</a>', 'type': 'text'}

    elif atype == 'market':
        market_url = f'https://vk.com/market{attachment[atype]["owner_id"]}_{attachment[atype]["id"]}'
        photo_content = ''
        if attachment[atype].get('thumb_photo'):
            photo_content = f'<a href="{attachment[atype]["thumb_photo"]}">&#8203;</a>'
        title = f'<a href="{market_url}">{attachment[atype].get("title", "") or "🛍 Товар"}</a>'
        description = attachment[atype].get('description', '')
        if description:
            description = f'\n<i>{description}</i>'
        price = ''
        if attachment[atype].get('price'):
            price = f'\n<b>{attachment[atype]["price"]["text"]}</b>'

        return {'content': photo_content + title + description + price + '\n', 'type': 'text'}

    elif atype == 'market_album':
        market_album_url = f'https://vk.com/market{attachment[atype]["owner_id"]}?section=album_{attachment[atype]["id"]}'
        photo_content = ''
        if attachment[atype].get('photo'):
            photo_url = attachment[atype]['photo'][await get_max_photo(attachment[atype])]
            photo_content = f'<a href="{photo_url or ""}">&#8203;</a>'
        title = f'<a href="{market_album_url}">{attachment[atype].get("title", "") or "🛒 Подборка Товаров"}</a>'
        count = f'\n<i>Число товаров:</i> {attachment[atype]["count"]}'
        return {'content': photo_content + title + count + '\n', 'type': 'text'}

    elif atype == 'wall':
        owner_id = attachment[atype].get('owner_id', '') or attachment[atype].get('from_id', '') or attachment[
            atype].get('to_id', '')
        post_id = attachment[atype]['id']
        # access_key = attachment[atype].get('access_key')
        wall_url = f'https://vk.com/wall{owner_id}_{post_id}'  # + f'_{access_key}' if access_key else ''
        return {'content': f'<a href="{wall_url}">📰 Запись на стене</a>', 'type': 'text'}

    elif atype == 'wall_reply':
        owner_id = attachment[atype].get('owner_id', '') or attachment[atype].get('from_id', '') or attachment[
            atype].get('to_id', '')
        post_id = attachment[atype]['post_id']
        wall_reply_url = f'https://vk.com/wall{owner_id}_{post_id}'
        reply_text = attachment[atype].get('text', '')
        if reply_text:
            reply_text = '\n' + reply_text
        return {'content': f'<a href="{wall_reply_url}">💬 Комментарий к записи</a>{reply_text}', 'type': 'text'}


async def vk_polling(vkuser: VkUser):
    while True:
        try:
            session = VkSession(access_token=vkuser.token, driver=await get_driver(vkuser.token))
            session.API_VERSION = API_VERSION
            log.warning('Starting polling for: id ' + str(vkuser.pk))
            api = API(session)
            lp = LongPoll(session, mode=10, version=4)
            while VkUser.objects.filter(token=vkuser.token, is_polling=True).exists():
                data = await lp.wait()
                log.debug('Longpoll: ' + str(data))
                if data['updates']:
                    for update in data['updates']:
                        await process_longpoll_event(api, update)
            break
        except VkLongPollError:
            log.error('Longpoll error! {}'.format(vkuser.pk))
            asyncio.sleep(5)
        except VkAuthError:
            log.error('Auth Error! {}'.format(vkuser.pk))
            vkuser.is_polling = False
            vkuser.save()
            break
        except CancelledError:
            log.warning('Stopped polling for: id ' + str(vkuser.pk))
            break
        except Exception:
            log.exception(msg='Error in longpolling', exc_info=True)
            asyncio.sleep(5)


def vk_polling_tasks():
    tasks = [{'token': vkuser.token, 'task': asyncio.ensure_future(vk_polling(vkuser))} for vkuser in
             VkUser.objects.filter(token__isnull=False, is_polling=True)]
    log.warning('Starting Vk polling')
    return tasks
