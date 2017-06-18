import vk
import time


class VkPolling:
    def __init__(self):
        self._running = True

    def terminate(self):
        self._running = False

    def run(self, vk_user, bot, chat_id):
        while self._running:
            try:
                messages = vk_user.get_new_messages()
                if messages:
                    for m in messages:
                        bot.send_message(chat_id, m, parse_mode='HTML')
            except Exception as e:
                print('Error: {}'.format(e))
            for i in range(35):
                if self._running:
                    time.sleep(0.1)
                else:
                    break


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
            print(msgs)
            messages = msgs[1:]
            for m in messages:
                if not m['out'] and m['body']:
                    if 'chat_id' in m:
                        user = api.users.get(user_ids=m["uid"], fields=[])[0]
                        data = '<a href="x{}.{}.{}">&#8203;</a><b>{} {} @ {}:</b>\n{}'.format(
                            m["uid"], m['chat_id'], m['push_settings']['sound'], user["first_name"],
                            user["last_name"], m['title'], m["body"].replace('<br>', '\n'))
                        res.append(data)
                    else:
                        user = api.users.get(user_ids=m["uid"], fields=[])[0]
                        data = '<a href="x{}.0">&#8203;</a><b>{} {}:</b>\n{}'.format(
                            m["uid"], user["first_name"], user["last_name"], m["body"].replace('<br>', '\n'))
                        res.append(data)
        return res


def get_session(token):
    return vk.Session(access_token=token)


def get_tses(session):
    api = vk.API(session)

    ts = api.messages.getLongPollServer(need_pts=1)
    return ts['ts'], ts['pts']
