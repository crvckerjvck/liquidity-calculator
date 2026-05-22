import sqlite3
import os
import time
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data_storage', 'positions.db')

print(f"БД: {DB_PATH}")
print(f"Файл существует: {os.path.exists(DB_PATH)}")

if not os.path.exists(DB_PATH):
    print("Файл БД не найден!")
    exit(1)

max_retries = 5
for attempt in range(1, max_retries + 1):
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()

        # SQLite запрещает DEFAULT CURRENT_TIMESTAMP в ALTER TABLE,
        # поэтому добавляем колонку без дефолта
        cursor.execute("ALTER TABLE custom_positions ADD COLUMN last_updated TIMESTAMP")
        conn.commit()
        print("Колонка last_updated добавлена без дефолта.")

        # Заполняем created_at как last_updated для существующих строк
        cursor.execute("UPDATE custom_positions SET last_updated = created_at WHERE last_updated IS NULL")
        conn.commit()
        print(f"Существующие строки обновлены: last_updated = created_at")

        cursor.execute("PRAGMA table_info(custom_positions)")
        columns = cursor.fetchall()
        print("Текущие колонки custom_positions:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]}){' DEFAULT ' + str(col[4]) if col[4] else ''}")
        conn.close()
        break
    except sqlite3.OperationalError as e:
        conn.close()
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            print("Колонка last_updated уже существует. Всё в порядке.")
            break
        if "database is locked" in str(e) and attempt < max_retries:
            print(f"БД заблокирована, попытка {attempt}/{max_retries}... ждём 2с")
            time.sleep(2)
        else:
            print(f"Ошибка: {e}")
            exit(1)

print("Готово.")