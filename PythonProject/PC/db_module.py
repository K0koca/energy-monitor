import sqlite3
from datetime import datetime


class EnergyDataDB:
    def __init__(self, db_name="energy_monitor.db"):
        self.db_name = db_name
        self.init_table()

    def init_table(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS energy_record (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_time TEXT,
                voltage REAL,
                current REAL,
                power REAL
            )
            ''')

    def save_energy(self, voltage, current, power):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO energy_record (record_time, voltage, current, power)
                VALUES (?, ?, ?, ?)
                ''', (now, voltage, current, power))
            return True
        except Exception as e:
            print(f"数据库写入失败: {e}")
            return False

    def get_all_data(self):
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM energy_record ORDER BY id DESC")
                return cursor.fetchall()
        except Exception as e:
            print(f"数据查询失败: {e}")
            return []

    def clear_all_data(self):
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM energy_record")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='energy_record'")
            print("数据库已清空")
            return True
        except Exception as e:
            print(f"清空数据失败: {e}")
            return False