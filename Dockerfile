FROM python:3.6-alpine
ENV PYTHONUNBUFFERED 1
WORKDIR /src
COPY requirements.txt /src/
RUN apk update && apk add postgresql-dev gcc musl-dev jpeg-dev zlib-dev libwebp-dev  && \
    pip install -r requirements.txt && \
    apk del musl-dev gcc && \
    rm -rf /var/cache/apk/*
COPY . /src
ENTRYPOINT sh -c "python manage.py makemigrations data && python manage.py migrate data && python telegram.py"