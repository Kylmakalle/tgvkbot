#!/usr/bin/env bash
ASKED_FOR_SUDO=""

if [ ! $(which docker) ]; then
  echo "🔑 Пароль sudo потребуется для установки Docker"
  sudo true
  ASKED_FOR_SUDO="1"

  echo "🔨 Устанавливаем docker..."
  curl -fsSL https://get.docker.com/ | sh
  user="$(id -un 2>/dev/null || true)"
  sudo groupadd docker
  sudo usermod -aG docker $user
else
  echo "👌 Docker уже установлен"
fi

if [ ! $(which docker-compose) ]; then
  if [ ! $ASKED_FOR_SUDO ]; then
    echo "🔑 Пароль sudo потребуется для установки docker-compose"
    sudo true
    ASKED_FOR_SUDO="1"
  fi
  echo "🔨 Устанавливаем docker-compose..."
  # Install docker-compose
  COMPOSE_VERSION=$(git ls-remote https://github.com/docker/compose | grep refs/tags | grep -oE "[0-9]+\.[0-9][0-9]+\.[0-9]+$" | sort --version-sort | tail -n 1)
  sudo sh -c "curl -L https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m) > /usr/local/bin/docker-compose"
  sudo chmod +x /usr/local/bin/docker-compose
  sudo sh -c "curl -L https://raw.githubusercontent.com/docker/compose/${COMPOSE_VERSION}/contrib/completion/bash/docker-compose > /etc/bash_completion.d/docker-compose"
else
  echo "👌 Docker-compose уже установлен"
fi

echo "⚙️ Настраиваем переменные окружения..."
python3 setenv.py

if [ ! "$(docker ps -a | grep watchtower)" ]; then
  echo "🔄 Поднимаем систему обновлений watchtower..."
  docker run -d \
    --name watchtower \
    --restart always \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -e TZ='Europe/Moscow' \
    -e WATCHTOWER_CLEANUP='true' \
    -e WATCHTOWER_INCLUDE_STOPPED='true' \
    -e WATCHTOWER_MONITOR_ONLY='false' \
    -e WATCHTOWER_LABEL_ENABLE='true' \
    containrrr/watchtower:latest
else
  echo "👌 Апдейтер watchtower уже запущен"
fi

# Нужно убедиться, что бот встанет
set -e

echo "🚀 Запускаем бота..."
docker-compose up -d

echo "✅ Готово"
