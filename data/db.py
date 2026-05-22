import sqlite3
import os
import math
import secrets
import time
import functools
from datetime import datetime, date
from typing import Optional
from models.position import Position

# Threading fix to prevent "database is locked" errors
sqlite3.enable_callback_tracebacks(True)

DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'data_storage', 'positions.db')


from contextlib import contextmanager

@contextmanager
def get_db():
    """Предоставляет соединение с БД с управлением транзакциями и таймаутом."""
    conn = sqlite3.connect(DB_PATH, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000") # 15 секунд таймаут
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Database error: {e}") # Логирование ошибки
        raise
    finally:
        conn.close()


def retry_db(func):
    """Декоратор для повторных попыток при блокировке БД."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        for attempt in range(5):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < 4:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise
    return wrapper


@retry_db
def initialize_database():
    """Инициализирует базу данных и выполняет все необходимые миграции."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
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
            last_price REAL DEFAULT 0.0,
            initial_price REAL DEFAULT 0.0,
            goal TEXT DEFAULT 'maximize_fees',
            target_token TEXT DEFAULT '',
            target_amount REAL DEFAULT 0.0,
            fees_token0_total REAL DEFAULT 0.0,
            fees_token1_total REAL DEFAULT 0.0,
            liquidity REAL DEFAULT 0.0,
            is_public INTEGER DEFAULT 0,
            owner_id TEXT DEFAULT 'admin',
            status TEXT DEFAULT 'active',
            token0_amount_initial REAL DEFAULT 0.0,
            token1_amount_initial REAL DEFAULT 0.0
        )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fees_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER,
                token0_amount REAL DEFAULT 0,
                token1_amount REAL DEFAULT 0,
                reinvested INTEGER DEFAULT 0,
                logged_at TEXT,
                FOREIGN KEY(position_id) REFERENCES positions(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                protocol TEXT NOT NULL,
                network TEXT NOT NULL,
                asset_deposited TEXT NOT NULL,
                amount_deposited REAL NOT NULL,
                asset_borrowed TEXT,
                amount_borrowed REAL,
                liquidation_threshold REAL,
                apy REAL,
                notes TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                closed_at TEXT,
                initial_body_usd REAL DEFAULT 0,
                current_body_usd REAL DEFAULT 0,
                total_fees_usd REAL DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                actual_apy REAL DEFAULT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS v2_pools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                network TEXT NOT NULL,
                dex TEXT NOT NULL,
                pair TEXT NOT NULL,
                token0_symbol TEXT NOT NULL,
                token1_symbol TEXT NOT NULL,
                token0_initial REAL NOT NULL,
                token1_initial REAL NOT NULL,
                initial_price REAL NOT NULL,
                created_at TEXT NOT NULL,
                fees_token0_total REAL DEFAULT 0,
                fees_token1_total REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                goal TEXT DEFAULT 'balanced',
                target_token TEXT,
                target_amount REAL,
                apy REAL,
                closed_at TEXT,
                token0_current REAL DEFAULT NULL,
                token1_current REAL DEFAULT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS v2_fees_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                v2_pool_id INTEGER,
                timestamp TEXT,
                fee_token0 REAL,
                fee_token1 REAL,
                FOREIGN KEY(v2_pool_id) REFERENCES v2_pools(id)
            )
        ''')

        # Таблица для токенов аутентификации
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                expires_at INTEGER NOT NULL
            )
        ''')

        # Миграции ALTER TABLE
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
            ("status",              "TEXT DEFAULT 'active'"),
            ("token0_amount_initial","REAL DEFAULT 0.0"),
            ("token1_amount_initial","REAL DEFAULT 0.0"),
        ]
        for col_name, col_def in new_columns:
            try:
                cursor.execute(f"ALTER TABLE positions ADD COLUMN {col_name} {col_def}")
            except sqlite3.OperationalError:
                pass  # Уже существует

        # Миграция для добавления колонки APY кастомных позиций
        custom_cols = ["initial_body_usd", "current_body_usd", "total_fees_usd"]
        for col in custom_cols:
            try:
                cursor.execute(f"ALTER TABLE custom_positions ADD COLUMN {col} REAL DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Уже существует
        
        # Миграция для колонки is_public в custom_positions
        try:
            cursor.execute("ALTER TABLE custom_positions ADD COLUMN is_public INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # Уже существует
        
        # Миграция для колонки is_public в v2_pools
        try:
            cursor.execute("ALTER TABLE v2_pools ADD COLUMN is_public INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # Уже существует
        
        # Миграция для колонок token0_current, token1_current в v2_pools
        try:
            cursor.execute("ALTER TABLE v2_pools ADD COLUMN token0_current REAL DEFAULT NULL")
        except sqlite3.OperationalError:
            pass  # Уже существует
        try:
            cursor.execute("ALTER TABLE v2_pools ADD COLUMN token1_current REAL DEFAULT NULL")
        except sqlite3.OperationalError:
            pass  # Уже существует

        # Синхронизация fees_token0_total из legacy fees_token0 (one-time migration)
        cursor.execute('''
            UPDATE positions
            SET fees_token0_total = fees_token0,
                fees_token1_total = fees_token1
            WHERE fees_token0_total = 0 AND (fees_token0 > 0 OR fees_token1 > 0)
        ''')

        # Миграция существующих позиций: сделать их публичными по умолчанию
        cursor.execute("CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY)")
        cursor.execute("SELECT name FROM _migrations WHERE name = 'make_legacy_public'")
        if not cursor.fetchone():
            cursor.execute("UPDATE positions SET is_public = 1, owner_id = 'public'")
            cursor.execute("INSERT INTO _migrations (name) VALUES ('make_legacy_public')")

        # Миграция для установки статуса 'active' для всех существующих позиций
        cursor.execute("SELECT name FROM _migrations WHERE name = 'set_status_active'")
        if not cursor.fetchone():
            cursor.execute("UPDATE positions SET status = 'active' WHERE status IS NULL OR status = ''")
            cursor.execute("INSERT INTO _migrations (name) VALUES ('set_status_active')")

        # Миграция для установки начальных количеств токенов (для IL)
        cursor.execute("SELECT name FROM _migrations WHERE name = 'set_initial_amounts'")
        if not cursor.fetchone():
            cursor.execute("UPDATE positions SET token0_amount_initial = token0_amount WHERE token0_amount_initial = 0")
            cursor.execute("UPDATE positions SET token1_amount_initial = token1_amount WHERE token1_amount_initial = 0")
            cursor.execute("INSERT INTO _migrations (name) VALUES ('set_initial_amounts')")

        # Миграция: добавить колонки token0_current, token1_current в positions
        cursor.execute("SELECT name FROM _migrations WHERE name = 'add_current_columns'")
        if not cursor.fetchone():
            try:
                cursor.execute("ALTER TABLE positions ADD COLUMN token0_current REAL DEFAULT 0.0")
                cursor.execute("ALTER TABLE positions ADD COLUMN token1_current REAL DEFAULT 0.0")
                # Инициализируем текущие балансы из начальных для старых позиций
                cursor.execute("UPDATE positions SET token0_current = token0_amount_initial, token1_current = token1_amount_initial")
                cursor.execute("INSERT INTO _migrations (name) VALUES ('add_current_columns')")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e):
                    print(f"Warning: Could not add current columns: {e}")

        # Миграция: пересчитать ликвидность для старых позиций, если она равна 0
        cursor.execute("SELECT name FROM _migrations WHERE name = 'recompute_liquidity_v2'")
        if not cursor.fetchone():
            import math
            cursor.execute("SELECT id, lower_price, upper_price, initial_price, token0_amount_initial, token1_amount_initial FROM positions WHERE (liquidity IS NULL OR liquidity = 0) AND lower_price > 0 AND upper_price > lower_price")
            rows = cursor.fetchall()
            for row in rows:
                pos_id, lower, upper, init_price, t0_initial, t1_initial = row
                try:
                    sqrt_low = math.sqrt(lower)
                    sqrt_high = math.sqrt(upper)
                    if init_price <= lower:
                        L = t0_initial / ((1.0 / sqrt_low) - (1.0 / sqrt_high)) if t0_initial > 0 else 0.0
                    elif init_price >= upper:
                        L = t1_initial / (sqrt_high - sqrt_low) if t1_initial > 0 else 0.0
                    else:
                        sqrt_cur = math.sqrt(init_price)
                        amount0_from_L = 1.0 / sqrt_cur - 1.0 / sqrt_high
                        amount1_from_L = sqrt_cur - sqrt_low
                        if amount0_from_L > 0 and amount1_from_L > 0:
                            L0 = t0_initial / amount0_from_L
                            L1 = t1_initial / amount1_from_L
                            L = min(L0, L1)
                        elif amount0_from_L > 0:
                            L = t0_initial / amount0_from_L
                        elif amount1_from_L > 0:
                            L = t1_initial / amount1_from_L
                        else:
                            L = 0.0
                    if L > 0:
                        cursor.execute("UPDATE positions SET liquidity = ? WHERE id = ?", (L, pos_id))
                except Exception as e:
                    print(f"Error recomputing liquidity for pos {pos_id}: {e}")
            cursor.execute("INSERT INTO _migrations (name) VALUES ('recompute_liquidity_v2')")

        # Миграция для кастомных позиций (APY)
        cursor.execute("SELECT name FROM _migrations WHERE name = 'add_custom_apy_columns'")
        if not cursor.fetchone():
            cursor.execute("UPDATE custom_positions SET initial_body_usd = amount_deposited, current_body_usd = amount_deposited WHERE initial_body_usd = 0")
            cursor.execute("INSERT INTO _migrations (name) VALUES ('add_custom_apy_columns')")

        # Миграция: добавить колонку last_updated в custom_positions
        try:
            cursor.execute("ALTER TABLE custom_positions ADD COLUMN last_updated TIMESTAMP")
        except sqlite3.OperationalError:
            pass  # Уже существует

        # Миграция: добавить колонку actual_apy в custom_positions
        try:
            cursor.execute("ALTER TABLE custom_positions ADD COLUMN actual_apy REAL DEFAULT NULL")
        except sqlite3.OperationalError:
            pass  # Уже существует

        # Миграция: пересчитать actual_apy для существующих кастомных позиций
        cursor.execute("SELECT name FROM _migrations WHERE name = 'recalc_actual_apy'")
        if not cursor.fetchone():
            cursor.execute("SELECT id, initial_body_usd, current_body_usd, total_fees_usd, created_at FROM custom_positions WHERE initial_body_usd > 0 AND created_at IS NOT NULL")
            rows = cursor.fetchall()
            for row in rows:
                pos_id = row['id']
                initial = float(row['initial_body_usd'] or 0.0)
                current = float(row['current_body_usd'] or 0.0)
                fees = float(row['total_fees_usd'] or 0.0)
                created_at = row['created_at']
                calc_apy = _recalc_actual_apy(initial, current, fees, created_at)
                if calc_apy is not None:
                    cursor.execute("UPDATE custom_positions SET actual_apy = ? WHERE id = ?", (calc_apy, pos_id))
            cursor.execute("INSERT INTO _migrations (name) VALUES ('recalc_actual_apy')")

        # Миграция: заполнить initial_body_usd/current_body_usd для позиций, где они равны 0
        try:
            cursor.execute("SELECT id FROM custom_positions WHERE (initial_body_usd IS NULL OR initial_body_usd = 0) AND amount_deposited > 0")
            rows = cursor.fetchall()
            for row in rows:
                cursor.execute("UPDATE custom_positions SET initial_body_usd = amount_deposited, current_body_usd = amount_deposited WHERE id = ?", (row['id'],))
        except sqlite3.OperationalError:
            pass

        # Миграция для таблицы auth_tokens
        cursor.execute("SELECT name FROM _migrations WHERE name = 'add_auth_tokens_table'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token TEXT PRIMARY KEY,
                    expires_at INTEGER NOT NULL
                )
            ''')
            cursor.execute("INSERT INTO _migrations (name) VALUES ('add_auth_tokens_table')")

        # Миграция: перенос из position_fees_log (старая схема) в fees_log
        cursor.execute("SELECT name FROM _migrations WHERE name = 'migrate_position_fees_log'")
        if not cursor.fetchone():
            try:
                cursor.execute("SELECT count(*) FROM position_fees_log")
                has_old_table = True
            except sqlite3.OperationalError:
                has_old_table = False
            if has_old_table:
                cursor.execute('''
                    INSERT OR IGNORE INTO fees_log (position_id, token0_amount, token1_amount, logged_at, reinvested)
                    SELECT position_id, fee_token0, fee_token1, timestamp, 0 FROM position_fees_log
                ''')
                cursor.execute("DROP TABLE position_fees_log")
            cursor.execute("INSERT INTO _migrations (name) VALUES ('migrate_position_fees_log')")

        conn.commit()

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
    status: str = "active",
    created_at: str = None,
):
    """Добавляет новую позицию в БД."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO positions 
        (network, dex, pair, lower_price, upper_price, token0_amount, token1_amount,
         fees_token0, fees_token1, wallet_address,
         initial_price, goal, target_token, target_amount,
         fees_token0_total, fees_token1_total, liquidity, is_public, owner_id, status, created_at,
         token0_amount_initial, token1_amount_initial,
         token0_current, token1_current)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        network, dex, pair, lower_price, upper_price,
        token0_amount, token1_amount, fees_token0, fees_token1, wallet_address,
        initial_price, goal, target_token, target_amount,
        fees_token0, fees_token1, liquidity, int(is_public), owner_id, status, created_at,
        token0_amount, token1_amount,
        token0_amount, token1_amount
    ))


def get_all_positions():
    """Получает все позиции из БД."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM positions ORDER BY created_at DESC')
        return cursor.fetchall()


def get_all_positions_objs():
    """Получает все позиции как объекты Position."""
    return [Position.from_tuple(row) for row in get_all_positions()]


def get_position_by_id(pos_id: int):
    """Получает позицию по ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM positions WHERE id = ?', (pos_id,))
        return cursor.fetchone()


@retry_db
def update_position_price(pos_id: int, price: float):
    """Обновляет сохраненную цену."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE positions SET last_price = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?',
            (price, pos_id)
        )


def delete_position(pos_id: int):
    """Удаляет позицию и связанные логи комиссий."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM fees_log WHERE position_id = ?', (pos_id,))
        cursor.execute('DELETE FROM positions WHERE id = ?', (pos_id,))


def update_position_goal(pos_id: int, goal: str, target_token: str, target_amount: float):
    """Обновляет цель позиции."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE positions SET goal = ?, target_token = ?, target_amount = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?',
            (goal, target_token, target_amount, pos_id)
        )


@retry_db
def update_position_ranges(pos_id: int, lower: float, upper: float, initial_price: float, token0: float, token1: float, liquidity: float):
    """Обновляет диапазон и сбрасывает ликвидность."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE positions
            SET lower_price = ?, upper_price = ?, initial_price = ?,
                token0_amount = ?, token1_amount = ?, liquidity = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (lower, upper, initial_price, token0, token1, liquidity, pos_id))


@retry_db
def update_position_status(pos_id: int, status: str):
    """Обновляет статус позиции."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE positions SET status = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?',
            (status, pos_id)
        )


@retry_db
def update_position_date(pos_id: int, created_at: str):
    """Обновляет дату открытия позиции."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE positions SET created_at = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?',
            (created_at, pos_id)
        )


@retry_db
def update_position_current_balances(pos_id: int, token0_current: float, token1_current: float):
    """Обновляет текущие балансы позиции (ручная корректировка)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE positions SET token0_current = ?, token1_current = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?',
            (token0_current, token1_current, pos_id)
        )


@retry_db
def update_v2_pool_status(pool_id: int, status: str):
    """Обновляет статус V2 пула."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE v2_pools SET status = ? WHERE id = ?',
            (status, pool_id)
        )


@retry_db
def update_v2_pool_balances(pool_id: int, token0_current: float, token1_current: float):
    """Обновляет текущие балансы V2 пула (ручная корректировка тела депозита)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE v2_pools SET token0_current = ?, token1_current = ? WHERE id = ?',
            (token0_current, token1_current, pool_id)
        )


@retry_db
def update_custom_position_status(pos_id: int, status: str):
    """Обновляет статус кастомной позиции."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE custom_positions SET status = ? WHERE id = ?',
            (status, pos_id)
        )


# ─── Fee Logging ─────────────────────────────────────────────────────────────

@retry_db
def log_fees(pos_id: int, token0_amount: float, token1_amount: float, reinvested: bool = False, new_liquidity: float = 0.0, logged_at: str = None):
    """
    Записывает новую запись комиссий.
    Если reinvested=True — прибавляет к базовым token0_amount/token1_amount, обнуляет накопленные.
    Если reinvested=False — только прибавляет к fees_token0_total/fees_token1_total.
    Если передан new_liquidity — обновляет его в базе (важно для реинвестирования).
    Если передан logged_at — использует его вместо CURRENT_TIMESTAMP.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Лог
        if logged_at:
            cursor.execute('''
                INSERT INTO fees_log (position_id, token0_amount, token1_amount, reinvested, logged_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (pos_id, token0_amount, token1_amount, 1 if reinvested else 0, logged_at))
        else:
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
                    token0_current = token0_current + ?,
                    token1_current = token1_current + ?,
                    fees_token0 = fees_token0 + ?,
                    fees_token1 = fees_token1 + ?,
                    fees_token0_total = fees_token0_total + ?,
                    fees_token1_total = fees_token1_total + ?,
                    last_updated = CURRENT_TIMESTAMP
                    {update_liquidity_sql}
                WHERE id = ?
            '''
            params = [token0_amount, token1_amount, token0_amount, token1_amount, token0_amount, token1_amount, token0_amount, token1_amount]
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


@retry_db
def delete_fee_log(log_id: int):
    """Удаляет запись из истории комиссий и пересчитывает totals из оставшихся записей."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получим данные записи для коррекции текущих балансов (reinvested)
        cursor.execute('SELECT position_id, token0_amount, token1_amount, reinvested FROM fees_log WHERE id = ?', (log_id,))
        log = cursor.fetchone()
        if not log:
            return

        pos_id, f0, f1, reinvested = log['position_id'], log['token0_amount'], log['token1_amount'], log['reinvested']

        if reinvested:
            # Вычитаем из текущих балансов (реинвестированные суммы были туда добавлены)
            cursor.execute('''
                UPDATE positions
                SET token0_amount = MAX(0, token0_amount - ?),
                    token1_amount = MAX(0, token1_amount - ?),
                    token0_current = MAX(0, token0_current - ?),
                    token1_current = MAX(0, token1_current - ?),
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (f0, f1, f0, f1, pos_id))

        # Удаляем запись
        cursor.execute('DELETE FROM fees_log WHERE id = ?', (log_id,))

        # Пересчитываем все суммы для этой позиции
        cursor.execute('''
            SELECT 
                COALESCE(SUM(CASE WHEN reinvested = 0 THEN CAST(token0_amount AS REAL) ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN reinvested = 0 THEN CAST(token1_amount AS REAL) ELSE 0 END), 0),
                COALESCE(SUM(CAST(token0_amount AS REAL)), 0),
                COALESCE(SUM(CAST(token1_amount AS REAL)), 0)
            FROM fees_log WHERE position_id = ?
        ''', (pos_id,))
        
        row = cursor.fetchone()
        new_curr0 = float(row[0])
        new_curr1 = float(row[1])
        new_total0 = float(row[2])
        new_total1 = float(row[3])

        # Обновляем все колонки в positions
        cursor.execute('''
            UPDATE positions
            SET fees_token0 = ?,
                fees_token1 = ?,
                fees_token0_total = ?,
                fees_token1_total = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (new_curr0, new_curr1, new_total0, new_total1, pos_id))


@retry_db
def clear_all_fees(pos_id: int):
    """Удаляет всю историю комиссий и сбрасывает счетчики в позиции."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Удаление истории комиссий
        cursor.execute('DELETE FROM fees_log WHERE position_id = ?', (pos_id,))
        
        # Сброс счетчиков в positions
        cursor.execute('''
            UPDATE positions
            SET fees_token0 = 0.0,
                fees_token1 = 0.0,
                fees_token0_total = 0.0,
                fees_token1_total = 0.0,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (pos_id,))


def get_fees_log(pos_id: int) -> list:
    """Получает историю комиссий для позиции."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM fees_log WHERE position_id = ? ORDER BY logged_at DESC', (pos_id,))
        return cursor.fetchall()


# ─── Custom Positions CRUD ───────────────────────────────────────────────────

def add_custom_position(
    type: str, protocol: str, network: str,
    asset_deposited: str, amount_deposited: float,
    asset_borrowed: str = None, amount_borrowed: float = 0.0,
    liquidation_threshold: float = None, apy: float = None,
    notes: str = None, is_public: bool = False, created_at: str = None
):
    """Добавляет новую произвольную DeFi-позицию."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO custom_positions (
                type, protocol, network, asset_deposited, amount_deposited,
                asset_borrowed, amount_borrowed, liquidation_threshold, apy,
                status, created_at, notes, is_public,
                initial_body_usd, current_body_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            type, protocol, network, asset_deposited, amount_deposited,
            asset_borrowed, amount_borrowed, liquidation_threshold, apy,
            'active', created_at, notes, int(is_public),
            amount_deposited, amount_deposited
        ))


def get_custom_positions(status_filter: str = None) -> list:
    """Получает кастомные позиции с фильтром по статусу."""
    with get_db() as conn:
        cursor = conn.cursor()
        if status_filter:
            cursor.execute('SELECT * FROM custom_positions WHERE status = ? ORDER BY created_at DESC', (status_filter,))
        else:
            cursor.execute('SELECT * FROM custom_positions ORDER BY created_at DESC')
        return cursor.fetchall()


def update_custom_position(pos_id: int, **kwargs):
    """Обновляет произвольные поля кастомной позиции."""
    if not kwargs:
        return
    with get_db() as conn:
        cursor = conn.cursor()
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        params = list(kwargs.values())
        params.append(pos_id)
        cursor.execute(f'UPDATE custom_positions SET {set_clause} WHERE id = ?', params)


def soft_delete_custom_position(pos_id: int):
    """Переводит позицию в статус 'closed'."""
    update_custom_position(pos_id, status='closed', closed_at=datetime.now().strftime('%Y-%m-%d'))


def hard_delete_custom_position(pos_id: int):
    """Полностью удаляет запись о позиции из БД."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM custom_positions WHERE id = ?', (pos_id,))


def _recalc_actual_apy(initial_body: float, current_body: float, total_fees: float, created_at: str) -> float | None:
    """Рассчитывает фактический APY для кастомной позиции."""
    if initial_body <= 0 or not created_at:
        return None
    try:
        created_date = datetime.strptime(created_at[:10], '%Y-%m-%d').date()
        days_active = (date.today() - created_date).days
    except (ValueError, TypeError):
        days_active = 0
    if days_active < 1:
        return None
    total_gain = (current_body - initial_body) + total_fees
    calc_apy = (total_gain / initial_body) * (365.0 / days_active) * 100.0
    return max(-100.0, min(500.0, calc_apy))


@retry_db
def update_custom_body(pos_id: int, current_body_usd: float):
    """Обновляет текущее тело депозита кастомной позиции и пересчитывает фактический APY."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT initial_body_usd, total_fees_usd, created_at FROM custom_positions WHERE id = ?",
            (pos_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return

        initial_body = float(row['initial_body_usd'] or 0.0)
        total_fees = float(row['total_fees_usd'] or 0.0)
        created_at = row['created_at']

        actual_apy = _recalc_actual_apy(initial_body, current_body_usd, total_fees, created_at)

        cursor.execute(
            'UPDATE custom_positions SET current_body_usd = ?, last_updated = CURRENT_TIMESTAMP, actual_apy = ? WHERE id = ?',
            (current_body_usd, actual_apy, pos_id)
        )


@retry_db
def update_custom_fees(pos_id: int, total_fees_usd: float):
    """Обновляет накопленные комиссии кастомной позиции и пересчитывает фактический APY."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT initial_body_usd, current_body_usd, created_at FROM custom_positions WHERE id = ?",
            (pos_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return

        initial_body = float(row['initial_body_usd'] or 0.0)
        current_body = float(row['current_body_usd'] or 0.0)
        created_at = row['created_at']

        actual_apy = _recalc_actual_apy(initial_body, current_body, total_fees_usd, created_at)

        cursor.execute(
            'UPDATE custom_positions SET total_fees_usd = ?, last_updated = CURRENT_TIMESTAMP, actual_apy = ? WHERE id = ?',
            (total_fees_usd, actual_apy, pos_id)
        )


# ─── V2 Pools CRUD ───────────────────────────────────────────────────────────

@retry_db
def add_v2_pool(
    network: str, dex: str, pair: str,
    token0_symbol: str, token1_symbol: str,
    token0_initial: float, token1_initial: float,
    initial_price: float, created_at: str,
    apy: float = None, goal: str = 'balanced',
    target_token: str = None, target_amount: float = None, is_public: bool = False
):
    """Добавляет новую позицию V2 пула."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO v2_pools (
                network, dex, pair, token0_symbol, token1_symbol,
                token0_initial, token1_initial, initial_price,
                created_at, apy, goal, target_token, target_amount, status, is_public,
                token0_current, token1_current
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            network, dex, pair, token0_symbol, token1_symbol,
            token0_initial, token1_initial, initial_price,
            created_at, apy, goal, target_token, target_amount, 'active', int(is_public),
            token0_initial, token1_initial
        ))

def get_v2_pools(status_filter: str = None) -> list:
    """Получает V2 позиции."""
    with get_db() as conn:
        cursor = conn.cursor()
        if status_filter:
            cursor.execute('SELECT * FROM v2_pools WHERE status = ? ORDER BY created_at DESC', (status_filter,))
        else:
            cursor.execute('SELECT * FROM v2_pools ORDER BY created_at DESC')
        return cursor.fetchall()

@retry_db
def update_v2_pool(pool_id: int, **kwargs):
    """Обновляет поля V2 позиции."""
    if not kwargs:
        return
    with get_db() as conn:
        cursor = conn.cursor()
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        params = list(kwargs.values())
        params.append(pool_id)
        cursor.execute(f'UPDATE v2_pools SET {set_clause} WHERE id = ?', params)

def soft_delete_v2_pool(pool_id: int):
    """Переводит V2 позицию в статус 'closed'."""
    update_v2_pool(pool_id, status='closed', closed_at=datetime.now().strftime('%Y-%m-%d'))

def hard_delete_v2_pool(pool_id: int):
    """Полностью удаляет запись о V2 позиции из БД."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM v2_fees_log WHERE v2_pool_id = ?', (pool_id,))
        cursor.execute('DELETE FROM v2_pools WHERE id = ?', (pool_id,))

@retry_db
def log_v2_fees(pool_id: int, fee_token0: float, fee_token1: float, timestamp: str):
    """Добавляет запись о комиссиях V2 пула и обновляет totals."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO v2_fees_log (v2_pool_id, timestamp, fee_token0, fee_token1)
            VALUES (?, ?, ?, ?)
        ''', (pool_id, timestamp, fee_token0, fee_token1))
        
        cursor.execute('''
            UPDATE v2_pools
            SET fees_token0_total = fees_token0_total + ?,
                fees_token1_total = fees_token1_total + ?
            WHERE id = ?
        ''', (fee_token0, fee_token1, pool_id))

def get_v2_fees_log(pool_id: int) -> list:
    """Получает историю комиссий для V2 пула."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM v2_fees_log
            WHERE v2_pool_id = ?
            ORDER BY timestamp DESC
        ''', (pool_id,))
        return cursor.fetchall()

@retry_db
def clear_all_v2_fees(pool_id: int):
    """Удаляет все логи комиссий для V2 пула и сбрасывает totals."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM v2_fees_log WHERE v2_pool_id = ?', (pool_id,))
        cursor.execute('''
            UPDATE v2_pools
            SET fees_token0_total = 0,
                fees_token1_total = 0
            WHERE id = ?
        ''', (pool_id,))


# ─── Public Visibility Functions ────────────────────────────────────────────

@retry_db
def get_all_public_positions():
    """Получает все публичные позиции (is_public=1)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM positions WHERE is_public = 1 ORDER BY created_at DESC')
        positions = cursor.fetchall()
        cursor.execute('SELECT * FROM v2_pools WHERE is_public = 1 ORDER BY created_at DESC')
        v2_pools = cursor.fetchall()
        cursor.execute('SELECT * FROM custom_positions WHERE is_public = 1 AND status = \'active\' ORDER BY created_at DESC')
        custom = cursor.fetchall()
        return positions + v2_pools + custom


@retry_db
def get_public_v2_pools():
    """Получает только публичные V2 пулы (is_public=1)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM v2_pools WHERE is_public = 1 ORDER BY created_at DESC')
        return cursor.fetchall()


@retry_db
def get_public_custom_positions():
    """Получает только публичные кастомные позиции (is_public=1)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM custom_positions WHERE is_public = 1 AND status = \'active\' ORDER BY created_at DESC')
        return cursor.fetchall()


@retry_db
def update_position_visibility(pos_id: int, is_public: int):
    """Обновляет флаг публичности позиции V3."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE positions SET is_public = ? WHERE id = ?', (is_public, pos_id))


@retry_db
def update_v2_pool_visibility(pool_id: int, is_public: int):
    """Обновляет флаг публичности пула V2."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE v2_pools SET is_public = ? WHERE id = ?', (is_public, pool_id))


@retry_db
def update_custom_visibility(cpos_id: int, is_public: int):
    """Обновляет флаг публичности кастомной позиции."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE custom_positions SET is_public = ? WHERE id = ?', (is_public, cpos_id))


# ─── Auth Token Functions ────────────────────────────────────────────────────

def generate_auth_token() -> str:
    """Генерирует случайный токен для аутентификации."""
    return secrets.token_urlsafe(32)


@retry_db
def save_auth_token(token: str, days_valid: int = 30):
    """Сохраняет токен в БД с указанием срока действия (по умолчанию 30 дней)."""
    with get_db() as conn:
        cursor = conn.cursor()
        expires = int(time.time()) + days_valid * 86400
        cursor.execute(
            "INSERT OR REPLACE INTO auth_tokens (token, expires_at) VALUES (?, ?)",
            (token, expires)
        )


def is_token_valid(token: str) -> bool:
    """Проверяет, что токен существует и не просрочен."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT expires_at FROM auth_tokens WHERE token = ?", (token,))
        row = cursor.fetchone()
        if row and row["expires_at"] > int(time.time()):
            return True
        return False


@retry_db
def delete_auth_token(token: str):
    """Удаляет токен из БД."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))


@retry_db
def clear_all_auth_tokens():
    """Очищает все токены из БД (для аннулирования при смене пароля)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM auth_tokens")

