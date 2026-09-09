FROM python:3.6-slim AS builder
RUN printf '%s\n' \
    'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20211220T000000Z bullseye main' \
    'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/20211220T000000Z bullseye-security main' \
    > /etc/apt/sources.list
RUN apt-get update && apt-get install -y gcc
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.6-slim
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
ENTRYPOINT bash -c "python manage.py makemigrations data && python manage.py migrate data && python telegram.py"
