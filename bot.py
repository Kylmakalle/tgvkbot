import io
import logging
import re
import tempfile
import ujson

import aiohttp
import django.conf
import wget
from PIL import Image
from aiogram import Bot
from aiogram.dispatcher import Dispatcher
from aiogram.types import ParseMode, MediaGroup, InlineKeyboardMarkup, InlineKeyboardButton, ChatActions
from aiogram.utils.exceptions import *
from aiogram.utils.parts import safe_split_text, split_text, MAX_MESSAGE_LENGTH
from aiogram.utils import context
from aiovk import TokenSession, API
from aiovk.drivers import HttpDriver
from aiovk.exceptions import *
from aiovk.mixins import LimitRateDriverMixin

from config import *

django.conf.ENVIRONMENT_VARIABLE = SETTINGS_VAR
os.environ.setdefault(SETTINGS_VAR, "settings")
# Ensure settings are read
from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

from data.models import *


class VkSession(TokenSession):
    API_VERSION = API_VERSION


class RateLimitedDriver(LimitRateDriverMixin, HttpDriver):
    requests_per_period = 1
    period = 0.4


DRIVERS = {}


async def get_driver(vk_token=None):
    if vk_token:
        if vk_token in DRIVERS:
            return DRIVERS[vk_token]
        else:
            new_driver = RateLimitedDriver()
            DRIVERS[vk_token] = new_driver
            return new_driver
    else:
        return RateLimitedDriver()


async def get_vk_chat(cid):
    return VkChat.objects.get_or_create(cid=cid)


max_photo_re = re.compile('photo_([0-9]*)')


async def get_max_photo(obj, keyword='photo'):
    maxarr = []
    for k, v in obj.items():
        m = max_photo_re.match(k)
        if m:
            maxarr.append(int(m.group(1)))
    return keyword + '_' + str(max(maxarr))


async def get_content(url, docname='tgvkbot.document', chrome_headers=True, rewrite_name=False,
                      custom_ext=''):
    try:
        with aiohttp.ClientSession(headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36'} if chrome_headers else {}) as session:
            r = await session.request('GET', url)
            direct_url = str(r.url)
            tempdir = tempfile.gettempdir()
            filename_options = {'out': docname} if rewrite_name else {'default': docname}
            if direct_url != url:
                r.release()
                c = await session.request('GET', direct_url)
                file = wget.detect_filename(direct_url, headers=dict(c.headers), **filename_options)
                temppath = os.path.join(tempdir, file + custom_ext)
                with open(temppath, 'wb') as f:
                    f.write(await c.read())
            else:
                file = wget.detect_filename(direct_url, headers=dict(r.headers), **filename_options)
                temppath = os.path.join(tempdir, file + custom_ext)
                with open(temppath, 'wb') as f:
                    f.write(await r.read())
        content = open(temppath, 'rb')
        return {'content': content, 'file_name': file, 'custom_ext': custom_ext, 'temp_path': tempdir}
    except Exception:
        return {'url': url, 'docname': docname}


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.loop.set_task_factory(context.task_factory)
