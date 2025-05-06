import socket
import threading
import uuid
import datetime
import json

from encryption import encrypt, decrypt
from DBMS_worker import DBMS_worker
from config import (
    NO_UUID,
    LOC_SOCK_SERV_ADDR,
    LOC_SOCK_SERV_PORT,
    PASSWORD,
    SEND_STATE_DELAY,
)


class Server:
    def __init__(self, host: str, port: int, password: str, no_uuid: str):
        """
        Инициализирует сервер IoT для управления умной теплицей.

        Args:
            host (str): IP-адрес для прослушивания подключений
            port (int): Порт для входящих соединений
            password (str): Секретный пароль для аутентификации устройств
            no_uuid (str): Специальный UUID для новых неподключенных устройств

        Attributes:
            sock (socket.socket): Основной сокет сервера
            connections (list): Активные клиентские подключения
            db_worker (DBMS_worker): Объект для работы с базой данных
            running (bool): Флаг активности сервера
        """
        self.host = host
        self.port = port
        self.password = password
        self.no_uuid = no_uuid
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connections = []
        self.db_worker = DBMS_worker("localhost", "root", "123", "GreenHouseLocal")
        self.running = False
        self.lock = threading.Lock()

    @staticmethod
    def print_with_time(*args, **kwargs) -> None:
        """
        Выводит сообщение с временной меткой в формате HH:MM:SS.

        Args:
            *args: Аргументы для передачи в стандартный print()
            **kwargs: Именованные аргументы для print()
        """
        print(f"({datetime.datetime.now().strftime('%H:%M:%S')}) ", end="")
        print(*args, **kwargs)

    @staticmethod
    def print_as_device(device_name: str, device_uuid: str, data: object) -> None:
        """
        Форматирует вывод сообщения от имени устройства.

        Args:
            device_name (str): Человекочитаемое имя устройства
            device_uuid (str): Уникальный идентификатор устройства
            data (object): Данные для отображения (автоматически конвертируются в JSON)
        """
        Server.print_with_time(
            f"{device_uuid}[{device_name}]: {json.dumps(data, ensure_ascii=False)}"
        )

    def receive_data(self, conn: socket.socket) -> dict:
        """
        Принимает и десериализует данные из сокета.

        Args:
            conn (socket.socket): Активное клиентское подключение

        Returns:
            dict: Расшифрованные данные в виде словаря

        Raises:
            JSONDecodeError: При получении некорректных данных
            ConnectionResetError: При обрыве соединения
        """
        try:
            raw_length = conn.recv(4)
            if not raw_length:
                raise ConnectionError("Соединение закрыто")
            data_length = int.from_bytes(raw_length, "big")
            encrypted_data = b''
            while len(encrypted_data) < data_length:
                packet = conn.recv(data_length - len(encrypted_data))
                if not packet:
                    raise ConnectionError("Не удалось прочитать все данные")
                encrypted_data += packet
            return json.loads(decrypt(encrypted_data))
        except Exception as e:
            raise

    def send_data(self, conn: socket.socket, data: object) -> None:
        """
        Сериализует и отправляет данные через сокет.

        Args:
            conn (socket.socket): Активное клиентское подключение
            data (object): Данные для отправки (обычно словарь)

        Raises:
            TypeError: При проблемах с сериализацией данных
            BrokenPipeError: При попытке записи в закрытый сокет
        """
        encrypted_data = encrypt(json.dumps(data))
        conn.sendall(len(encrypted_data).to_bytes(4, "big"))
        conn.sendall(encrypted_data)

    def perform_login(self, conn: socket.socket) -> tuple[str, str] | None:
        """
        Выполняет процесс аутентификации устройства.

        Протокол авторизации:
        1. Устройство отправляет словарь с паролем {'password': str}
        2. Сервер проверяет пароль
        3. Устройство отправляет метаданные {'device_name': str, 'uuid': str}
        4. Сервер генерирует новый UUID при необходимости

        Args:
            conn (socket.socket): Клиентское подключение

        Returns:
            tuple | None: Кортеж (имя устройства, UUID) или None при ошибке
        """
        try:
            auth_data = self.receive_data(conn)
            if auth_data.get("password") != self.password:
                return None

            device_info = self.receive_data(conn)
            device_name = device_info.get("device_name")
            device_uuid = device_info.get("uuid", self.no_uuid)

            if device_uuid == self.no_uuid:
                device_uuid = str(uuid.uuid4())
                self.send_data(conn, {"status": "registered", "uuid": device_uuid})
            else:
                self.send_data(conn, {"status": "authorized"})

            return device_name, device_uuid

        except Exception as e:
            self.print_with_time(f"Ошибка авторизации: {e}")
            return None

    def process_sensor_data(self, device_uuid: str, data: dict) -> None:
        """
        Обрабатывает данные с датчиков и сохраняет в БД.

        Args:
            device_uuid (str): UUID устройства-источника
            data (dict): Словарь с показателями датчиков:
                {
                    'state': int,
                    'temperature': int,
                    'humidity': int,
                    ...
                }

        Note:
            Поле 'state' игнорируется при сохранении в БД
        """
        try:
            sensor_data = {k: v for k, v in data.items() if k != "state"}
            self.db_worker.add_device_data_batch(device_uuid, sensor_data)
        except Exception as e:
            self.print_with_time(f"Ошибка обработки данных: {e}")

    def check_rules(self, device_uuid: str) -> list[str]:
        """
        Проверяет активные правила для устройства и генерирует команды.

        Args:
            device_uuid (str): UUID целевого устройства-исполнителя

        Returns:
            list[str]: Список команд для выполнения в формате "команда~параметр"

        Logic:
            1. Получает все правила для устройства из БД
            2. Для каждого активного правила:
               - Проверяет текущее значение параметра
               - Сравнивает с порогом по условию
               - При выполнении условия добавляет команду
        """
        try:
            commands = []
            rules = self.db_worker.get_rules_by_target_device(device_uuid)
            custom_delay = None

            for rule in rules:
                if not rule["is_active"]:
                    continue

                current_value = (
                    self.db_worker.get_actual_data(
                        rule["source_device"], rule["parameter"]
                    )
                    .get(rule["parameter"], {})
                    .get("value", 0)
                )

                condition_met = False
                if rule["condition"] == 1:  # >
                    condition_met = current_value > rule["threshold"]
                elif rule["condition"] == 2:  # <
                    condition_met = current_value < rule["threshold"]
                elif rule["condition"] == 3:  # ==
                    condition_met = current_value == rule["threshold"]
                elif rule["condition"] == 4:  # !=
                    condition_met = current_value != rule["threshold"]

                if condition_met:
                    parts = rule["message"].split("~")
                    command = parts[0]
                    if len(parts) > 1 and parts[1].isdigit():
                        custom_delay = int(parts[1])
                    commands.append(command)

            final_delay = custom_delay if custom_delay else SEND_STATE_DELAY
            return (final_delay, commands)
        except Exception as e:
            self.print_with_time(f"Ошибка проверки правил: {e}")
            return []

    def handle_connection(self, conn: socket.socket, addr: tuple) -> None:
        """
        Обрабатывает жизненный цикл клиентского подключения.

        Args:
            conn (socket.socket): Новое клиентское подключение
            addr (tuple): Кортеж (IP-адрес, порт) клиента

        Workflow:
            1. Аутентификация устройства
            2. Регистрация в системе
            3. Основной цикл обработки данных:
               - Прием показателей датчиков
               - Обновление БД
               - Проверка правил
               - Отправка команд
            4. Обработка ошибок и закрытие соединения
        """
        device_info = self.perform_login(conn)
        if not device_info:
            conn.close()
            return

        device_name, device_uuid = device_info
        self.print_as_device(device_name, device_uuid, "Подключение установлено")
        self.db_worker.add_device(device_uuid, device_name)

        try:
            while self.running:
                sensor_data = self.receive_data(conn)
                self.print_as_device(device_name, device_uuid, sensor_data)
                self.db_worker.update_device_communication_timestamp(device_uuid)

                self.process_sensor_data(device_uuid, sensor_data)
                delay, commands = self.check_rules(device_uuid)
                response = {"delay": delay, "commands": commands}
                self.send_data(conn, response)
        except Exception as e:
            self.print_as_device(device_name, device_uuid, f"Ошибка: {str(e)}")
        finally:
            conn.close()
            with self.lock:
                if conn in self.connections:
                    self.connections.remove(conn)
            self.print_as_device(device_name, device_uuid, "Отключен")

    def start(self) -> None:
        """
        Запускает основной цикл работы сервера.

        Actions:
            1. Привязывает сокет к указанному адресу
            2. Переходит в режим прослушивания
            3. Для каждого нового подключения:
               - Создает отдельный поток
               - Добавляет в список активных соединений
            4. Обрабатывает KeyboardInterrupt для плавного завершения
        """
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)
        self.running = True
        self.print_with_time(f"Сервер запущен на {self.host}:{self.port}")

        try:
            while self.running:
                conn, addr = self.sock.accept()
                with self.lock:
                    self.connections.append(conn)
                threading.Thread(
                    target=self.handle_connection, args=(conn, addr), daemon=True
                ).start()
        except KeyboardInterrupt:
            self.shutdown()

    def shutdown(self) -> None:
        """
        Безопасно останавливает сервер.

        Actions:
            1. Устанавливает флаг running=False
            2. Закрывает все активные подключения
            3. Освобождает ресурсы сокета
            4. Выводит статус завершения
        """
        self.running = False
        with self.lock:
            for conn in self.connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self.connections.clear()
        self.sock.close()
        self.print_with_time("Сервер остановлен")


if __name__ == "__main__":
    server = Server(
        host=LOC_SOCK_SERV_ADDR,
        port=LOC_SOCK_SERV_PORT,
        password=PASSWORD,
        no_uuid=NO_UUID,
    )
    server.start()
