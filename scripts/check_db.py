import sys
sys.path.insert(0, '.')

import sqlite3

DB_PATH = 'd:/VibeCode Projects/LiquidityCalculator/data_storage/positions.db'

# Проверка существования базы данных
try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    
    print("Таблицы в базе данных:")
    for table in tables:
        print(f"  - {table[0]}")
    
    # Подсчет количества записей в каждой таблице
    print("\nКоличество записей:")
    cursor.execute("SELECT COUNT(*) FROM positions")
    print(f"  positions: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM custom_positions")
    print(f"  custom_positions: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM v2_pools")
    print(f"  v2_pools: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM auth_tokens")
    print(f"  auth_tokens: {cursor.fetchone()[0]}")

    conn.close()
    print("\nБаза данных успешно проверена!")
except Exception as e:
    print(f"Ошибка: {e}")
