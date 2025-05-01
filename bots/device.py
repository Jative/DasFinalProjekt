import socket
import json
import datetime
from time import sleep
from typing import Optional

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
        Базовый класс для IoT-устройств умной теплицы.
        
        Args:
            db_worker (DBMS_worker): Объект для работы с базой данных
        """
        self.sock = socket.socket()
        self.uuid = get_uuid(self.uuid_filename)
        self.db_worker = db_worker
        self.state = 0
        self.IoT_name = self.__class__.__name__
        self.sector = 0
        self.to_change = None

    def print(self, *args, **kwargs) -> None:
        """
        Выводит форматированное сообщение с меткой времени и информацией об устройстве.
        """
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        print(f"({timestamp}) {self.uuid} [{self.IoT_name}]:", *args, **kwargs)

    def receive_data(self) -> Optional[dict]:
        """
        Принимает и расшифровывает данные от сервера.
        
        Returns:
            dict | None: Расшифрованные данные в виде словаря или None при ошибке
        """
        try:
            data_length = int.from_bytes(self.sock.recv(4), "big")
            encrypted_data = self.sock.recv(data_length)
            return json.loads(decrypt(encrypted_data))
        except (ConnectionResetError, json.JSONDecodeError) as e:
            self.print(f"Ошибка получения данных: {e}")
            return None

    def send_data(self, data: dict) -> bool:
        """
        Шифрует и отправляет данные на сервер.
        
        Args:
            data (dict): Данные для отправки в виде словаря
            
        Returns:
            bool: True если данные успешно отправлены
        """
        try:
            encrypted_data = encrypt(json.dumps(data))
            self.sock.sendall(len(encrypted_data).to_bytes(4, "big"))
            self.sock.sendall(encrypted_data)
            return True
        except (TypeError, BrokenPipeError) as e:
            self.print(f"Ошибка отправки данных: {e}")
            return False

    def login(self) -> bool:
        """
        Выполняет процесс аутентификации на сервере.
        
        Протокол аутентификации:
        1. Отправка пароля в формате {'password': str}
        2. Отправка метаданных устройства {'device_name': str, 'uuid': str}
        3. Получение подтверждения или нового UUID
        
        Returns:
            bool: True при успешной аутентификации
        """
        try:
            # Отправка пароля
            if not self.send_data({'password': PASSWORD}):
                return False

            # Отправка метаданных
            device_info = {
                'device_name': self.IoT_name,
                'uuid': self.uuid
            }
            if not self.send_data(device_info):
                return False

            # Обработка ответа сервера
            response = self.receive_data()
            if not response:
                return False

            if response.get('status') == 'registered':
                new_uuid = response.get('uuid')
                if new_uuid and new_uuid != self.uuid:
                    self.uuid = new_uuid
                    set_uuid(self.uuid_filename, self.uuid)
                    self.print(f"Получен новый UUID: {self.uuid}")

            return True
        except Exception as e:
            self.print(f"Ошибка аутентификации: {e}")
            return False

    def start(self) -> None:
        """
        Основной цикл работы устройства с обработкой переподключений.
        """
        while True:
            try:
                self.sock = socket.socket()
                self.sock.settimeout(10)
                self.sock.connect((SERVER_ADDR, SERVER_PORT))
                
                if not self.login():
                    continue
                
                self.work_loop()
                
            except (ConnectionRefusedError, TimeoutError):
                self.print(f"Не удалось подключиться к {SERVER_ADDR}:{SERVER_PORT}")
                sleep(RECONNECT_DELAY)
            except Exception as e:
                self.print(f"Критическая ошибка: {e}")
                sleep(RECONNECT_DELAY)
            finally:
                self.sock.close()

    def work_loop(self) -> None:
        """
        Основной рабочий цикл после успешного подключения.
        """
        while True:
            try:
                # Формирование данных для отправки
                sensor_data = {'state': self.state}
                for indicator in self.indicators:
                    sensor_data[indicator] = self.db_worker.get_value(
                        self.sector,
                        indicator
                    )
                
                self.print(f"Отправка данных: {sensor_data}")
                if not self.send_data(sensor_data):
                    break
                
                # Ожидание ответа от сервера
                response = self.receive_data()
                if not response:
                    break
                
                self.process_server_response(response)
                
            except socket.timeout:
                self.print("Таймаут соединения, переподключение...")
                break

    def process_server_response(self, response: dict) -> None:
        """
        Обрабатывает ответ от сервера с командами.
        
        Args:
            response (dict): Ответ сервера в формате:
                {
                    'delay': int, 
                    'commands': list[str]
                }
        """
        self.print(f"Получен ответ: {response}")
        
        delay = response.get('delay', SEND_STATE_DELAY)
        commands = response.get('commands', [])
        
        if commands:
            for command in commands:
                self.execute_command(command)
        else:
            sleep(delay)

    def execute_command(self, command: str) -> None:
        """
        Выполняет одну команду от сервера.
        
        Args:
            command (str): Команда в формате "команда~параметр"
        """
        try:
            cmd, param = command.split('~')
            self.print(f"Выполнение команды: {cmd} с параметром {param}")
            
            if cmd == "SET_DELAY":
                self.delay = int(param)
            elif self.to_change:
                self.process_control_command(cmd, param)
                
        except ValueError as e:
            self.print(f"Ошибка разбора команды: {e}")

    def process_control_command(self, cmd: str, param: str) -> None:
        """
        Обрабатывает команды управления исполнительными устройствами.
        
        Args:
            cmd (str): Тип команды (OPEN, CLOSE, SET и т.д.)
            param (str): Параметр команды
        """
        try:
            value = int(param)
            self.state = 1
            
            for i in range(value):
                if self.db_worker.change_value(
                    self.sector,
                    self.to_change,
                    1 if value > 0 else -1
                ):
                    self.print(f"Успешное изменение параметра ({i+1}/{value})")
                sleep(1)
                
            self.state = 0
        except ValueError as e:
            self.print(f"Некорректный параметр команды: {e}")