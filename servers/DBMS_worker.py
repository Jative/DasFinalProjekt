import mysql.connector


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
            if err.errno == mysql.connector.errorcode.ER_BAD_DB_ERROR:
                self.create_db(db_name)
            else:
                raise


    def create_db(self, db_name: str) -> None:
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
                rule_device_id INTEGER,
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


    def add_device(self, uuid: str, name: str) -> bool:
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


    def update_actual_data_line(
        self,
        data_id: int,
        value: int = 0
    ) -> bool:
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


    def remove_rule(self, rule_id: int) -> bool:
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


    def remove_task(self, task_id: int) -> bool:
        try:
            self.cursor.execute(
                "DELETE FROM tasks WHERE task_id = %s",
                (task_id,)
            )
            return True
        except:
            return False
