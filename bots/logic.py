import os

from config import NO_UUID


UUID_DIR = os.path.join(os.path.dirname(p=__file__), 'uuids')


def get_uuid(uuid_filename: str) -> str:
    uuid = NO_UUID

    if uuid_filename in os.listdir(UUID_DIR):
        with open(os.path.join(UUID_DIR, uuid_filename), "r") as file:
            uuid = file.read()
    
    return uuid


def set_uuid(uuid_filename: str, uuid: str) -> None:
    with open(os.path.join(UUID_DIR, uuid_filename), "w") as file:
        file.write(uuid)