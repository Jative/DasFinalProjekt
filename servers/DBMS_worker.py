import mysql.connector


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

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id INTEGER NOT NULL AUTO_INCREMENT,
                device_uuid CHAR(36) UNIQUE,
                device_name VARCHAR(255),
                device_last_communication DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (device_id)
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS actual_data (
                data_id INTEGER NOT NULL AUTO_INCREMENT,
                data_device_id INTEGER,
                data_sector INTEGER,
                data_name VARCHAR(255),
                data_value INTEGER,
                data_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (data_id),
                FOREIGN KEY (data_device_id)
                REFERENCES devices(device_id)
                ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_history (
                data_id INTEGER NOT NULL AUTO_INCREMENT,
                data_device_id INTEGER,
                data_sector INTEGER,
                data_name VARCHAR(255),
                data_value INTEGER,
                data_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (data_id),
                FOREIGN KEY (data_device_id)
                REFERENCES devices(device_id)
                ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                rule_id INTEGER NOT NULL AUTO_INCREMENT,
                rule_data_id INTEGER,
                rule_condition INTEGER,
                rule_value INTEGER,
                rule_device_id INTEGER UNIQUE,
                rule_message VARCHAR(255),
                PRIMARY KEY (rule_id),
                FOREIGN KEY (rule_data_id)
                REFERENCES actual_data(data_id)
                ON DELETE CASCADE,
                FOREIGN KEY (rule_device_id)
                REFERENCES devices(device_id)
                ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER NOT NULL AUTO_INCREMENT,
                task_device_id INTEGER,
                task_message VARCHAR(255),
                task_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (task_id),
                FOREIGN KEY (task_device_id)
                REFERENCES devices(device_id)
                ON DELETE CASCADE
            );
        """)
        
        self.cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS after_actual_data_insert
            AFTER INSERT ON actual_data
            FOR EACH ROW
            INSERT INTO data_history (
                data_device_id, 
                data_sector, 
                data_name, 
                data_value, 
                data_timestamp
            )
            VALUES (
                NEW.data_device_id, 
                NEW.data_sector, 
                NEW.data_name, 
                NEW.data_value, 
                NEW.data_timestamp
            );
        """)

        self.cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS after_actual_data_update
            AFTER UPDATE ON actual_data
            FOR EACH ROW
            BEGIN
                INSERT INTO data_history (
                    data_device_id, 
                    data_sector, 
                    data_name, 
                    data_value, 
                    data_timestamp
                )
                VALUES (
                    NEW.data_device_id, 
                    NEW.data_sector, 
                    NEW.data_name, 
                    NEW.data_value, 
                    NEW.data_timestamp
                );
            END;
        """)


    def get_device_id(self, device_uuid: str) -> int | None:
        """
        Получает ID устройства по его UUID.
        
        Args:
            device_uuid (str): Уникальный идентификатор устройства
            
        Returns:
            int | None: ID устройства или None если не найдено
        """
        self.cursor.execute(
            """
            SELECT device_id
            FROM devices
            WHERE device_uuid = %s
            """,
            (device_uuid,)
        )
        query_result = self.cursor.fetchone()
        if query_result:
            return query_result[0]
        else:
            return None


    def add_device(self, uuid: str, name: str) -> bool:
        """
        Добавляет новое устройство в базу данных.
        
        Args:
            uuid (str): Уникальный идентификатор устройства
            name (str): Человекочитаемое имя устройства
            
        Returns:
            bool: True при успешном добавлении
        """
        try:
            self.cursor.execute("""
                    INSERT INTO devices (device_uuid, device_name)
                    VALUES (%s, %s)
                """,
                (uuid, name)
            )
            return True
        except:
            return False


    def remove_device(self, device_id: int) -> bool:
        """
        Полностью удаляет устройство и все связанные данные.
        Отключает проверку внешних ключей для каскадного удаления.
        
        Args:
            device_id (int): ID удаляемого устройства
            
        Returns:
            bool: True при успешном удалении
        """
        try:
            self.cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            
            self.cursor.execute(
                "DELETE FROM tasks WHERE task_device_id = %s",
                (device_id,)
            )
            self.cursor.execute(
                "DELETE FROM rules WHERE rule_device_id = %s",
                (device_id,)
            )
            self.cursor.execute(
                "DELETE FROM actual_data WHERE data_device_id = %s",
                (device_id,)
            )
            self.cursor.execute(
                "DELETE FROM data_history WHERE data_device_id = %s",
                (device_id,)
            )
            self.cursor.execute(
                "DELETE FROM devices WHERE device_id = %s",
                (device_id,)
            )
            
            self.cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            return True
        except:
            return False


    def add_actual_data_line(
        self,
        device_id: int,
        sector: int,
        name: str,
        value: int = 0,
    ) -> bool:
        """
        Добавляет новую запись актуальных данных.
        
        Args:
            device_id (int): ID устройства-источника
            sector (int): Номер сектора данных
            name (str): Название показателя
            value (int): Значение по умолчанию
            
        Returns:
            bool: True при успешном добавлении
        """
        try:
            self.cursor.execute("""
                    INSERT INTO actual_data (
                        data_device_id,
                        data_sector,
                        data_name,
                        data_value
                    ) VALUES (%s, %s, %s, %s)
                """,
                (device_id, sector, name, value)
            )
            return True
        except:
            return False


    def get_actual_data_lines_by_uuid(
        self,
        device_uuid: str
    ) -> list[tuple] | None:
        """
        Получает все актуальные показатели для устройства.
        
        Args:
            device_uuid (str): UUID устройства
            
        Returns:
            list[tuple] | None: Список записей или None при ошибке
        """
        device_id = self.get_device_id(device_uuid)
        if device_id:
            self.cursor.execute("""
                SELECT *
                FROM actual data
                WHERE data_device_id = %s
                """,
                (device_id,)
            )
        else:
            return None


    def get_actual_data_line(
        self,
        data_id: int,
    ) -> tuple | None:
        """
        Получает конкретную запись актуальных данных по ID.
        
        Args:
            data_id (int): ID записи данных
            
        Returns:
            tuple | None: Запись данных или None
        """
        self.cursor.execute("""
            SELECT *
            FROM actual data
            WHERE data_id = %s
            """,
            (data_id,)
        )
        return self.cursor.fetchone()


    def update_actual_data_line(
        self,
        data_id: int,
        value: int = 0
    ) -> bool:
        """
        Обновляет значение в записи актуальных данных.
        
        Args:
            data_id (int): ID обновляемой записи
            value (int): Новое значение
            
        Returns:
            bool: True при успешном обновлении
        """
        try:
            self.cursor.execute("""
                    UPDATE actual_data 
                    SET data_value = %s, 
                        data_timestamp = NOW()
                    WHERE data_id = %s
                """,
                (value, data_id)
            )
            return True
        except:
            return False


    def remove_actual_data_line(self, data_id: int) -> bool:
        """
        Удаляет запись актуальных данных и связанные правила.
        
        Args:
            data_id (int): ID удаляемой записи
            
        Returns:
            bool: True при успешном удалении
        """
        try:
            self.cursor.execute(
                "DELETE FROM rules WHERE rule_data_id = %s",
                (data_id,)
            )
            self.cursor.execute(
                "DELETE FROM actual_data WHERE data_id = %s",
                (data_id,)
            )
            return True
        except:
            return False

    
    def add_rule(
        self,
        data_id: int,
        condition: int,
        value: int,
        device_id: int,
        message: str,
    ) -> bool:
        """
        Добавляет новое правило обработки данных.
        
        Args:
            data_id (int): ID связанных данных
            condition (int): Тип условия (1-4)
            value (int): Пороговое значение
            device_id (int): ID целевого устройства
            message (str): Сообщение для устройства
            
        Returns:
            bool: True при успешном добавлении
        """
        try:
            self.cursor.execute("""
                    INSERT INTO rules (
                        rule_data_id,
                        rule_condition,
                        rule_value,
                        rule_device_id,
                        rule_message
                    ) VALUES (%s, %s, %s, %s, %s)
                """,
                (data_id, condition, value, device_id, message)
            )
            return True
        except:
            return False
    

    def get_rules(self, device_uuid: str) -> list[tuple] | None:
        """
        Получает все правила для указанного устройства.
        
        Args:
            device_uuid (str): UUID устройства
            
        Returns:
            list[tuple] | None: Список правил или None
        """
        device_id = self.get_device_id(device_uuid)
        if device_id:
            self.cursor.execute(
                """
                SELECT *
                FROM rules
                WHERE rule_device_id = %s
                """,
                (device_id,)
            )
            return self.cursor.fetchall()
        else:
            return None


    def remove_rule(self, rule_id: int) -> bool:
        """
        Удаляет правило по ID.
        
        Args:
            rule_id (int): ID удаляемого правила
            
        Returns:
            bool: True при успешном удалении
        """
        try:
            self.cursor.execute(
                "DELETE FROM rules WHERE rule_id = %s",
                (rule_id,)
            )
            return True
        except:
            return False


    def add_task(
        self,
        task_device_id: int,
        task_message: str
    ) -> bool:
        """
        Добавляет новую задачу для устройства.
        
        Args:
            task_device_id (int): ID устройства-получателя
            task_message (str): Сообщение задачи
            
        Returns:
            bool: True при успешном добавлении
        """
        try:
            self.cursor.execute(
                """
                INSERT INTO tasks (task_device_id, task_message)
                VALUES (%s, %s)
                """,
                (task_device_id, task_message)
            )
            return True
        except:
            return False
    

    def get_task_message(
        self,
        task_device_uuid: str
    ) -> str | None:
        """
        Получает и удаляет первую задачу для устройства.
        
        Args:
            task_device_uuid (str): UUID устройства
            
        Returns:
            str | None: Сообщение задачи или None
        """
        device_id = self.get_device_id(task_device_uuid)
        if device_id:
            self.cursor.execute(
                """
                SELECT task_message
                FROM tasks
                WHERE task_device_id = %s
                """,
                (device_id,)
            )
            task = cursor.fetchone()
            if task:
                self.remove_task(task[0])
                return task[2]
            else:
                return None
        else:
            return None


    def remove_task(self, task_id: int) -> bool:
        """
        Удаляет задачу по ID.
        
        Args:
            task_id (int): ID удаляемой задачи
            
        Returns:
            bool: True при успешном удалении
        """
        try:
            self.cursor.execute(
                "DELETE FROM tasks WHERE task_id = %s",
                (task_id,)
            )
            return True
        except:
            return False
    
    
    def task_exists(self, device_id: int) -> bool:
        """
        Проверяет наличие задач для устройства.
        
        Args:
            device_id (int): ID устройства
            
        Returns:
            bool: True если задачи существуют
        """
        self.cursor.execute(
            """
            SELECT *
            FROM tasks
            WHERE task_device_id = %s
            """,
            (device_id,)
        )
        return True if self.cursor.fetchone() else False