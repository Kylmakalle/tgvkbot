FROM python:3.6-slim
ENV PYTHONUNBUFFERED 1
WORKDIR /src
COPY requirements.txt /src/
RUN apt-get update && \
    apt-get install -y gcc && \
    pip install -r requirements.txt && \
    apt-get remove -y --auto-remove gcc && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
COPY . /src
ENTRYPOINT bash -c "python manage.py makemigrations data && python manage.py migrate data && python telegram.py"