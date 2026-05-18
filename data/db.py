import sqlite3
import os
import math
from typing import Optional
from models.position import Position

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data_storage', 'positions.db')


def get_db_connection():
    """Возвращает соединение с БД."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализирует базу данных и создает таблицу positions."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        network TEXT NOT NULL,
        dex TEXT NOT NULL,
        pair TEXT NOT NULL,
        lower_price REAL NOT NULL,
        upper_price REAL NOT NULL,
        token0_amount REAL NOT NULL,
        token1_amount REAL NOT NULL,
        fees_token0 REAL DEFAULT 0,
        fees_token1 REAL DEFAULT 0,
        wallet_address TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_price REAL DEFAULT 0.0
    )
    ''')
    conn.commit()
    conn.close()
    migrate_db()


def migrate_db():
    """Безопасно добавляет новые колонки и таблицы (идемпотентно)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Новые колонки для трекинга с целями
    new_columns = [
        ("initial_price",       "REAL DEFAULT 0.0"),
        ("goal",                "TEXT DEFAULT 'maximize_fees'"),
        ("target_token",        "TEXT DEFAULT ''"),
        ("target_amount",       "REAL DEFAULT 0.0"),
        ("fees_token0_total",   "REAL DEFAULT 0.0"),
        ("fees_token1_total",   "REAL DEFAULT 0.0"),
        ("liquidity",           "REAL DEFAULT 0.0"),
        ("is_public",           "INTEGER DEFAULT 0"),
        ("owner_id",            "TEXT DEFAULT 'admin'"),
    ]
    for col_name, col_def in new_columns:
        try:
            cursor.execute(f"ALTER TABLE positions ADD COLUMN {col_name} {col_def}")
        except sqlite3.OperationalError:
            pass  # Already exists

    # Таблица истории комиссий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fees_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL,
            token0_amount REAL DEFAULT 0,
            token1_amount REAL DEFAULT 0,
            reinvested INTEGER DEFAULT 0,
            logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
        )
    ''')

    # Синхронизация fees_token0_total из legacy fees_token0 (one-time migration)
    cursor.execute('''
        UPDATE positions
        SET fees_token0_total = fees_token0,
            fees_token1_total = fees_token1
        WHERE fees_token0_total = 0 AND (fees_token0 > 0 OR fees_token1 > 0)
    ''')

    # Миграция существующих позиций: сделать их публичными по умолчанию
    # We only do this if we actually added the column just now, but SQLite ALTER TABLE doesn't return status.
    # Instead, we can check if there are any records with owner_id = 'admin' AND is_public = 0.
    # Wait, any new private position will also have this!
    # Let's use a migrations table to ensure we only run this once.
    cursor.execute("CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY)")
    cursor.execute("SELECT name FROM _migrations WHERE name = 'make_legacy_public'")
    if not cursor.fetchone():
        cursor.execute("UPDATE positions SET is_public = 1, owner_id = 'public'")
        cursor.execute("INSERT INTO _migrations (name) VALUES ('make_legacy_public')")

    conn.commit()
    conn.close()


# ─── Position CRUD ───────────────────────────────────────────────────────────

def add_position(
    network: str, dex: str, pair: str,
    lower_price: float, upper_price: float,
    token0_amount: float, token1_amount: float,
    fees_token0: float = 0, fees_token1: float = 0,
    wallet_address: Optional[str] = None,
    initial_price: float = 0.0,
    goal: str = 'maximize_fees',
    target_token: str = '',
    target_amount: float = 0.0,
    liquidity: float = 0.0,
    is_public: bool = False,
    owner_id: str = "admin",
):
    """Добавляет новую позицию в БД."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO positions 
        (network, dex, pair, lower_price, upper_price, token0_amount, token1_amount,
         fees_token0, fees_token1, wallet_address,
         initial_price, goal, target_token, target_amount,
         fees_token0_total, fees_token1_total, liquidity, is_public, owner_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        network, dex, pair, lower_price, upper_price,
        token0_amount, token1_amount, fees_token0, fees_token1, wallet_address,
        initial_price, goal, target_token, target_amount,
        fees_token0, fees_token1, liquidity, int(is_public), owner_id
    ))
    conn.commit()
    conn.close()


def get_all_positions():
    """Получает все позиции из БД."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM positions ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_positions_objs():
    """Получает все позиции как объекты Position."""
    return [Position.from_tuple(row) for row in get_all_positions()]


def get_position_by_id(pos_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM positions WHERE id = ?', (pos_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def update_position_price(pos_id: int, price: float):
    """Обновляет сохраненную цену."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE positions SET last_price = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?',
        (price, pos_id)
    )
    conn.commit()
    conn.close()


def delete_position(pos_id: int):
    """Удаляет позицию и связанные логи комиссий."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM fees_log WHERE position_id = ?', (pos_id,))
    cursor.execute('DELETE FROM positions WHERE id = ?', (pos_id,))
    conn.commit()
    conn.close()


def update_position_goal(pos_id: int, goal: str, target_token: str, target_amount: float):
    """Обновляет цель позиции."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE positions SET goal = ?, target_token = ?, target_amount = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?',
        (goal, target_token, target_amount, pos_id)
    )
    conn.commit()
    conn.close()


def update_position_ranges(pos_id: int, lower: float, upper: float, initial_price: float, token0: float, token1: float, liquidity: float):
    """Обновляет диапазон и токены после ребалансировки."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE positions 
        SET lower_price = ?, upper_price = ?, initial_price = ?,
            token0_amount = ?, token1_amount = ?, liquidity = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (lower, upper, initial_price, token0, token1, liquidity, pos_id))
    conn.commit()
    conn.close()


# ─── Fee Logging ─────────────────────────────────────────────────────────────

def log_fees(pos_id: int, token0_amount: float, token1_amount: float, reinvested: bool = False, new_liquidity: float = 0.0):
    """
    Записывает новую запись комиссий.
    Если reinvested=True — прибавляет к базовым token0_amount/token1_amount, обнуляет накопленные.
    Если reinvested=False — только прибавляет к fees_token0_total/fees_token1_total.
    Если передан new_liquidity — обновляет его в базе (важно для реинвестирования).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Лог
    cursor.execute('''
        INSERT INTO fees_log (position_id, token0_amount, token1_amount, reinvested)
        VALUES (?, ?, ?, ?)
    ''', (pos_id, token0_amount, token1_amount, 1 if reinvested else 0))

    if reinvested:
        update_liquidity_sql = ", liquidity = ?" if new_liquidity > 0 else ""
        sql = f'''
            UPDATE positions
            SET token0_amount = token0_amount + ?,
                token1_amount = token1_amount + ?,
                fees_token0 = fees_token0 + ?,
                fees_token1 = fees_token1 + ?,
                fees_token0_total = fees_token0_total + ?,
                fees_token1_total = fees_token1_total + ?,
                last_updated = CURRENT_TIMESTAMP
                {update_liquidity_sql}
            WHERE id = ?
        '''
        params = [token0_amount, token1_amount, token0_amount, token1_amount,
                  token0_amount, token1_amount]
        if new_liquidity > 0:
            params.append(new_liquidity)
        params.append(pos_id)
        
        cursor.execute(sql, tuple(params))
    else:
        cursor.execute('''
            UPDATE positions
            SET fees_token0 = fees_token0 + ?,
                fees_token1 = fees_token1 + ?,
                fees_token0_total = fees_token0_total + ?,
                fees_token1_total = fees_token1_total + ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (token0_amount, token1_amount, token0_amount, token1_amount, pos_id))

    conn.commit()
    conn.close()


def get_fees_log(pos_id: int) -> list:
    """Возвращает историю записи комиссий для позиции."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM fees_log WHERE position_id = ? ORDER BY logged_at DESC',
        (pos_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_weekly_fees(pos_id: int) -> tuple:
    """Возвращает сумму комиссий за последние 7 дней."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COALESCE(SUM(token0_amount), 0), COALESCE(SUM(token1_amount), 0)
        FROM fees_log
        WHERE position_id = ? AND logged_at >= datetime('now', '-7 days')
    ''', (pos_id,))
    row = cursor.fetchone()
    conn.close()
    return (float(row[0]), float(row[1])) if row else (0.0, 0.0)



