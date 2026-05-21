# Liquidity Lounge Calculator — Техническая спецификация (GitHub Spec Kit)

## 1. Обзор проекта

**Название:** Liquidity Lounge Calculator (LLC)  
**Назначение:** Десктопное/локальное приложение для поставщиков ликвидности (LP) на AMM с концентрированной ликвидностью (Uniswap V3, PancakeSwap V3, Aerodrome, Trader Joe, Raydium CLMM, Cetus). Помогает управлять несколькими позициями в разных сетях, рассчитывает IL, комиссии, даёт рекомендации по ребалансировке и использованию накопленных комиссий.

**Ключевые принципы:**
- Гибридный сбор данных: ручной ввод для всех сетей.
- Локальное хранение данных (SQLite + JSON), никаких облачных сервисов (кроме бесплатных API).
- Работа через веб-интерфейс на Streamlit (запуск локально).
- В будущем — возможность превратить в веб-сервис с подпиской (FastAPI + React).

**Целевые пользователи:** Опытные криптотрейдеры и LP-провайдеры, имеющие позиции на нескольких DEX и сетях.

---

## 2. Технологический стек (определён)

| Компонент | Выбор | Причина |
|-----------|-------|---------|
| Язык | Python 3.10+ | Богатая экосистема для анализа данных и DeFi |
| GUI | Streamlit | Быстрое прототипирование, встроенные графики, простота |
| Хранение | SQLite + JSON | Локально, без сервера, легко мигрировать |
| API для цен | DexScreener (приоритет), CoinGecko (fallback) | DexScreener — реальное время, CoinGecko — резерв |
| API для газа | Etherscan (Ethereum), другие по желанию | Для учёта затрат на ребалансировку |
| Расчёт IL | Точная формула Uniswap V3 | Необходима для корректных рекомендаций |
| Графики | Plotly (интерактивные) + matplotlib (статические) | Streamlit хорошо интегрируется с Plotly |
| Логирование | Стандартный logging | В файл `logs.txt` |

---

## 3. Структура проекта

```
liquidity_lounge_calculator/
├── README.md                  # Общее описание и инструкции
├── SPECIFICATION.md           # Данный документ
├── requirements.txt           # Зависимости Python
├── .env.example               # Шаблон для API ключей
├── launch.bat                 # Для Windows: активация venv и запуск
├── launch.sh                  # Для Linux/Mac
│
├── app.py                     # Главная точка входа Streamlit (Dashboard)
│
├── config/                    # Конфигурационные файлы
│   ├── settings.json          # Настраиваемые пороги (IL, комиссии и т.д.)
│   ├── networks.json          # Список поддерживаемых сетей и DEX
│   └── absolute_min_widths.json # Абсолютные минимумы ширины диапазонов
│
├── core/                      # Основная логика
│   ├── il_calculator.py       # Точный расчёт IL для V3
│   ├── metrics.py             # APR, эффективность, волатильность
│   ├── recommendations.py     # Рекомендательная система
│   └── health_check.py        # Интегральный индикатор (красный/жёлтый/зелёный)
│
├── data/                      # Работа с данными
│   ├── db.py                  # SQLite операции (CRUD позиций, истории)
│   ├── price_client.py        # Цены и волатильность (DexScreener + CoinGecko)
│   └── gas_client.py          # Оценка газа (Etherscan)
│
├── models/                    # Классы данных
│   └── position.py            # Класс Position (с методами расчёта)
│
├── pages/                     # Нативные страницы Streamlit UI
│   ├── 1_Add_Position.py      # Форма добавления/редактирования
│   ├── 2_Analytics.py         # Страница аналитики по позиции
│   └── 3_Settings.py          # Страница настроек
│
├── utils/                     # Вспомогательные модули
│   ├── validators.py          # Проверка ввода чисел
│   ├── logger.py              # Настройка логирования
│   └── helpers.py             # Общие утилиты
│
└── data_storage/              # Локальные файлы (создаются при первом запуске)
    ├── positions.db           # SQLite база данных
    └── cache/                 # Кэш API ответов (JSON)
```

---

## 4. Модели данных

### 4.1. Position (основная сущность)

Таблица SQLite `positions`:

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PRIMARY KEY | Автоинкремент |
| network | TEXT | ethereum, arbitrum, solana и т.д. |
| dex | TEXT | uniswap_v3, pancakeswap_v3, aerodrome, raydium_clmm, cetus |
| pair | TEXT | ETH/USDC, SOL/USDC |
| lower_price | REAL | Нижняя граница диапазона |
| upper_price | REAL | Верхняя граница |
| token0_amount | REAL | Количество базового актива (например, ETH) |
| token1_amount | REAL | Количество стейблкоина (USDC) |
| fees_token0 | REAL | Накопленные комиссии в токене0 (ручной ввод для не-EVM, авто для EVM) |
| fees_token1 | REAL | Накопленные комиссии в токене1 |
| wallet_address | TEXT | Для EVM — адрес кошелька (опционально, для автозагрузки) |
| created_at | TIMESTAMP | Дата открытия позиции |
| last_updated | TIMESTAMP | Последнее обновление данных |

### 4.2. Настройки (JSON)

**config/settings.json** (пример):
```json
{
  "il_warning_percent": 3.0,
  "il_critical_percent": 5.0,
  "fees_reinvest_percent": 10.0,
  "gas_enabled": true,
  "gas_threshold_usd": 5.0,
  "auto_update_interval_minutes": 30,
  "default_volatility_lookback_days": 30
}
```

**config/absolute_min_widths.json**:
```json
{
  "ETH": 600,
  "SOL": 40,
  "AVAX": 8,
  "APT": 3,
  "SUI": 3
}
```

**config/networks.json**:
```json
{
  "ethereum": {"type": "evm", "rpc": "https://...", "debank_chain_id": "eth", "gas_api": "etherscan"},
  "arbitrum": {"type": "evm", "debank_chain_id": "arb", "gas_api": "arbiscan"},
  "solana": {"type": "non_evm", "price_source": "coingecko", "dexes": ["raydium", "orca", "meteora"]},
  "sui": {"type": "non_evm", "dexes": ["cetus", "turbos"]}
}
```

---

## 5. API Интеграции (конкретные эндпоинты)

### 5.1. DeBank API (основной для EVM)
- **Документация:** [DeBank Open API](https://docs.debank.com/open-api)
- **Эндпоинт для LP позиций:** `GET /v1/user/complex_protocol_list?user_address=...`
- **Ответ:** возвращает все позиции в DeFi, включая Uniswap V3, с полями: `pool.id`, `supply_balance` (количество токенов), `reward_balance` (комиссии).
- **Ограничения:** бесплатный тариф — 2000 запросов/день (достаточно).

### 5.2. Zerion API (fallback)
- **Документация:** [Zerion Wallet API](https://developers.zerion.io/)
- **Эндпоинт:** `POST /v1/wallets/:address/positions`
- **Ограничения:** 2000 запросов/месяц на бесплатном тарифе. Использовать только если DeBank не дал данных.

### 5.3. DexScreener API (цены в реальном времени)
- **Документация:** [DexScreener API](https://docs.dexscreener.com/api)
- **Эндпоинт:** `GET /latest/dex/search?q=ETH/USDC`
- **Ответ:** текущая цена, ликвидность, объём за 24h.

### 5.4. CoinGecko API (цены и историческая волатильность)
- **Документация:** [CoinGecko API](https://www.coingecko.com/en/api)
- **Эндпоинт:** `GET /simple/price?ids=ethereum&vs_currencies=usd`
- **Исторические данные:** `GET /coins/ethereum/market_chart?days=30`

### 5.5. Etherscan API (газ)
- **Документация:** [Etherscan Gas Tracker](https://docs.etherscan.io/api-endpoints/gas-tracker)
- **Эндпоинт:** `GET /api?module=gastracker&action=gasoracle`

---

## 6. Алгоритмы и формулы

### 6.1. Точный расчёт IL для Uniswap V3 (концентрированная ликвидность)

**Обозначения:**
- $L$ — ликвидность (инвариант активного диапазона)
- $P$ — текущая цена, $P_a$ — нижняя граница, $P_b$ — верхняя граница
- $S = \sqrt{P}$, $S_a = \sqrt{P_a}$, $S_b = \sqrt{P_b}$
- $x_{real}$ — реальное количество Token0, $y_{real}$ — реальное количество Token1

**Вывод L из начального депозита ($x_{init}$, $y_{init}$ при $P_{entry}$):**

Если $P_{entry} < P_a$ (вход ниже диапазона):
$$L = \frac{x_{init}}{\frac{1}{S_a} - \frac{1}{S_b}}$$

Если $P_{entry} > P_b$ (вход выше диапазона):
$$L = \frac{y_{init}}{S_b - S_a}$$

Если $P_a \le P_{entry} \le P_b$ (вход внутри диапазона):
$$L = \min\left(\frac{x_{init}}{\frac{1}{S_{entry}} - \frac{1}{S_b}},\; \frac{y_{init}}{S_{entry} - S_a}\right)$$

**Расчёт реальных количеств токенов при текущей цене $P$:**

Если $P < P_a$ (цена ниже диапазона — позиция на 100% в Token0):
$$x_{real} = L \cdot \frac{S_b - S_a}{S_a \cdot S_b}$$
$$y_{real} = 0$$

Если $P > P_b$ (цена выше диапазона — позиция на 100% в Token1):
$$x_{real} = 0$$
$$y_{real} = L \cdot (S_b - S_a)$$

Если $P_a \le P \le P_b$ (цена внутри диапазона):
$$x_{real} = L \cdot \frac{S_b - S}{S \cdot S_b}$$
$$y_{real} = L \cdot (S - S_a)$$

**Стоимость позиции:**
$$V_{current} = x_{real} \cdot P + y_{real}$$

**Стоимость HODL (если бы токены просто лежали):**
$$V_{hold} = x_{init} \cdot P + y_{init}$$

**Impermanent Loss:**
$$IL_{usd} = V_{current} - V_{hold}$$
$$IL_{\%} = \frac{IL_{usd}}{V_{hold}} \times 100$$

**Важно:**
- IL отрицателен, когда $V_{current} < V_{hold}$ (цена вне диапазона — позиция терпит убыток относительно HODL).
- При $P < P_a$: $y_{real} = 0$, $x_{real}$ зафиксирован на максимальном значении для диапазона и НЕ меняется при дальнейшем падении цены.
- При $P > P_b$: $x_{real} = 0$, $y_{real}$ зафиксирован на максимальном значении.

Функция в `core/il_calculator.py`:
```python
def calculate_il(current_price, lower_price, upper_price, initial_token0, initial_token1, initial_price=None):
    # возвращает (il_percent, il_dollar, current_value)
```

### 6.2. Историческая волатильность (годовая)

Используем цены закрытия за последние N дней (по умолчанию 30).  
Рассчитываем логарифмические доходности:  
`r_i = ln(price_i / price_{i-1})`  
Волатильность = `std(r) * sqrt(365) * 100%`

### 6.3. Рекомендуемая минимальная ширина диапазона (активная)

`MinWidth = CurrentPrice * max(AbsoluteMinPercent, HistoricalVolatilityFloor, 0.25)`  
Где `AbsoluteMinPercent` из конфига (для ETH 600/price), `HistoricalVolatilityFloor` — многолетний минимум.

### 6.4. Учёт газа при ребалансировке

Оценка стоимости газа (в USD) для `rebalance` транзакции.  
Если `gas_cost > fees_accumulated * 0.2` (или превышает порог из настроек), рекомендация меняется: «Ребалансировка невыгодна из-за газа».

---

## 7. Рекомендательная система (логика)

### 7.1. Для каждой позиции оцениваем:
- **IL %** — текущий
- **Накопленные комиссии** (% от текущего депозита)
- **Статус цены** (внутри диапазона / ниже / выше)
- **Тренд цены** (скользящая средняя за 7 дней)

### 7.2. Правила (пороги из `settings.json`):

| Условие | Действие |
|---------|----------|
| Цена вне диапазона > 24 часов и IL < 3% | «Не ребалансировать, ждать возврата» |
| IL > 3% и комиссии < IL | «Ребалансировка рискованна, копите комиссии» |
| IL > 5% и комиссии > IL*0.8 | «Рекомендуется ребалансировка в новый диапазон» |
| Комиссии > 10% депозита | «Реинвестируйте комиссии в расширение диапазона» |
| Цена упала на 10% за неделю | «Конвертируйте комиссии в актив (ETH) для усреднения» |
| Цена выросла на 10% за неделю | «Фиксируйте комиссии в стейблы» |

### 7.3. Рекомендация нового диапазона при ребалансировке:
- Если нисходящий тренд: сдвинуть диапазон вниз на `volatility_offset%` (например, 15% от текущей цены)
- Если восходящий тренд: сдвинуть вверх
- Новая ширина = текущая ширина или рекомендуемая минимальная (какая больше)

---

## 8. Пользовательский интерфейс (Streamlit)

### 8.1. Главная страница (app.py)
- Таблица всех позиций (колонки: сеть, DEX, пара, диапазон, текущая цена, IL, комиссии, статус)
- Цветовая индикация статуса (зелёный/жёлтый/красный)
- Кнопка «Обновить все» (вызов API)
- Ссылка-кнопка «Добавить позицию» 

### 8.2. Добавление/редактирование (pages/1_Add_Position.py)
- Сначала выбор сети (EVM/non-EVM)
- Если EVM: поле «Адрес кошелька» → кнопка «Загрузить позиции из DeBank»
- Если non-EVM: ручной ввод всех полей
- Валидация: `lower_price < current_price < upper_price` (предупреждение, если нет)

### 8.3. Страница аналитики (pages/2_Analytics.py)
- График цены за 30 дней (Plotly) с заливкой диапазона
- График изменения IL и накопленных комиссий
- Блок рекомендаций (жирный текст)
- Кнопка «Симулятор ребалансировки» (позволяет задать новый диапазон и показывает, как изменится IL)

### 8.4. Страница настроек (pages/3_Settings.py)
- Редактировать пороги (IL warning, IL critical, fees reinvest)
- Ввести API ключи (DeBank, Etherscan, CoinGecko) — сохраняются в `.env`
- Настроить абсолютные минимумы ширины

---

## 9. Инструкция по запуску

```bash
# 1. Создать виртуальное окружение
python -m venv venv

# 2. Активировать (Windows)
venv\Scripts\activate

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Запустить Streamlit
streamlit run app.py
```

---

## 10. Тестирование и логирование

- Логировать все ошибки API в `logs.txt` с уровнем ERROR.
- При каждом обновлении цен писать в лог INFO.
- Юнит-тесты для `il_calculator.py`.

---

## 11. Ограничения и допущения

- Не поддерживаются пулы с несколькими токенами (только пары).
- Для не-EVM сетей только ручной ввод.
- Не рассчитывается сложный IL для пулов с не-стейблкоинами.

---
**Конец спецификации.**
