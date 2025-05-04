#!/bin/bash

if ! systemctl is-active --quiet mariadb; then
    echo "MariaDB не запущена. Запускаем службу..."
    sudo systemctl start mariadb
    if systemctl is-active --quiet mariadb; then
        echo "MariaDB успешно запущена"
    else
        echo "Ошибка! Не удалось запустить MariaDB" >&2
        exit 1
    fi
else
    echo "MariaDB уже работает"
fi

konsole --noclose -e "bash -c 'source ./venv/bin/activate && python ./servers/main-server/main.py; exec bash'" &
konsole --noclose -e "bash -c 'source ./venv/bin/activate && python ./servers/web-server/app.py; exec bash'" &
konsole --noclose -e "bash -c 'source ./venv/bin/activate && python ./servers/IoT-server/main.py; exec bash'" &
sleep 1
konsole --noclose -e "bash -c 'source ./venv/bin/activate && python ./bots/main.py; exec bash'" &

exit
