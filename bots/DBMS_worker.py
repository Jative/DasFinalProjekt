import mysql.connector
from mysql.connector import pooling
from random import randint


class DBMS_worker:
    def __init__(self, host: str, user: str, password: str, db_name: str):
        """
        Инициализирует подключение с проверкой существования БД
        """
        self.db_name = db_name
        
        try:
            # Этап 1: Временное подключение без указания БД
            temp_cnx = mysql.connector.connect(
                host=host,
                user=user,
                password=password,
                autocommit=True
            )
            
            # Этап 2: Проверка и создание всей структуры
            self._check_database(temp_cnx)
            temp_cnx.close()

            # Этап 3: Инициализация пула для рабочей БД
            self.cnx_pool = pooling.MySQLConnectionPool(
                pool_name="device_pool",
                pool_size=20,
                host=host,
                user=user,
                password=password,
                database=db_name,
                autocommit=True
            )
            
            self.created = True
        
        except Exception as e:
            self.created = False
            self.error = str(e)

    def _check_database(self, temp_cnx):
        """
        Проверяет существование БД и создает при необходимости
        """
        cursor = temp_cnx.cursor()
        try:
            cursor.execute(f"USE {self.db_name}")
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_BAD_DB_ERROR:
                self._create_database(temp_cnx)
                self._create_tables(temp_cnx)
                self._insert_test_data(temp_cnx)
            else:
                raise
        finally:
            cursor.close()

    def _create_database(self, temp_cnx):
        cursor = temp_cnx.cursor()
        try:
            cursor.execute(f"CREATE DATABASE {self.db_name}")
        finally:
            cursor.close()

    def _create_tables(self, temp_cnx):
        cursor = temp_cnx.cursor()
        try:
            cursor.execute(f"USE {self.db_name}")
            cursor.execute("""
                CREATE TABLE indicators (
                    indicator_id INT NOT NULL AUTO_INCREMENT,
                    indicator_sector INT,
                    indicator_name VARCHAR(255),
                    indicator_value INT,
                    PRIMARY KEY (indicator_id)
                )
            """)
        finally:
            cursor.close()

    def _insert_test_data(self, temp_cnx):
        cursor = temp_cnx.cursor()
        try:
            params = ("temperature", "humidity", "brightness")
            allowed_values = ((22, 28), (60, 90), (0, 100))
            
            data = [
                (i, param, randint(*allowed_values[j]))
                for i in range(2)
                for j, param in enumerate(params)
            ]
            
            cursor.executemany(
                "INSERT INTO indicators (indicator_sector, indicator_name, indicator_value) VALUES (%s, %s, %s)",
                data
            )
            temp_cnx.commit()
        finally:
            cursor.close()

    def _execute(self, query, params=None, multi=False):
        """
        Универсальный метод выполнения SQL-запросов
        Возвращает словарь с результатами:
        {
            'success': bool,
            'results': list,    # Для SELECT
            'rowcount': int,    # Для INSERT/UPDATE/DELETE
            'lastrowid': int    # Для INSERT
        }
        """
        conn = self.cnx_pool.get_connection()
        result = {'success': False}
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params, multi)
                
                if cursor.with_rows:
                    result['results'] = cursor.fetchall()
                else:
                    result['rowcount'] = cursor.rowcount
                    result['lastrowid'] = cursor.lastrowid
                
                result['success'] = True
        except Exception as e:
            result['error'] = str(e)
        finally:
            conn.close()
        return result

    def insert_test_values(self) -> None:
        """
        Заполняет таблицу тестовыми данными с использованием пула соединений
        """
        params = ("temperature", "humidity", "brightness")
        allowed_values = ((22, 28), (60, 90), (0, 100))
        
        data = []
        for i in range(2):
            for j in range(len(params)):
                data.append((
                    i,
                    params[j],
                    randint(*allowed_values[j])
                ))

        conn = self.cnx_pool.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO indicators (
                        indicator_sector,
                        indicator_name,
                        indicator_value
                    ) VALUES (%s, %s, %s)
                    """,
                    data
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_value(self, sector: int, name: str) -> int:
        """
        Получает значение показателя из базы данных
        """
        result = self._execute(
            """
            SELECT indicator_value
            FROM indicators
            WHERE indicator_sector = %s AND indicator_name = %s
            """,
            (sector, name)
        )
        
        if result['success'] and result.get('results'):
            return result['results'][0][0]
        return 0

    def change_value(self, sector: int, name: str, value: int) -> bool:
        """
        Обновляет значение показателя в базе данных
        """
        result = self._execute(
            """
            UPDATE indicators
            SET indicator_value = indicator_value + %s
            WHERE indicator_sector = %s AND indicator_name = %s
            """,
            (value, sector, name))
        
        return result['success'] and result.get('rowcount', 0) > 0