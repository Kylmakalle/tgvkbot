FROM python:3.6-alpine
ENV PYTHONUNBUFFERED 1
RUN mkdir /src
WORKDIR /src
COPY requirements.txt /src/
RUN apk update && apk add postgresql-dev gcc musl-dev jpeg-dev zlib-dev
RUN pip install -r requirements.txt
COPY . /src