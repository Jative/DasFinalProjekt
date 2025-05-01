import threading
from time import sleep
from random import random

import IoT_devices
from DBMS_worker import DBMS_worker


def main() -> None:
    """
    Основная функция запуска системы управления умной теплицей.
    
    Логика работы:
    1. Инициализирует подключение к базе данных
    2. Создает список IoT-устройств
    3. Запускает каждое устройство в отдельном потоке
    4. Добавляет случайные задержки между запусками для имитации реальной работы
    
    Примеры устройств:
    - Датчики температуры/влажности
    - Датчики освещенности
    - Исполнительные устройства (обогреватели, увлажнители, лампы)
    
    Note:
    - Для работы требуется запущенный MySQL сервер с указанными учетными данными
    - Все устройства должны быть определены в модуле IoT_devices
    """
    host = "localhost"
    user = "root"
    password = "123"
    db_name = "GreenHouseIoT"
    db_worker = DBMS_worker(host, user, password, db_name)

    device_list = [
        IoT_devices.TermometerAndHumiditySensor1(db_worker),
        IoT_devices.TermometerAndHumiditySensor2(db_worker),
        IoT_devices.BrightnessSensor1(db_worker),
        IoT_devices.BrightnessSensor2(db_worker),
        IoT_devices.Heater1(db_worker),
        IoT_devices.Heater2(db_worker),
        IoT_devices.Humiditator1(db_worker),
        IoT_devices.Humiditator2(db_worker),
        IoT_devices.Lamp1(db_worker),
        IoT_devices.Lamp2(db_worker),
    ]
    
    for device in device_list:
        t = threading.Thread(target=device.start)
        t.start()
        sleep(random())


if __name__ == "__main__":
    main()