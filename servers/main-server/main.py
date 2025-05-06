import socket
import struct
import json
from threading import Thread
from encryption import encrypt, decrypt
from DBMS_worker import DBMS_worker
from config import MAIN_SERV_ADDR, MAIN_SERV_PORT


class MainServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.db = DBMS_worker(
            host="localhost", user="root", password="123", db_name="GreenHouseMain"
        )
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def handle_client(self, conn, addr):
        """Обработка клиентского соединения"""
        try:
            raw_length = conn.recv(4)
            if len(raw_length) != 4:
                print("Некорректная длина данных")
                return

            data_length = struct.unpack("!I", raw_length)[0]

            encrypted_data = bytearray()
            while len(encrypted_data) < data_length:
                chunk = conn.recv(min(4096, data_length - len(encrypted_data)))
                if not chunk:
                    print("Соединение разорвано")
                    return
                encrypted_data.extend(chunk)

            try:
                decrypted = decrypt(bytes(encrypted_data))
            except Exception as e:
                print(f"Декодирование не удалось: {str(e)}")
                return

            try:
                request = json.loads(decrypted)
            except json.JSONDecodeError as e:
                print(f"Ошибка декодирования JSON: {str(e)}")
                print(f"Данные: {decrypted}")
                return

            if "email" not in request:
                print("Не указан 'email' в запросе")
                return

            print(f"Проверка подписки для: {request['email']}")

            response = self.db.check_subscription(request["email"])
            print(f"Статус подписки: {response}")

            response_str = json.dumps(response)
            encrypted_response = encrypt(response_str)

            conn.sendall(struct.pack("!I", len(encrypted_response)))
            conn.sendall(encrypted_response)

        except Exception as e:
            print(f"Ошибка обработки запроса: {e}")
            import traceback

            traceback.print_exc()
        finally:
            conn.close()

    def start(self):
        """Запуск сервера"""
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        print(f"Главный сервер запущен на {self.host}:{self.port}")

        while True:
            conn, addr = self.socket.accept()
            client_thread = Thread(target=self.handle_client, args=(conn, addr))
            client_thread.start()


if __name__ == "__main__":
    server = MainServer(MAIN_SERV_ADDR, MAIN_SERV_PORT)
    server.start()
