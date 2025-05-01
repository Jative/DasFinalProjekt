import os

from config import NO_UUID


UUID_DIR = os.path.join(os.path.dirname(p=__file__), 'uuids')


def get_uuid(uuid_filename: str) -> str:
    """
    Получает UUID устройства из файла в специальной директории.

    Args:
        uuid_filename (str): Имя файла с UUID (без пути)

    Returns:
        str: Сохраненный UUID или значение NO_UUID, если файл не найден
    """
    uuid = NO_UUID

    if uuid_filename in os.listdir(UUID_DIR):
        with open(os.path.join(UUID_DIR, uuid_filename), "r") as file:
            uuid = file.read()
    
    return uuid


def set_uuid(uuid_filename: str, uuid: str) -> None:
    """
    Сохраняет UUID устройства в файл. Перезаписывает существующий файл.

    Args:
        uuid_filename (str): Имя файла для сохранения (без пути)
        uuid (str): UUID для сохранения

    Raises:
        IOError: При проблемах с записью в файл
    """
    with open(os.path.join(UUID_DIR, uuid_filename), "w") as file:
        file.write(uuid)