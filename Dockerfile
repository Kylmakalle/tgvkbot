FROM python:3.6 AS builder
RUN apt-get update && apt-get install -y gcc libjpeg-dev libpq-dev \
    python3-dev python3-setuptools libjpeg62-turbo-dev zlib1g-dev
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.6-slim
RUN apt-get update && apt-get install -y libpq5 \
    python3-psycopg2 libjpeg-dev libopenjp2-7 libtiff5-dev libwebp-dev  \ 
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
ENTRYPOINT bash -c "python manage.py makemigrations data && python manage.py migrate data && python telegram.py"