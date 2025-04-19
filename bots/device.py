import socket
import json
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
        self.sock = socket.socket()
        self.uuid = get_uuid(self.uuid_filename)
        self.state = 0
        self.db_worker = db_worker
    
    def print(self, data: object) -> None:
        print(f"{self.uuid} [{self.IoT_name}]: ", end="")
        if hasattr(data, "__str__"):
            print(data)
        else:
            print("Неприводимые к строке данные")
    
    def receive_data(self) -> str:
        data_length = int.from_bytes(self.sock.recv(4), "big")
        data = self.sock.recv(data_length)
        return json.loads(decrypt(data))[0]

    def send_data(self, data: list) -> None:
        encoded_data = encrypt(json.dumps(data))
        self.sock.sendall(len(encoded_data).to_bytes(4, "big"))
        self.sock.sendall(encoded_data)

    def login(self) -> None:
        self.send_data([PASSWORD])
        self.send_data([self.IoT_name])
        self.send_data([self.uuid])
        if self.uuid == NO_UUID:
            self.uuid = self.receive_data()
            set_uuid(self.uuid_filename, self.uuid)

    def start(self) -> None:
        while True:
            try:
                self.sock.connect((SERVER_ADDR, SERVER_PORT))
                self.login()
                while True:
                    self.work()
            except (ConnectionRefusedError, TimeoutError):
                print(
                    f"Подключение к '{SERVER_ADDR}:{SERVER_PORT}' "
                    f"не удалось с устройства '{self.IoT_name}'"
                )
                sleep(RECONNECT_DELAY)
            except Exception as e:
                print(e)
                print(
                    "Непредвиденная ошибка логики "
                    f"устройства '{self.IoT_name}'"
                )
            finally:
                self.sock.close()
                self.sock = socket.socket()

    def work(self) -> None:
        if self.indicators:
            data_to_send = list()
            for indicator in self.indicators:
                data_to_send.append(self.db_worker.get_value(
                                        self.sector,
                                        indicator,
                                    ))
        else:
            data_to_send = [self.state]
        self.send_data(data_to_send)
        self.print(self.receive_data())
        sleep(SEND_STATE_DELAY)