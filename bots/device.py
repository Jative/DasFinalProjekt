import socket
import json
import datetime
from time import sleep

from DBMS_worker import DBMS_worker
from logic import get_uuid, set_uuid
from encryption import encrypt, decrypt
from config import (
    RECONNECT_DELAY,
    SERVER_ADDR,
    SERVER_PORT,
    NO_UUID,
    PASSWORD,
    SEND_STATE_DELAY,
)


class Device:
    def __init__(self, db_worker: DBMS_worker):
        """
        Инициализирует устройство с подключением к БД и базовыми параметрами.

        Args:
            db_worker (DBMS_worker): Объект для работы с базой данных
        """
        self.sock = socket.socket()
        self.uuid = get_uuid(self.uuid_filename)
        self.db_worker = db_worker
        self.delay = SEND_STATE_DELAY
        self.state = 0


    def print(self, *args, **kwargs) -> None:
        """
        Выводит сообщение с временной меткой, UUID и именем устройства.

        Args:
            *args: Аргументы для стандартной функции print
            **kwargs: Именованные аргументы для стандартной функции print
        """
        print(
            f"({datetime.datetime.now().strftime('%H:%M:%S')})",
            f"{self.uuid} [{self.IoT_name}]: ",
            end="",
        )
        print(*args, **kwargs)


    def receive_data(self) -> str:
        """
        Принимает и расшифровывает данные от сервера.

        Returns:
            str: Расшифрованная строка с данными (первый элемент из массива)
        """
        data_length = int.from_bytes(self.sock.recv(4), "big")
        data = self.sock.recv(data_length)
        return json.loads(decrypt(data))[0]


    def send_data(self, data: list) -> None:
        """
        Шифрует и отправляет данные на сервер.

        Args:
            data (list): Список данных для отправки
        """
        encoded_data = encrypt(json.dumps(data))
        self.sock.sendall(len(encoded_data).to_bytes(4, "big"))
        self.sock.sendall(encoded_data)


    def login(self) -> None:
        """
        Выполняет процесс аутентификации на сервере:
        1. Отправляет пароль
        2. Отправляет имя устройства
        3. Отправляет/получает UUID
        4. Сохраняет новый UUID при необходимости
        """
        self.send_data([PASSWORD])
        self.send_data([self.IoT_name])
        self.send_data([self.uuid])
        if self.uuid == NO_UUID:
            self.uuid = self.receive_data()
            set_uuid(self.uuid_filename, self.uuid)


    def start(self) -> None:
        """
        Основной цикл работы устройства:
        1. Устанавливает соединение с сервером
        2. Выполняет аутентификацию
        3. Запускает рабочий цикл
        4. Обрабатывает ошибки соединения
        5. Выполняет повторное подключение при обрыве
        """
        while True:
            try:
                self.sock.connect((SERVER_ADDR, SERVER_PORT))
                self.login()
                while True:
                    self.work()
            except (ConnectionRefusedError, TimeoutError):
                self.print(
                    f"Подключение к '{SERVER_ADDR}:{SERVER_PORT}' "
                    f"не удалось с устройства '{self.IoT_name}'"
                )
                sleep(RECONNECT_DELAY)
            except Exception as e:
                print(e)
                self.print(
                    "Непредвиденная ошибка логики "
                    f"устройства '{self.IoT_name}'"
                )
            finally:
                self.sock.close()
                self.sock = socket.socket()


    def work(self) -> None:
        """
        Рабочий цикл устройства:
        1. Формирует данные для отправки
        2. Получает текущие показатели из БД
        3. Отправляет данные на сервер
        4. Обрабатывает ответ сервера
        5. Выполняет задержку между операциями
        """
        data_to_send = [self.state]
        for indicator in self.indicators:
            data_to_send.append(
                self.db_worker.get_value(
                    self.sector,
                    indicator,
                )
            )
        
        self.print("->", *data_to_send)
        self.send_data(data_to_send)
        if server_answer := self.receive_data():
            self.interpret(server_answer)
        else:
            sleep(self.delay)


    def interpret(self, command: str) -> None:
        """
        Интерпретирует и выполняет команды от сервера.

        Args:
            command (str): Команда в формате "задержка~значение"
            
        Логика выполнения:
        - Парсит команду на задержку и целевое значение
        - При ненулевом значении изменяет состояние устройства
        - Выполняет инкрементальное изменение значений в БД
        - Регулирует временные интервалы выполнения операций
        """
        self.print("<-", command)
        delay, value = tuple(map(int, command.split("~")))
        if self.to_change and value != 0:
            self.state = 1
            for i in range(delay):
                if (i+1) % (delay // value) == 0:
                    changed = self.db_worker.change_value(
                        self.sector,
                        self.to_change,
                        1 if value > 0 else -1
                    )
                    if changed:
                        self.print("Изменил на 1")
                    else:
                        self.print("Не удалось изменить значение")
                sleep(1)
        else:
            self.state = 0
            sleep(delay)