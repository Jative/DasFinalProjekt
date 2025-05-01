import mysql.connector

from random import randint


class DBMS_worker:
    def __init__(self, host: str, user: str, password: str, db_name: str):
        """
        Инициализирует подключение к MySQL и целевую базу данных.
        
        Args:
            host: Хост MySQL сервера
            user: Имя пользователя
            password: Пароль пользователя
            db_name: Название базы данных
            
        Attributes:
            cnx: Объект соединения с MySQL
            cursor: Курсор для выполнения SQL-запросов
            created (bool): Флаг успешного создания подключения
            error (str): Сообщение об ошибке при неудачной инициализации
        """
        try:
            self.cnx = mysql.connector.connect(
                host=host,
                user=user,
                password=password,
                autocommit=True
            )
            self.cursor = self.cnx.cursor()
            self.connect_to_db(db_name)
            self.created = True
        except Exception as e:
            self.created = False
            self.error = str(e)


    def connect_to_db(self, db_name: str) -> None:
        """
        Подключается к указанной базе данных. Если база не существует - создает её
        и заполняет тестовыми данными.
        
        Args:
            db_name: Название базы данных
            
        Raises:
            mysql.connector.Error: Ошибки MySQL кроме отсутствия базы данных
        """
        try:
            self.cursor.execute(f"USE {db_name}")
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_BAD_DB_ERROR:
                self.create_db(db_name)
                self.insert_test_values()
            else:
                raise


    def create_db(self, db_name: str) -> None:
        """
        Создает новую базу данных и структуру таблиц.
        
        Args:
            db_name: Название создаваемой базы данных
            
        Создает:
            - Базу данных с указанным именем
            - Таблицу indicators с полями:
                * indicator_id (первичный ключ)
                * indicator_sector (INT)
                * indicator_name (VARCHAR(255))
                * indicator_value (INT)
        """
        self.cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        self.cursor.execute(f"USE {db_name}")

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS indicators (
                indicator_id INT NOT NULL AUTO_INCREMENT,
                indicator_sector INT,
                indicator_name VARCHAR(255),
                indicator_value INT,
                PRIMARY KEY (indicator_id)
            )
        """)


    def insert_test_values(self) -> None:
        """
        Заполняет таблицу indicators тестовыми данными:
        - 2 сектора (0 и 1)
        - 3 параметра: temperature, humidity, brightness
        - Случайные значения в заданных диапазонах
        """
        params = ("temperature", "humidity", "brightness")
        allowed_values = ((22, 28), (60, 90), (0, 100))
        for i in range(2):
            for j in range(len(params)):
                self.cursor.execute("""
                    INSERT INTO indicators (
                        indicator_sector,
                        indicator_name,
                        indicator_value
                    )
                    VALUES (%s, %s, %s)
                """, (i, params[j], randint(*allowed_values[j])))
    

    def get_value(
        self,
        sector: int,
        name: str
    ) -> int:
        """
        Получает текущее значение показателя из базы данных.
        
        Args:
            sector: Номер сектора теплицы
            name: Название показателя
            
        Returns:
            int: Значение показателя или 0 при ошибке
        """
        try:
            self.cursor.execute("""
                    SELECT indicator_value
                    FROM indicators
                    WHERE indicator_sector = %s AND indicator_name = %s
                """,
                (sector, name)
            )
            cursor_result = self.cursor.fetchone()
            if cursor_result:
                return cursor_result[0]
            else:
                raise
        except:
            return 0
    

    def change_value(
        self,
        sector: int,
        name: str,
        value: int,
    ) -> bool:
        """
        Изменяет значение показателя в базе данных.
        
        Args:
            sector: Номер сектора
            name: Название показателя
            value: Величина изменения (может быть отрицательной)
            
        Returns:
            bool: True при успешном обновлении
        """
        try:
            self.cursor.execute(
                """
                UPDATE indicators
                SET indicator_value = indicator_value + %s
                WHERE indicator_sector = %s AND indicator_name = %s
                """,
                (value, sector, name)
            )
            return True
        except:
            return False