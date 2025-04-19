import socket
import threading
import uuid
import datetime
import json

from encryption import encrypt, decrypt
from config import (
    NO_UUID,
    LOC_SOCK_SERV_ADDR,
    LOC_SOCK_SERV_PORT,
    PASSWORD,
)


def print_with_time(*args, **kwargs) -> None:
    print(f"({datetime.datetime.now().strftime('%H:%M:%S')}) ", end="")
    print(*args, **kwargs)


def print_as_device(
    device_name: str,
    device_uuid: str,
    data: object,
) -> None:
    print_with_time(
        f"{device_uuid}[{device_name}]: ",
        end=""
    )
    if hasattr(data, "__str__"):
        print(data)
    else:
        print("неприводимые к строке данные")


def receive_data(conn: socket.socket) -> str:
    data_length = int.from_bytes(conn.recv(4), "big")
    data = json.loads(decrypt(conn.recv(data_length)))
    return data


def send_data(conn: socket.socket, data: object) -> None:
    encoded_data = encrypt(json.dumps(data))
    conn.sendall(len(encoded_data).to_bytes(4, "big"))
    conn.sendall(encoded_data)


def login(conn: socket.socket) -> list[str]:
    password = receive_data(conn)[0]
    if password != PASSWORD:
        return []
    del password
    device_name = receive_data(conn)[0]
    device_uuid = receive_data(conn)[0]
    if device_uuid == NO_UUID:
        device_uuid = str(uuid.uuid4())
        send_data(conn, [device_uuid])
    return [device_name, device_uuid]


def work(
    conn: socket.socket,
    addr: tuple,
    device_name: str,
    device_uuid: str,
) -> None:
    try:
        if data := receive_data(conn):
            print_as_device(device_name, device_uuid, data)
        send_data(conn, [data])
    except Exception as ex:
        print_as_device(
            device_name,
            device_uuid,
            "подключение разорвано"
        )
        raise ex


def start_device(conn: socket.socket, addr: tuple) -> None:
    login_res = login(conn)
    if not login_res:
        print_with_time("нелигитимное устройство не было подключено")
        conn.close()
        return
    device_name = login_res[0]
    device_uuid = login_res[1]
    print_as_device(
        device_name,
        device_uuid,
        "устройство подключено"
    )
    while True:
        try:
            work(conn, addr, device_name, device_uuid)
        except:
            break
    conn.close()


def main() -> None:
    connections = list()

    sock = socket.socket()
    sock.bind((LOC_SOCK_SERV_ADDR, LOC_SOCK_SERV_PORT))
    sock.listen(1)
    print_with_time("сервер запущен")
    while True:
        try:
            conn, addr = sock.accept()
        except KeyboardInterrupt:
            print_with_time("работа сервера завершена")
            break
        t = threading.Thread(
            target=start_device,
            args=(conn, addr),
        )
        t.start()
        connections.append(conn)
    for connection in connections:
        connection.shutdown(socket.SHUT_RDWR)


if __name__ == "__main__":
    main()
