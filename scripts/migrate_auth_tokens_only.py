"""
Emergency migration of auth_tokens without Streamlit

Run: python scripts/migrate_auth_tokens_only.py
"""
import sys
sys.path.insert(0, '.')

import sqlite3
import os

DB_PATH = os.path.join('data', 'data_storage', 'positions.db')

def migrate_auth_tokens_table():
    """Creates auth_tokens table only."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # First create _migrations table if needed
    cursor.execute('CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY)')
    
    # Create auth_tokens table (if not exists)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            expires_at INTEGER NOT NULL
        )
    ''')
    
    # Record migration marker
    cursor.execute("INSERT OR IGNORE INTO _migrations (name) VALUES ('add_auth_tokens_table')")
    
    conn.commit()
    conn.close()
    print("OK: auth_tokens table created")

def fix_custom_apy_migration():
    """Fixes syntax error in custom_apy migration."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if migration marker exists
    cursor.execute("SELECT COUNT(*) FROM _migrations WHERE name = 'add_custom_apy_columns'")
    count = cursor.fetchone()[0]
    
    if count >= 1:
        print("OK: add_custom_apy_columns is already done")
    else:
        cursor.execute("INSERT OR IGNORE INTO _migrations (name) VALUES ('add_custom_apy_columns')")
        conn.commit()
        print("OK: add_custom_apy_columns migration completed")
    
    conn.close()
    return True

if __name__ == '__main__':
    print("Running emergency migration...")
    migrate_auth_tokens_table()
    fix_custom_apy_migration()
    print("Done! You can now restart the Streamlit app.")
