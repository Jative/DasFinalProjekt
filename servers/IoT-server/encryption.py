from Crypto.Cipher import AES

from config import ENCRYPTION_KEY


def encrypt(message: str) -> bytes:
    """
    Шифрует строковое сообщение с использованием AES в режиме EAX.
    
    Args:
        message (str): Исходное сообщение для шифрования
        
    Returns:
        bytes: Зашифрованные данные в формате:
        [16-байтовый тег][16-байтовый nonce][шифротекст]
        
    Процесс:
        1. Генерирует случайный nonce
        2. Шифрует сообщение с аутентификацией
        3. Объединяет аутентификационный тег, nonce и шифротекст
    """
    cipher = AES.new(ENCRYPTION_KEY, AES.MODE_EAX)
    
    byte_message = message.encode("utf-8")
    cipher_message, tag = cipher.encrypt_and_digest(byte_message)
    nonce = cipher.nonce
    byte_data = tag + nonce + cipher_message

    return byte_data


def decrypt(byte_data: bytes) -> str:
    """
    Дешифрует данные из формата AES-EAX.
    
    Args:
        byte_data (bytes): Данные в формате [тег][nonce][шифротекст]
        
    Returns:
        str: Расшифрованное исходное сообщение
        
    Raises:
        ValueError: При ошибках:
        - Неверная длина или формат данных
        - Неверный аутентификационный тег
        - Неверная кодировка сообщения
        
    Процесс:
        1. Извлекает тег, nonce и шифротекст
        2. Проверяет целостность данных
        3. Дешифрует сообщение
        4. Проверяет кодировку UTF-8
    """
    tag = byte_data[:16]
    nonce = byte_data[16:32]
    cipher_message = byte_data[32:]

    try:
        cipher = AES.new(ENCRYPTION_KEY, AES.MODE_EAX, nonce=nonce)
        byte_message = cipher.decrypt_and_verify(cipher_message, tag)
        return byte_message.decode('utf-8')
    except ValueError:
        raise ValueError("Ошибка дешифрования. Невалидные данные")
    except UnicodeDecodeError:
        raise ValueError("Ошибка дешифрования. Сообщение использует не UTF-8")