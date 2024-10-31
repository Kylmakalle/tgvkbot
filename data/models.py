import asyncio

from django.db import models
from django.db.models.query import QuerySet


class AsyncManager(models.Manager):
    """ A model manager which uses the AsyncQuerySet. """

    async def get_query_set(self):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, AsyncQuerySet(self.model, using=self._db))


class AsyncQuerySet(QuerySet):
    """ A queryset which allows DB operations to be pre-triggered so that they run in the
        background while the application can continue doing other processing.
    """

    def __init__(self, *args, **kwargs):
        super(AsyncQuerySet, self).__init__(*args, **kwargs)


class TgUser(models.Model):
    objects = AsyncManager()

    # id пользователя на сервере Telegram
    uid = models.BigIntegerField(unique=True)

    # имя
    first_name = models.CharField(max_length=256)

    # фамилия
    last_name = models.CharField(
        max_length=256,
        null=True,
        default=None,
    )

    # username
    username = models.CharField(
        max_length=256,
        null=True,
        default=None,
    )

    BLOCKED = -1
    BASE = 0

    STATUSES = (
        (BLOCKED, 'Заблокирован'),
        (BASE, 'Базовый'),
    )

    status = models.IntegerField(
        choices=STATUSES,
        default=BASE
    )


class VkUser(models.Model):
    objects = AsyncManager()

    token = models.TextField(unique=True)
    is_polling = models.BooleanField(default=False)
    owner = models.ForeignKey(TgUser, on_delete=models.CASCADE)

    class Meta:
        indexes = [
            models.Index(fields=['token', 'is_polling'], name='idx_token_polling')
        ]


class VkChat(models.Model):
    objects = AsyncManager()

    cid = models.BigIntegerField(unique=True)


class TgChat(models.Model):
    objects = AsyncManager()

    cid = models.BigIntegerField(unique=True)


class Forward(models.Model):
    objects = AsyncManager()

    owner = models.ForeignKey(TgUser, on_delete=models.CASCADE)
    tgchat = models.ForeignKey(TgChat, on_delete=models.CASCADE)
    vkchat = models.ForeignKey(VkChat, on_delete=models.CASCADE)


class Message(models.Model):
    objects = AsyncManager()

    vk_chat = models.BigIntegerField()
    vk_id = models.BigIntegerField(null=True)
    tg_chat = models.BigIntegerField()
    tg_id = models.BigIntegerField()


class MessageMarkup(models.Model):
    objects = AsyncManager()

    message_id = models.BigIntegerField()

    chat_id = models.BigIntegerField()

    buttons = models.TextField(null=True, blank=True)
