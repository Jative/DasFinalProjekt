from Crypto.Cipher import AES

from config import ENCRYPTION_KEY


def encrypt(message: str) -> bytes:
    cipher = AES.new(ENCRYPTION_KEY, AES.MODE_EAX)
    
    byte_message = message.encode("utf-8")
    cipher_message, tag = cipher.encrypt_and_digest(byte_message)
    nonce = cipher.nonce
    byte_data = tag + nonce + cipher_message

    return byte_data


def decrypt(byte_data: bytes) -> str:
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