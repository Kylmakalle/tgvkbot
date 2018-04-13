FROM python:3.6
# MAINTAINER Sergey (@Kylmakalle) <iceman9831@gmail.com>

ENV PYTHONUNBUFFERED 1
RUN mkdir /src
WORKDIR /src
COPY requirements.txt /src/
RUN pip install -r requirements.txt
COPY . /src


