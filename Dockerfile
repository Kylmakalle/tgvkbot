FROM python:3.6-slim AS builder
RUN apt-get update && apt-get install -y gcc
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.6-slim
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
ENTRYPOINT bash -c "python manage.py makemigrations data && python manage.py migrate data && python telegram.py"