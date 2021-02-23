from config import API_VERSION, VK_APP_ID
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from urllib.parse import urlencode

ENV_FILE_TEMPLATE = """
POSTGRES_DB=tgvkbot
POSTGRES_PASSWORD=postgres
BOT_TOKEN=%(tg_token)s
VK_APP_ID=%(vk_app_id)s
"""


def check_token(token):
    response = urlopen("https://api.telegram.org/bot{token}/{method}".format(token=token, method='getMe'))
    if response.code == 200:
        return True
    else:
        raise HTTPError


def get_auth_page(app_id):
    AUTH_URL = 'https://oauth.vk.com/authorize'
    params = {'client_id': app_id,
              'redirect_uri': 'https://oauth.vk.com/blank.html',
              'display': 'mobile',
              'response_type': 'token',
              'v': API_VERSION
              }
    post_args = urlencode(params).encode('UTF-8')
    request = Request(AUTH_URL, post_args)
    response = urlopen(request)
    if response.code == 200:
        return True
    else:
        raise HTTPError


def set_env():
    while True:
        tg_token = input('Токен Telegram бота: ')
        tg_token = tg_token.strip()
        try:
            check_token(tg_token)
            break
        except HTTPError:
            print('❌ Токен бота неверный или нерабочий, попробуйте снова!')

    while True:
        vk_app_id = input('VK APP ID: ')
        vk_app_id = vk_app_id.strip()
        if vk_app_id:
            try:
                get_auth_page(vk_app_id)
                break
            except HTTPError:
                print('❌ VK APP ID неверный, попробуйте снова!')

    with open('env_file', 'w') as env_file:
        env_file.write(ENV_FILE_TEMPLATE % {'tg_token': tg_token, 'vk_app_id': vk_app_id or VK_APP_ID})

    print('✅ Успешно!')


if __name__ == '__main__':
    set_env()
