import os

DATABASE_USER = os.environ.get('POSTGRES_USER', 'postgres')
DATABASE_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'postgres')
DATABASE_HOST = os.environ.get('DATABASE_HOST', 'db')
DATABASE_PORT = os.environ.get('DATABASE_PORT', '5432')
DATABASE_NAME = os.environ.get('POSTGRES_DB', 'tgvkbot')

VK_APP_ID = os.environ.get('VK_APP_ID', '2685278')  # Kate mobile

AUDIO_URL = os.environ.get('AUDIO_URL', '')
AUDIO_ACCESS_URL = os.environ.get('AUDIO_ACCESS_URL',
                                  '')
TOKEN_REFRESH_URL = os.environ.get('TOKEN_REFRESH_URL', '')
AUDIO_SEARCH_URL = os.environ.get('AUDIO_SEARCH_URL', '')
AUDIO_PROXY_URL = os.environ.get('AUDIO_PROXY_URL', '')
AUDIO_HEADERS = {
    'user-agent': 'KateMobileAndroid/52.1 lite-445 (Android 4.4.2; SDK 19; x86; unknown Android SDK built for x86; en)'}

CHROME_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36'}
BOT_TOKEN = os.environ.get('BOT_TOKEN')

SETTINGS_VAR = os.environ.get('SETTINGS_VAR', 'DJANGO_TGVKBOT_SETTINGS_MODULE')

MAX_FILE_SIZE = os.environ.get('MAX_FILE_SIZE', 52428800)

API_VERSION = os.environ.get('API_VERSION', '5.124')
AUDIO_API_VERSION = os.environ.get('API_VERSION', '5.78')

# https://www.miniwebtool.com/django-secret-key-generator/
# Возможно достаточно заглушки в стиле 'tgvkbot-super-secret-key(nope)'
SECRET_KEY = os.environ.get('SECRET_KEY', '!jh4wm=%s%l&jv7-lru6hg)mq2pk&rd@i*s0*c!v!zv01cf9iw')

SENTRY_URL = os.environ.get('SENTRY_URL', None)

if SENTRY_URL:
    import sentry_sdk

    sentry_sdk.init(SENTRY_URL)