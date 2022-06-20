from config import *

import dj_database_url

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


DATABASES = {}

if DATABASE_URL:
    # Reads string from DATABASE_URL env by default
    DATABASES['default'] = dj_database_url.config()
else:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': DATABASE_NAME,
        'USER': DATABASE_USER,
        'PASSWORD': DATABASE_PASSWORD,
        'HOST': DATABASE_HOST,
        'PORT': DATABASE_PORT
    }

INSTALLED_APPS = (
    'data',
)
