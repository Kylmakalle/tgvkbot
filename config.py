import os


def get_external_host():
    import urllib.request
    host = urllib.request.urlopen('https://api.ipify.org').read().decode('utf8')
    return host


HOST = ''

WEBHOOK_HOST = os.environ.get('WEBHOOK_HOST', HOST or get_external_host())
WEBHOOK_PORT = os.environ.get('WEBHOOK_PORT', 443)
WEBHOOK_URL_PATH = os.environ.get('WEBHOOK_URL_PATH', '/tgwebhook')

WEBHOOK_URL = f"https://{WEBHOOK_HOST}:{WEBHOOK_PORT}{WEBHOOK_URL_PATH}"

WEBAPP_HOST = os.environ.get('WEBAPP_HOST', 'localhost')
WEBAPP_PORT = os.environ.get('WEBAPP_PORT', 3001)

DATABASE_USER = os.environ.get('DATABASE_USER', 'postgres')
DATABASE_PASSWORD = os.environ.get('DATABASE_PASSWORD', 'postgres')
DATABASE_HOST = os.environ.get('DATABASE_HOST', 'localhost')
DATABASE_PORT = os.environ.get('DATABASE_PORT', '5432')
DATABASE_NAME = os.environ.get('DATABASE_NAME', 'tgvkbot')

VK_APP_ID = os.environ.get('VK_APP_ID', 1234567)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '123456789:AAABBBCCCDDDEEEFFFGGGHHHIIIJJJKKKLL')

SETTINGS_VAR = os.environ.get('SETTINGS_VAR', 'DJANGO_TGVKBOT_SETTINGS_MODULE')

MAX_FILE_SIZE = os.environ.get('MAX_FILE_SIZE', 52428800)

API_VERSION = os.environ.get('API_VERSION', '5.73')

# https://www.miniwebtool.com/django-secret-key-generator/
# Возможно достаточно заглушки в стиле 'tgvkbot-super-secret-key(nope)'
SECRET_KEY = os.environ.get('SECRET_KEY', '!jh4wm=%s%l&jv7-lru6hg)mq2pk&rd@i*s0*c!v!zv01cf9iw')
