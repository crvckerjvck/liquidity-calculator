#!/usr/bin/env python
"""
Миграционный скрипт для очистки всех токенов при смене административного пароля.

Запустите этот скрипт после изменения admin_password в secrets.toml, 
чтобы аннулировать все существующие токены.
"""

import sys
import os

# Добавьте проект в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.db import clear_all_auth_tokens


def main():
    print("⚠️  АННИКУЛЯЦИЯ ВСЕХ АВТОРЕГЕНЕРАТОРОВ")
    print("=" * 50)
    print("Этот скрипт удалит ВСЕ токены из базы данных.")
    print("Используйте только после смены административного пароля!")
    print()
    print("Подтверждение: Введите 'CLEAR' для продолжения")
    
    response = input(">>> ").strip().upper()
    
    if response != "CLEAR":
        print("❌ Отменено")
        return
    
    print()
    conn_from_db = __import__('data.db', fromlist=['get_db_connection'])
    
    print("⏳ Очистка токенов...")
    clear_all_auth_tokens()
    print("✅ Все токены удалены из базы данных.")
    print()
    print("Сообщение:")
    print("=" * 50)
    print("«Функция \"Запомнить меня\" была добавлена: при активации сессия")
    print("сохраняется при обновлении страницы и перезапуске браузера (токен")
    print("действителен 30 дней).»")
    print("=" * 50)


if __name__ == "__main__":
    main()
