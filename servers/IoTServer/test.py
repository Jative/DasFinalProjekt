from DBMS_worker import DBMS_worker

db_worker = DBMS_worker("localhost", "root", "123", "GreenHouseLocal")

if not db_worker.created:
    print(db_worker.error)