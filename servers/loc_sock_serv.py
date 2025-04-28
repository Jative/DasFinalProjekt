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
        Инициализирует сервер с сетевыми параметрами и подключением к БД.

        Args:
            host (str): IP-адрес сервера
            port (int): Порт сервера
            password (str): Пароль для аутентификации устройств
            no_uuid (str): Специальный UUID для новых устройств
        """
        self.host = host
        self.port = port
        self.password = password
        self.no_uuid = no_uuid
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connections = []
        self.db_worker = DBMS_worker(
            "localhost",
            "root",
            "123",
            "GreenHouseLocal"
        )
        self.running = False

    @staticmethod
    def print_with_time(*args, **kwargs) -> None:
        """
        Выводит сообщение с временной меткой в начале.

        Args:
            *args: Позиционные аргументы для print()
            **kwargs: Именованные аргументы для print()
        """
        print(f"({datetime.datetime.now().strftime('%H:%M:%S')}) ", end="")
        print(*args, **kwargs)

    @staticmethod
    def print_as_device(device_name: str, device_uuid: str, data: object) -> None:
        """
        Форматирует вывод от лица устройства.

        Args:
            device_name (str): Имя устройства
            device_uuid (str): Уникальный идентификатор устройства
            data (object): Выводимые данные
        """
        Server.print_with_time(f"{device_uuid}[{device_name}]: ", end="")
        if hasattr(data, "__str__"):
            print(data)
        else:
            print("неприводимые к строке данные")

    def receive_data(self, conn: socket.socket) -> object:
        """
        Принимает и расшифровывает данные из соединения.

        Args:
            conn (socket.socket): Активное сокет-подключение

        Returns:
            object: Расшифрованные и десериализованные данные
        """
        data_length = int.from_bytes(conn.recv(4), "big")
        encrypted_data = conn.recv(data_length)
        return json.loads(decrypt(encrypted_data))

    def send_data(self, conn: socket.socket, data: object) -> None:
        """
        Шифрует и отправляет данные через соединение.

        Args:
            conn (socket.socket): Активное сокет-подключение
            data (object): Данные для отправки
        """
        encrypted_data = encrypt(json.dumps(data))
        conn.sendall(len(encrypted_data).to_bytes(4, "big"))
        conn.sendall(encrypted_data)

    def perform_login(self, conn: socket.socket) -> tuple[str, str] | None:
        """
        Выполняет процесс аутентификации устройства.

        Args:
            conn (socket.socket): Активное сокет-подключение

        Returns:
            tuple[str, str] | None: (Имя устройства, UUID) при успехе, иначе None
        """
        try:
            if (password := self.receive_data(conn)[0]) != self.password:
                return None

            device_name = self.receive_data(conn)[0]
            device_uuid = self.receive_data(conn)[0]

            if device_uuid == self.no_uuid:
                device_uuid = str(uuid.uuid4())
                self.send_data(conn, [device_uuid])

            return device_name, device_uuid

        except:
            return None
    
    def process_data(
        self,
        device_name: str,
        device_uuid: str,
        data: list,
    ) -> None:
        """
        Обрабатывает полученные данные датчиков и обновляет БД.

        Args:
            device_name (str): Имя устройства
            device_uuid (str): Уникальный идентификатор устройства
            data (list): Полученные значения данных
        """
        data_lines = self.db_worker.get_actual_data_lines_by_uuid(device_uuid)
        if len(data_lines) < len(data-1):
            Server.print_as_device(
                device_name,
                device_uuid,
                "В БД не заданы данные для устройства"
            )
            return
        for i in range(len(data_lines)):
            self.db_worker.update_actual_data_line(data_lines[i][0], data[i+1])
    
    def process_rules(
        self,
        rules: list[tuple] | None
    ) -> None:
        """
        Обрабатывает правила и создаёт задачи.

        Args:
            rules (list[tuple] | None): Список правил из БД
        """
        for rule in rules:
            _, data_id, rule_condition, rule_value, _, message = rule
            data_value = self.db_worker.get_actual_data_line(data_id)[4]
            device_id = data[1]
            if task_exists(device_id):
                break
            match rule_condition:
                case 1:
                    if data_value > rule_value:
                        self.db_worker.add_task(device_id, message)
                    break
                case 2:
                    if data_value < rule_value:
                        self.db_worker.add_task(device_id, message)
                    break
                case 3:
                    if data_value == rule_value:
                        self.db_worker.add_task(device_id, message)
                    break
                case 4:
                    if data_value != rule_value:
                        self.db_worker.add_task(device_id, message)
                    break
                case _:
                    break

    def process_tasks(self, device_uuid: str) -> list[str]:
        """
        Получает активную задачу для устройства.

        Args:
            device_uuid (str): Уникальный идентификатор устройства

        Returns:
            list[str]: Запись задачи из таблицы или значение по умолчанию
        """
        task_message = self.db_worker.get_task_message(device_uuid)
        return task_message if task_message else [f"{SEND_STATE_DELAY}~0"]

    def handle_connection(self, conn: socket.socket, addr: tuple) -> None:
        """
        Управляет всем жизненным циклом клиентского подключения.

        Args:
            conn (socket.socket): Новое сокет-подключение
            addr (tuple): Информация об адресе клиента
        """
        device_info = self.perform_login(conn)
        if not device_info:
            self.print_with_time("Неизвестное устройство не было авторизовано")
            conn.close()
            return

        device_name, device_uuid = device_info
        self.print_as_device(device_name, device_uuid, "Подключение установлено")
        self.db_worker.add_device(device_uuid, device_name)

        try:
            while self.running:
                if (data := self.receive_data(conn)) is not None:
                    self.print_as_device(device_name, device_uuid, data)
                    self.process_data(device_name, device_uuid, data)
                    self.process_rules(self.db_worker.get_rules(device_uuid))
                    self.send_data(conn, self.process_tasks(device_uuid))
        except Exception as e:
            print(e)
            self.print_as_device(device_name, device_uuid, "Подключение разорвано")
        finally:
            conn.close()

    def start(self) -> None:
        """
        Запускает сервер и начинает принимать подключения.
        """
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)
        self.running = True
        self.print_with_time(f"Сервер запущен на {self.host}:{self.port}")

        try:
            while self.running:
                conn, addr = self.sock.accept()
                self.connections.append(conn)
                threading.Thread(
                    target=self.handle_connection,
                    args=(conn, addr),
                    daemon=True
                ).start()
        except KeyboardInterrupt:
            self.shutdown()

    def shutdown(self) -> None:
        """
        Корректно останавливает сервер и освобождает ресурсы.
        """
        self.running = False
        self.print_with_time("Работа сервера завершается...")
        
        for conn in self.connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
                conn.close()
            except OSError:
                pass
        
        self.sock.close()
        self.print_with_time("Работа сервера прекращена")


if __name__ == "__main__":
    server = Server(
        host=LOC_SOCK_SERV_ADDR,
        port=LOC_SOCK_SERV_PORT,
        password=PASSWORD,
        no_uuid=NO_UUID
    )
    server.start()