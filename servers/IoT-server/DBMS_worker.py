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
            CREATE TABLE IF NOT EXISTS sectors (
                sector_id INTEGER NOT NULL AUTO_INCREMENT,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                PRIMARY KEY (sector_id)
            );
            """
        )

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id INTEGER NOT NULL AUTO_INCREMENT,
                device_uuid CHAR(36) UNIQUE,
                device_name VARCHAR(255),
                sector_id INTEGER DEFAULT NULL,
                device_last_communication DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (device_id),
                FOREIGN KEY (sector_id) REFERENCES sectors(sector_id) ON DELETE SET NULL
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS actual_data (
                data_id INTEGER NOT NULL AUTO_INCREMENT,
                data_device_id INTEGER,
                data_name VARCHAR(255),
                data_value INTEGER,
                data_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (data_id),
                UNIQUE KEY device_param (data_device_id, data_name),
                FOREIGN KEY (data_device_id)
                REFERENCES devices(device_id)
                ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_history (
                data_id INTEGER NOT NULL AUTO_INCREMENT,
                data_device_id INTEGER,
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
                rule_device_id INTEGER,
                rule_message VARCHAR(255),
                is_active BOOLEAN DEFAULT TRUE,
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
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER NOT NULL AUTO_INCREMENT,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id)
        );
        """)
        
        self.cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS after_actual_data_insert
            AFTER INSERT ON actual_data
            FOR EACH ROW
            INSERT INTO data_history (
                data_device_id, 
                data_name, 
                data_value, 
                data_timestamp
            )
            VALUES (
                NEW.data_device_id,
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
                    data_name, 
                    data_value, 
                    data_timestamp
                )
                VALUES (
                    NEW.data_device_id, 
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

    def update_device_communication_timestamp(self, device_uuid: str) -> None:
        """
        Обновляет временную метку последней коммуникации устройства до текущего времени.
        
        Args:
            device_uuid (str): Уникальный идентификатор устройства
        """
        self.cursor.execute(
            """
            UPDATE devices
            SET device_last_communication = CURRENT_TIMESTAMP
            WHERE device_uuid = %s
            """,
            (device_uuid,)
        )

    def add_device(self, uuid: str, name: str, sector_id: int = None) -> bool:
        """
        Добавляет новое устройство в базу данных с возможностью привязки к сектору.
        
        Args:
            uuid (str): Уникальный идентификатор устройства
            name (str): Человекочитаемое имя устройства
            sector_id (int, optional): ID сектора для привязки. Defaults to None.
            
        Returns:
            bool: True при успешном добавлении
        """
        try:
            self.cursor.execute("""
                INSERT INTO devices (device_uuid, device_name, sector_id)
                VALUES (%s, %s, %s)
                """,
                (uuid, name, sector_id)
            )
            return True
        except mysql.connector.Error as e:
            return False

    def remove_device(self, device_id: int) -> bool:
        """
        Полностью удаляет устройство и все связанные данные через каскадное удаление.
        
        Args:
            device_id (int): ID удаляемого устройства
            
        Returns:
            bool: True при успешном удалении
        """
        try:
            self.cursor.execute("""
                DELETE FROM devices 
                WHERE device_id = %s
                """,
                (device_id,)
            )
            return self.cursor.rowcount > 0
        except mysql.connector.Error as e:
            return False

    def assign_device_to_sector(self, device_id: int, sector_id: int) -> bool:
        """
        Привязывает устройство к указанному сектору.
        
        Args:
            device_id (int): ID устройства для привязки
            sector_id (int): ID целевого сектора
            
        Returns:
            bool: True при успешном обновлении
        """
        try:
            # Проверяем существование сектора
            self.cursor.execute("""
                SELECT sector_id 
                FROM sectors 
                WHERE sector_id = %s
                """,
                (sector_id,)
            )
            if not self.cursor.fetchone():
                return False

            self.cursor.execute("""
                UPDATE devices 
                SET sector_id = %s 
                WHERE device_id = %s
                """,
                (sector_id, device_id)
            )
            return self.cursor.rowcount > 0
        except mysql.connector.Error as e:
            return False

    def unassign_device_from_sector(self, device_id: int) -> bool:
        """
        Отвязывает устройство от текущего сектора.
        
        Args:
            device_id (int): ID устройства для отвязки
            
        Returns:
            bool: True при успешном обновлении
        """
        try:
            self.cursor.execute("""
                UPDATE devices 
                SET sector_id = NULL 
                WHERE device_id = %s
                """,
                (device_id,)
            )
            return self.cursor.rowcount > 0
        except mysql.connector.Error as e:
            return False

    def add_sector(self, name: str, description: str = None) -> int | None:
        """
        Создает новый сектор (теплицу) в системе.
        
        Args:
            name (str): Уникальное название сектора
            description (str, optional): Описание сектора
            
        Returns:
            int | None: ID созданного сектора или None при ошибке
        """
        try:
            self.cursor.execute(
                """
                INSERT INTO sectors (name, description)
                VALUES (%s, %s)
                """,
                (name, description)
            )
            return self.cursor.lastrowid
        except mysql.connector.Error as e:
            print(f"[Ошибка] Не удалось создать сектор: {e}")
            return None

    def remove_sector(self, sector_id: int) -> bool:
        """
        Удаляет сектор и отвязывает все связанные устройства.
        
        Args:
            sector_id (int): ID удаляемого сектора
            
        Returns:
            bool: True если сектор был удален, False если не существовал
        """
        try:
            self.cursor.execute(
                "DELETE FROM sectors WHERE sector_id = %s",
                (sector_id,)
            )
            return self.cursor.rowcount > 0
        except mysql.connector.Error as e:
            print(f"[Ошибка] Не удалось удалить сектор {sector_id}: {e}")
            return False

    def add_device_data_batch(self, device_uuid: str, data: dict) -> bool:
        """
        Добавляет или обновляет набор показателей для устройства за одну операцию.
        
        Args:
            device_uuid (str): UUID устройства
            data (dict): Словарь {параметр: значение}
                Пример: {"temperature": 25, "humidity": 60}
                
        Returns:
            bool: True при успешном обновлении
        """
        device_id = self.get_device_id(device_uuid)
        if not device_id or not data:
            return False

        try:
            # Формируем пакет данных для вставки
            values = [(device_id, param, value) for param, value in data.items()]
            
            # Используем executemany для пакетной вставки
            self.cursor.executemany(
                """
                INSERT INTO actual_data 
                    (data_device_id, data_name, data_value)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    data_value = VALUES(data_value),
                    data_timestamp = NOW()
                """,
                values
            )
            return True
        except mysql.connector.Error as e:
            print(f"Ошибка пакетного обновления: {e}")
            return False

    def get_actual_data(
        self,
        device_uuid: str,
        parameter_name: str = None
    ) -> dict | None:
        """
        Получает актуальные данные устройства.
        
        Args:
            device_uuid (str): UUID устройства
            parameter_name (str, optional): Фильтр по конкретному параметру
            
        Returns:
            dict: {parameter_name: {'value': int, 'timestamp': datetime}}
            None: Если устройство не найдено
        """
        device_id = self.get_device_id(device_uuid)
        if not device_id:
            return None

        try:
            query = """
                SELECT data_name, data_value, data_timestamp
                FROM actual_data
                WHERE data_device_id = %s
            """
            params = [device_id]
            
            if parameter_name:
                query += " AND data_name = %s"
                params.append(parameter_name)

            self.cursor.execute(query, params)
            results = self.cursor.fetchall()
            
            return {
                row[0]: {
                    'value': row[1],
                    'timestamp': row[2]
                } for row in results
            }
        except mysql.connector.Error as e:
            print(f"Ошибка получения данных: {e}")
            return None

    def add_rule(
        self,
        source_device_uuid: str,
        data_name: str,
        condition: int,
        threshold: int,
        target_device_uuid: str,
        message: str
    ) -> int | None:
        """
        Добавляет новое правило для устройства-исполнителя.
        Разрешено несколько правил для одного устройства.
        
        Args:
            source_device_uuid (str): UUID устройства-источника данных
            data_name (str): Название параметра в actual_data
            condition (int): Тип условия (1: >, 2: < и т.д.)
            threshold (int): Пороговое значение
            target_device_uuid (str): UUID устройства-исполнителя
            message (str): Команда для отправки
            
        Returns:
            int | None: ID созданного правила
        """
        try:
            source_device_id = self.get_device_id(source_device_uuid)
            target_device_id = self.get_device_id(target_device_uuid)
            
            if not source_device_id or not target_device_id:
                return None

            self.cursor.execute(
                """
                SELECT data_id 
                FROM actual_data 
                WHERE data_device_id = %s AND data_name = %s
                LIMIT 1
                """,
                (source_device_id, data_name)
            )
            data_row = self.cursor.fetchone()
            if not data_row:
                return None

            self.cursor.execute(
                """
                INSERT INTO rules (
                    rule_data_id,
                    rule_condition,
                    rule_value,
                    rule_device_id,
                    rule_message
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (data_row[0], condition, threshold, target_device_id, message)
            )
            return self.cursor.lastrowid
            
        except Exception as e:
            return None

    def get_rules_by_target_device(self, target_device_uuid: str) -> list[dict]:
        """
        Получает все правила для устройства-исполнителя.
        
        Args:
            target_device_uuid (str): UUID целевого устройства
            
        Returns:
            list[dict]: Список правил в формате:
            {
                "rule_id": int,
                "source_device": str (UUID источника),
                "parameter": str,
                "condition": int,
                "threshold": int,
                "message": str,
                "is_active": bool
            }
        """
        target_device_id = self.get_device_id(target_device_uuid)
        if not target_device_id:
            return []

        try:
            self.cursor.execute(
                """
                SELECT 
                    r.rule_id,
                    d.device_uuid,
                    a.data_name,
                    r.rule_condition,
                    r.rule_value,
                    r.rule_message,
                    r.is_active
                FROM rules r
                JOIN actual_data a ON r.rule_data_id = a.data_id
                JOIN devices d ON a.data_device_id = d.device_id
                WHERE r.rule_device_id = %s
                """,
                (target_device_id,)
            )
            
            return [
                {
                    "rule_id": row[0],
                    "source_device": row[1],
                    "parameter": row[2],
                    "condition": row[3],
                    "threshold": row[4],
                    "message": row[5],
                    "is_active": row[6]
                }
                for row in self.cursor.fetchall()
            ]
        except Exception as e:
            return []

    def remove_rule(self, rule_id: int) -> bool:
        """
        Удаляет правило по ID.
        
        Args:
            rule_id (int): ID удаляемого правила
            
        Returns:
            bool: True если правило было удалено
        """
        try:
            self.cursor.execute(
                "DELETE FROM rules WHERE rule_id = %s",
                (rule_id,)
            )
            return self.cursor.rowcount > 0
        except Exception as e:
            return False