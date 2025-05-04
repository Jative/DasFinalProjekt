import mysql.connector
from datetime import datetime


class DBMS_worker:
    def __init__(self, host: str, user: str, password: str, db_name: str):
        """
        Инициализирует соединение с MySQL сервером и подключается к базе данных.

        Args:
            host (str): Хост MySQL сервера
            user (str): Имя пользователя
            password (str): Пароль пользователя
            db_name (str): Название базы данных

        Attributes:
            created (bool): Флаг успешного подключения
            error (str): Сообщение об ошибке при неудачном подключении
        """
        try:
            self.cnx = mysql.connector.connect(
                host=host, user=user, password=password, autocommit=True
            )
            self.cursor = self.cnx.cursor(buffered=True)
            self.connect_to_db(db_name)
            self.created = True
        except Exception as e:
            self.created = False
            self.error = str(e)

    def connect_to_db(self, db_name: str) -> None:
        """
        Подключается к указанной базе данных. Если база не существует - создает её.

        Args:
            db_name (str): Название базы данных для подключения
        """
        try:
            self.cursor.execute(f"USE {db_name}")
        except mysql.connector.Error as err:
            if err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
                self.create_db(db_name)
            else:
                raise

    def create_db(self, db_name: str) -> None:
        """
        Создает новую базу данных и все необходимые таблицы:
        - devices (устройства)
        - actual_data (актуальные показатели)
        - data_history (история изменений)
        - rules (правила обработки данных)
        - tasks (задачи для устройств)

        Также создает триггеры для автоматического сохранения истории изменений.
        """
        self.cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        self.cursor.execute(f"USE {db_name}")

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INT AUTO_INCREMENT PRIMARY KEY,
                user_login VARCHAR(255) UNIQUE NOT NULL,
                user_subscription_until DATETIME NOT NULL
            )
        """
        )

    def add_user(self, login: str, subscription_end: datetime) -> int:
        """Добавление пользователя с подпиской"""
        try:
            self.cursor.execute(
                """
                INSERT INTO users (user_login, user_subscription_until)
                VALUES (%s, %s)
                """,
                (login, subscription_end),
            )
            self.cnx.commit()
            return self.cursor.lastrowid
        except mysql.connector.Error as e:
            print(f"Ошибка добавления пользователя: {e}")
            return -1

    def check_subscription(self, login: str) -> dict:
        """Проверка активности подписки"""
        self.cursor.execute(
            """
            SELECT user_subscription_until 
            FROM users 
            WHERE user_login = %s
            """,
            (login,),
        )
        result = self.cursor.fetchone()

        if not result:
            return {"active": False, "reason": "User not found"}

        subscription_end = result[0]
        is_active = subscription_end > datetime.now()

        return {
            "active": is_active,
            "until": subscription_end.isoformat() if is_active else None,
        }

    def __del__(self):
        self.cursor.close()
        self.cnx.close()
