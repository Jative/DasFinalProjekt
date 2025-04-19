import mysql.connector

from random import randint


class DBMS_worker:
    def __init__(self, host: str, user: str, password: str, db_name: str):
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
        try:
            self.cursor.execute(f"USE {db_name}")
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_BAD_DB_ERROR:
                self.create_db(db_name)
                self.insert_test_values()
            else:
                raise


    def create_db(self, db_name: str) -> None:
        self.cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        self.cursor.execute(f"USE {db_name}")

        self.cursor.execute("""
            CREATE TABLE indicators (
                indicator_id INT NOT NULL AUTO_INCREMENT,
                indicator_sector INT,
                indicator_name VARCHAR(255),
                indicator_value INT,
                PRIMARY KEY (indicator_id)
            )
        """)


    def insert_test_values(self):
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
        try:
            self.cursor.execute("""
                SELECT indicator_value
                FROM indicators
                WHERE indicator_sector = %s AND indicator_name = %s
            """, (sector, name))
            cursor_result = self.cursor.fetchone()
            if cursor_result:
                return cursor_result[0]
            else:
                raise
        except:
            return 0