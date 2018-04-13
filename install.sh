#!/usr/bin/env bash
sudo apt-get update && sudo apt-get upgrade && \
sudo apt-get install docker.io -y && \
sudo usermod -aG docker $(whoami) && \
sudo curl -L https://github.com/docker/compose/releases/download/1.20.1/docker-compose-`uname -s`-`uname -m` -o /usr/local/bin/docker-compose && \
sudo chmod +x /usr/local/bin/docker-compose && \
python3 set_env.py && \
python3 obtaincert.py && \
sudo docker-compose build && \
sudo docker-compose up -d