sudo true

if [ ! `which docker` ]; then
		echo "🔨 Устанавливаем docker..."
		# Alternatively you can use the official docker install script
		wget -qO- https://get.docker.com/ | sh
fi

if [ ! `which docker-compose` ]; then
		echo "🔨 Устанавливаем docker-compose..."
		# Install docker-compose
		COMPOSE_VERSION=`git ls-remote https://github.com/docker/compose | grep refs/tags | grep -oE "[0-9]+\.[0-9][0-9]+\.[0-9]+$" | sort --version-sort | tail -n 1`
		sudo sh -c "curl -L https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-`uname -s`-`uname -m` > /usr/local/bin/docker-compose"
		sudo chmod +x /usr/local/bin/docker-compose
		sudo sh -c "curl -L https://raw.githubusercontent.com/docker/compose/${COMPOSE_VERSION}/contrib/completion/bash/docker-compose > /etc/bash_completion.d/docker-compose"
fi


echo "⚙️ Настраиваем переменные окружения..."
python3 set_env.py

if [ ! "$(docker ps -a | grep <name>)" ]; then
  echo "🔄 Поднимаем систему обновлений..."
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
fi

echo "🚀 Запускаем бота..."
docker-compose up -d

echo "✅ Готово"

