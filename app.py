import streamlit as st
import json
import os
from streamlit_autorefresh import st_autorefresh

from data.db import (
    initialize_database, get_all_positions, update_position_price,
    log_fees, delete_position, update_position_ranges,
    update_position_status, update_position_date, get_fees_log, delete_fee_log,
    clear_all_fees, get_custom_positions, soft_delete_custom_position,
    hard_delete_custom_position, update_custom_position, update_position_visibility,
    update_v2_pool_visibility, update_custom_visibility,
    update_custom_body, update_custom_fees,
    get_v2_pools, get_public_v2_pools, get_public_custom_positions,
    update_position_current_balances,
    update_v2_pool, soft_delete_v2_pool, hard_delete_v2_pool,
    log_v2_fees, get_v2_fees_log, clear_all_v2_fees,
    update_v2_pool_status, update_custom_position_status,
    update_v2_pool_balances
)
from data.price_client import get_current_price
from core.position_state import (
    compute_liquidity, compute_il, range_proximity,
    get_composition_at_bounds, compute_liquidity_delta
)
from core.il_calculator import calculate_il_v2, compute_v3_balances
from core.goal_recommendations import get_goal_recommendation, GOAL_LABELS
from core.metrics import calculate_actual_apy

# Import date and datetime for APR calculation
from datetime import date, datetime

from data.db import initialize_database

# Инициализация базы данных при запуске приложения
initialize_database()

st.set_page_config(
    page_title="Liquidity Lounge Tracker",
    page_icon="💹",
    layout="wide"
)

# Auto-refresh every 5 minutes
st_autorefresh(interval=300_000, key="auto_refresh")


def load_settings():
    path = os.path.join(os.path.dirname(__file__), 'config', 'settings.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"il_warning_percent": 3.0, "il_critical_percent": 5.0}

settings_cfg = load_settings()

STABLES = {'USDC', 'USDT', 'DAI', 'FRAX', 'BUSD'}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def is_stable(symbol: str) -> bool:
    return symbol.upper() in STABLES


def token1_price_of(pair: str, token0_price: float) -> float:
    """Returns USD price of token1. Assumes stable=1.0, otherwise returns 0."""
    q = pair.split('/')[1].upper() if '/' in pair else 'USDC'
    return 1.0 if is_stable(q) else 0.0


def severity_color(severity: str) -> str:
    return {'info': '#2ecc71', 'warning': '#f39c12', 'critical': '#e74c3c'}.get(severity, '#aaa')


# ─── Visibility dialog ────────────────────────────────────────────────────────
@st.dialog("🌐 Публичность V3 позиции")
def visibility_dialog(pos: dict):
    current = bool(pos.get('is_public'))
    new_val = st.checkbox("Публичная позиция (видна гостям)", value=current)
    if st.button("Сохранить"):
        update_position_visibility(pos['id'], int(new_val))
        st.rerun()


@st.dialog("✏️ Изменить текущие балансы")
def edit_balance_dialog(pos: dict):
    st.markdown(f"**{pos['pair']}**")
    base_sym = pos['pair'].split('/')[0] if '/' in pos['pair'] else pos['pair']
    quote_sym = pos['pair'].split('/')[1] if '/' in pos['pair'] else 'USDC'
    curr_t0 = float(pos.get('token0_current') or pos.get('token0_amount') or 0.0)
    curr_t1 = float(pos.get('token1_current') or pos.get('token1_amount') or 0.0)
    new_t0 = st.number_input(f"Текущее количество {base_sym}", value=curr_t0, min_value=0.0, format="%.8f")
    new_t1 = st.number_input(f"Текущее количество {quote_sym}", value=curr_t1, min_value=0.0, format="%.2f")
    if st.button("Сохранить"):
        update_position_current_balances(pos['id'], new_t0, new_t1)
        st.success("Балансы обновлены!")
        st.rerun()


# ─── Fee entry dialog ─────────────────────────────────────────────────────────
@st.dialog("💰 Внести комиссии")
def fee_dialog(pos: dict, current_price: float):
    pos_id = pos['id']
    pair = pos['pair']
    base_sym = pair.split('/')[0] if '/' in pair else pair
    quote_sym = pair.split('/')[1] if '/' in pair else 'USDC'

    st.markdown(f"**Введите комиссии для позиции #{pos_id}** ({base_sym}/{quote_sym})")
    f0 = st.number_input(f"{base_sym}", min_value=0.0, value=0.0, format="%.8f")
    f1 = st.number_input(f"{quote_sym}", min_value=0.0, value=0.0, format="%.2f")
    fee_date = st.date_input("Дата получения комиссий", value=date.today())
    reinvest = st.checkbox("♻️ Реинвестировать в пул (добавить к депозиту)", value=False)

    if st.button("Сохранить"):
        if f0 == 0 and f1 == 0:
            st.warning("Введите хотя бы одно ненулевое значение.")
        else:
            delta_l = 0.0
            if reinvest and current_price > 0:
                lower = float(pos.get('lower_price') or 0.0)
                upper = float(pos.get('upper_price') or 0.0)
                if lower < upper:
                    delta_l = compute_liquidity_delta(current_price, lower, upper, f0, f1)

            log_fees(pos_id, f0, f1, reinvest, delta_l, logged_at=fee_date.isoformat())
            action = "реинвестированы" if reinvest else "записаны"
            st.success(f"Комиссии {action}! +{f0} {base_sym} / +{f1} {quote_sym}")
            st.rerun()

    st.divider()
    st.subheader("📋 История комиссий")
    logs = get_fees_log(pos_id)
    if logs:
        for log in logs:
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 1, 1])
            with col1:
                st.text(f"{log['token0_amount']:.6f} {base_sym}")
            with col2:
                st.text(f"{log['token1_amount']:.2f} {quote_sym}")
            with col3:
                st.text(log['logged_at'][:10] if log['logged_at'] else "—")
            with col4:
                st.text("♻️" if log['reinvested'] else "—")
            with col5:
                if st.button("🗑", key=f"del_fee_{log['id']}"):
                    delete_fee_log(log['id'])
                    st.rerun()
    else:
        st.info("История комиссий пуста.")
    
    if st.button("🔴 Очистить всю историю", use_container_width=True, help="Это сбросит счетчики комиссий, но не изменит текущий баланс токенов"):
        clear_all_fees(pos_id)
        st.rerun()

# ─── Edit Custom Position dialog ─────────────────────────────────────────────
@st.dialog("📝 Редактировать позицию")
def edit_custom_position_dialog(cpos: dict):
    with st.form(f"edit_cpos_form_{cpos['id']}"):
        st.write(f"**Протокол:** {cpos['protocol']} ({cpos['type'].title()})")
        new_dep = st.number_input("Депозит", value=float(cpos['amount_deposited']), min_value=0.0, step=0.1, format="%.6f")
        
        new_borrow = cpos['amount_borrowed']
        new_thresh = cpos.get('liquidation_threshold')
        if cpos['type'] == 'lending':
            st.divider()
            new_borrow = st.number_input("Заём", value=float(cpos['amount_borrowed'] or 0.0), min_value=0.0, step=0.1, format="%.6f")
            new_thresh = st.number_input("Порог ликвидации (LTV)", value=float(cpos.get('liquidation_threshold') or 0.75), min_value=0.0, max_value=1.0, step=0.01)
            
        new_apy = st.number_input("APY (%)", value=float(cpos['apy']) if cpos.get('apy') else 0.0, min_value=0.0, step=0.1)
        new_notes = st.text_area("Заметки", value=str(cpos.get('notes') or ""))
        new_is_public = st.checkbox("🌐 Публичная позиция (видна гостям)", value=bool(cpos.get('is_public')))
        
        if st.form_submit_button("Сохранить"):
            update_kwargs = {
                'amount_deposited': new_dep,
                'apy': new_apy,
                'notes': new_notes,
                'is_public': int(new_is_public),
            }
            if cpos['type'] == 'lending':
                update_kwargs['amount_borrowed'] = new_borrow
                update_kwargs['liquidation_threshold'] = new_thresh

            # Синхронизируем initial_body_usd/current_body_usd с депозитом
            if new_dep != float(cpos['amount_deposited']):
                update_kwargs['initial_body_usd'] = new_dep
                update_kwargs['current_body_usd'] = new_dep

            update_custom_position(cpos['id'], **update_kwargs)
            st.rerun()


# ─── V2 Dialogs ───────────────────────────────────────────────────────────────
@st.dialog("📝 Редактировать V2 пул")
def edit_v2_pool_dialog(pos: dict):
    with st.form(f"edit_v2_form_{pos['id']}"):
        st.write(f"**Пул:** {pos['pair']} ({pos['dex']})")
        new_t0 = st.number_input(f"Начальное кол-во {pos['token0_symbol']}", value=float(pos['token0_initial']), min_value=0.0, step=0.01)
        new_t1 = st.number_input(f"Начальное кол-во {pos['token1_symbol']}", value=float(pos['token1_initial']), min_value=0.0, step=0.01)
        new_price = st.number_input("Цена входа (Token0 в Token1)", value=float(pos['initial_price']), min_value=0.0, format="%.6f")
        new_apy = st.number_input("APY (%)", value=float(pos['apy'] or 0.0), min_value=0.0, step=0.1)
        
        goal_opts = list(GOAL_LABELS.keys())
        current_goal_idx = goal_opts.index(pos.get('goal', 'balanced')) if pos.get('goal', 'balanced') in goal_opts else 0
        new_goal = st.selectbox("Цель", options=goal_opts, format_func=lambda x: GOAL_LABELS[x], index=current_goal_idx)
        
        new_target_token = st.selectbox("Токен цели", ["", pos['token0_symbol'], pos['token1_symbol']], index=["", pos['token0_symbol'], pos['token1_symbol']].index(pos.get('target_token') or ""))
        target_label = f"Целевое количество {new_target_token}" if new_target_token else "Целевое количество"
        new_target_amount = st.number_input(target_label, value=float(pos.get('target_amount') or 0.0), min_value=0.0, step=1.0)
        
        created_at_str = pos.get('created_at', '')
        try:
            current_date = datetime.strptime(created_at_str.split('T')[0], '%Y-%m-%d').date()
        except Exception:
            current_date = date.today()
        new_date = st.date_input("Дата открытия", value=current_date)
        
        new_is_public = st.checkbox("🌐 Публичный пул (виден гостям)", value=bool(pos.get('is_public')))
        
        if st.form_submit_button("Сохранить"):
            update_v2_pool(
                pos['id'],
                token0_initial=new_t0,
                token1_initial=new_t1,
                initial_price=new_price,
                apy=new_apy,
                goal=new_goal,
                target_token=new_target_token,
                target_amount=new_target_amount,
                created_at=new_date.isoformat(),
                is_public=int(new_is_public)
            )
            st.rerun()

@st.dialog("💰 Комиссии V2 пула")
def v2_fee_dialog(pos: dict):
    pos_id = pos['id']
    st.markdown(f"**Комиссии для V2 пула #{pos_id}** ({pos['pair']})")
    f0 = st.number_input(f"{pos['token0_symbol']}", min_value=0.0, value=0.0, format="%.6f")
    f1 = st.number_input(f"{pos['token1_symbol']}", min_value=0.0, value=0.0, format="%.6f")
    fee_date = st.date_input("Дата получения комиссий", value=date.today())
    
    if st.button("Сохранить комиссии"):
        if f0 == 0 and f1 == 0:
            st.warning("Введите ненулевое значение.")
        else:
            log_v2_fees(pos_id, f0, f1, timestamp=fee_date.isoformat())
            st.success(f"Записано! +{f0} {pos['token0_symbol']} / +{f1} {pos['token1_symbol']}")
            st.rerun()
            
    st.divider()
    st.subheader("📋 История комиссий")
    logs = get_v2_fees_log(pos_id)
    if logs:
        for log in logs:
            c1, c2, c3 = st.columns([2, 2, 2])
            with c1: st.text(f"{log['fee_token0']:.4f} {pos['token0_symbol']}")
            with c2: st.text(f"{log['fee_token1']:.2f} {pos['token1_symbol']}")
            with c3: st.text(log['timestamp'][:10] if log['timestamp'] else "—")
    else:
        st.info("История комиссий пуста.")
        
    if st.button("🔴 Очистить всю историю", use_container_width=True):
        clear_all_v2_fees(pos_id)
        st.rerun()# ─── Rebalance dialog ─────────────────────────────────────────────────────────
@st.dialog("⚖️ Ребалансировка")
def rebalance_dialog(pos: dict, current_price: float):
    pos_id    = pos['id']
    pair      = pos['pair']
    base_sym  = pair.split('/')[0] if '/' in pair else pair
    quote_sym = pair.split('/')[1] if '/' in pair else 'USDC'
    goal      = pos.get('goal', 'maximize_fees')
    rec       = pos.get('_rec', {})

    st.markdown(f"**Текущая цена {base_sym}:** ${current_price:,.4f}")
    st.markdown(f"**Текущий диапазон:** ${pos['lower_price']:,.2f} – ${pos['upper_price']:,.2f}")

    # Default suggested range
    suggested = rec.get('suggested_range') if rec else None
    if suggested:
        def_lower, def_upper = suggested
    else:
        def_lower = current_price * 0.85
        def_upper = current_price * 1.15

    st.divider()
    st.subheader("Новый диапазон")
    col1, col2 = st.columns(2)
    with col1:
        new_lower = st.number_input("Нижняя граница", min_value=0.0, value=float(def_lower), format="%.4f")
    with col2:
        new_upper = st.number_input("Верхняя граница", min_value=0.01, value=float(def_upper), format="%.4f")

    # Preview new balances
    if new_lower < new_upper:
        new_l = compute_liquidity(current_price, new_lower, new_upper,
                                  pos['token0_amount'], pos['token1_amount'])
        new_a0, new_a1 = compute_v3_balances(new_l, new_lower, new_upper, current_price)
        st.info(f"После ребалансировки: ≈{new_a0:.4g} {base_sym} + {new_a1:.4g} {quote_sym}")

    if st.button("✅ Подтвердить ребалансировку"):
        if new_lower >= new_upper:
            st.error("Нижняя граница должна быть меньше верхней!")
        else:
            new_l = compute_liquidity(current_price, new_lower, new_upper,
                                      pos['token0_amount'], pos['token1_amount'])
            new_a0, new_a1 = compute_v3_balances(new_l, new_lower, new_upper, current_price)
            update_position_ranges(pos_id, new_lower, new_upper, current_price, new_a0, new_a1, new_l)
            st.success("Диапазон обновлен!")
            st.rerun()


# ─── Edit Date dialog ─────────────────────────────────────────────────────────
@st.dialog("📅 Изменить дату открытия")
def edit_date_dialog(pos: dict):
    pos_id = pos['id']
    created_at_str = pos.get('created_at', '')
    
    current_date = date.today()
    if created_at_str:
        try:
            current_date = datetime.strptime(created_at_str.split('T')[0], '%Y-%m-%d').date()
        except ValueError:
            pass

    new_date = st.date_input("Новая дата открытия", value=current_date)
    
    if st.button("💾 Сохранить дату"):
        update_position_date(pos_id, new_date.isoformat())
        st.success("Дата открытия обновлена!")
        st.rerun()


# ─── Update Custom Body Dialog ───────────────────────────────────────────────
@st.dialog("💼 Обновить тело депозита")
def update_custom_body_dialog(cpos: dict):
    pos_id = cpos['id']
    current_body = float(cpos.get('current_body_usd') or 0.0)
    initial_body = float(cpos.get('initial_body_usd') or 0.0)
    total_fees = float(cpos.get('total_fees_usd') or 0.0)
    
    st.markdown(f"**{cpos.get('asset_deposited', '—')}** ({cpos.get('type', '—')})")
    st.caption(f"Начальный депозит: ${initial_body:,.2f} | Накопленные комиссии: ${total_fees:,.2f}")
    new_body = st.number_input("Текущее тело депозита (USD)", value=current_body, min_value=0.0, step=10.0, format="%.2f")
    
    if st.button("💾 Сохранить"):
        update_custom_body(pos_id, new_body)
        st.success("Тело депозита обновлено!")
        st.rerun()


# ─── Custom Fee Dialog ───────────────────────────────────────────────────────
@st.dialog("🌐 Публичность кастомной позиции")
def custom_visibility_dialog(cpos: dict):
    current = bool(cpos.get('is_public'))
    new_val = st.checkbox("Публичная позиция (видна гостям)", value=current)
    if st.button("Сохранить"):
        update_custom_visibility(cpos['id'], int(new_val))
        st.rerun()


@st.dialog("💰 Внести комиссии (кастомная позиция)")
def custom_fee_dialog(cpos: dict):
    pos_id = cpos['id']
    total_fees = float(cpos.get('total_fees_usd') or 0.0)
    current_body = float(cpos.get('current_body_usd') or 0.0)
    initial_body = float(cpos.get('initial_body_usd') or 0.0)
    
    st.markdown(f"**{cpos.get('asset_deposited', '—')}** ({cpos.get('type', '—')})")
    st.caption(f"Начальный депозит: ${initial_body:,.2f} | Текущее тело: ${current_body:,.2f}")
    st.caption(f"Текущие накопленные комиссии: **${total_fees:,.2f}**")
    
    additional_fee = st.number_input("Сумма комиссий (USD)", min_value=0.0, value=0.0, step=1.0, format="%.2f")
    reinvest = st.checkbox("♻️ Реинвестировать (добавить к телу депозита)")
    
    if st.button("Сохранить"):
        if additional_fee <= 0:
            st.warning("Введите сумму больше 0.")
        else:
            if reinvest:
                # Прибавляем к телу депозита, комиссии не меняем
                current_body = float(cpos.get('current_body_usd') or 0.0)
                update_custom_body(pos_id, current_body + additional_fee)
            else:
                # Добавляем к комиссиям
                update_custom_fees(pos_id, total_fees + additional_fee)
            st.success(f"Комиссии +${additional_fee:.2f} {'реинвестированы' if reinvest else 'записаны'}!")
            st.rerun()


# ─── Auth ────────────────────────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

st.sidebar.title("🔐 Доступ")

if st.session_state.authenticated:
    st.sidebar.success("✅ **Администратор**")
    if st.sidebar.button("Выйти"):
        st.session_state.authenticated = False
        st.rerun()
else:
    st.sidebar.markdown("🔓 **Гость** (только чтение публичных позиций)")
    with st.sidebar:
        pwd = st.text_input("Пароль", type="password", key="admin_pwd_input")
        if st.button("🔑 Войти"):
            admin_pwd = "admin"
            try:
                admin_pwd = st.secrets.get("admin_password", "admin")
            except:
                pass
            if pwd == admin_pwd:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Неверный пароль")

st.sidebar.divider()
st.sidebar.title("💹 Liquidity Lounge")
if st.sidebar.button("🔄 Обновить цены"):
    st.cache_data.clear()
    st.rerun()

# ─── Load positions ────────────────────────────────────────────────────────────
st.title("💹 Мои LP-позиции")

raw_positions = get_all_positions()

if st.session_state.authenticated:
    visible_positions = raw_positions
else:
    visible_positions = [p for p in raw_positions if p['is_public'] == 1]

if not visible_positions and not st.session_state.get('authenticated', False):
    st.info("Пока нет доступных позиций. Администратор может добавить их в разделе **Добавить позицию**.")
    st.stop()

# ─── Load Custom Positions ───────────────────────────────────────────────────
if st.session_state.authenticated:
    custom_raw = get_custom_positions(status_filter='active')
else:
    custom_raw = get_public_custom_positions()

# ─── Enrich ──────────────────────────────────────────────────────────────────
positions_enriched = []
total_value       = 0.0
total_fees_usd    = 0.0
il_list           = []

for raw in visible_positions:
    pos = dict(raw)
    pair      = pos['pair']
    network   = pos['network']
    base_sym  = pair.split('/')[0] if '/' in pair else pair
    quote_sym = pair.split('/')[1] if '/' in pair else 'USDC'

    # Price
    price = get_current_price(base_sym, network)
    if price:
        update_position_price(pos['id'], price)
    else:
        price = float(pos.get('last_price') or 0.0)
    pos['current_price'] = price

    q_price = token1_price_of(pair, price)

    # V3 balances: вычисляем через compute_v3_balances или fallback на ручные/начальные
    lower = float(pos.get('lower_price') or 0.0)
    upper = float(pos.get('upper_price') or 0.0)
    L = float(pos.get('liquidity') or 0.0)
    if L > 0 and lower > 0 and upper > lower and price > 0:
        curr0, curr1 = compute_v3_balances(L, lower, upper, price)
    else:
        curr0 = float(pos.get('token0_current') or pos.get('token0_amount_initial') or pos.get('token0_amount') or 0.0)
        curr1 = float(pos.get('token1_current') or pos.get('token1_amount_initial') or pos.get('token1_amount') or 0.0)

    pos['curr0'] = curr0
    pos['curr1'] = curr1

    # Используем начальные количества токенов для расчета стоимости входа и IL
    init_price_for_il = float(pos.get('initial_price') or 0.0)
    token0_initial = float(pos.get('token0_amount_initial') or 0.0)
    token1_initial = float(pos.get('token1_amount_initial') or 0.0)
    # Если начальные количества не заданы (старые позиции), используем текущие
    if token0_initial == 0 and token1_initial == 0:
        token0_initial = float(pos.get('token0_amount') or 0.0)
        token1_initial = float(pos.get('token1_amount') or 0.0)
    entry_value = (token0_initial * init_price_for_il + token1_initial) if init_price_for_il > 0 else 0.0
    pos['entry_value'] = entry_value

    # IL: всегда рассчитываем на основе ликвидности, а не ручных балансов
    if price > 0 and entry_value > 0 and init_price_for_il > 0:
        hold_value = token0_initial * price + token1_initial
        # Для IL используем compute_v3_balances (без учёта ручной корректировки)
        if L > 0 and lower > 0 and upper > lower and price > 0:
            il_curr0, il_curr1 = compute_v3_balances(L, lower, upper, price)
        else:
            il_curr0, il_curr1 = token0_initial, token1_initial
        pool_value = il_curr0 * price + il_curr1 * q_price
        if hold_value > 0:
            il_pct = (pool_value - hold_value) / hold_value * 100.0
            il_usd = pool_value - hold_value
        else:
            il_pct, il_usd = 0.0, 0.0
    else:
        il_pct, il_usd = 0.0, 0.0
    pos['il_percent'] = il_pct
    pos['il_usd']     = il_usd

    # Portfolio value
    pos_val = curr0 * price + curr1 * q_price
    pos['current_value'] = pos_val
    
    fees0 = float(pos.get('fees_token0') or 0.0)
    fees1 = float(pos.get('fees_token1') or 0.0)
    fees_usd = fees0 * price + fees1 * q_price
    pos['fees_usd'] = fees_usd

    # Range proximity
    prox = range_proximity(price, lower, upper)
    pos['_prox'] = prox

    # Goal recommendation
    rec = get_goal_recommendation(pos, curr0, curr1, price)
    pos['_rec'] = rec

    # Автоматическое обновление статуса (если не закрыта вручную)
    current_status = pos.get('status', 'active')
    if current_status != 'closed':
        new_status = 'active' if prox['in_range'] else 'inactive'
        if new_status != current_status:
            update_position_status(pos['id'], new_status)
            pos['status'] = new_status

    # Исключаем закрытые позиции из общих итогов
    if pos.get('status') != 'closed':
        total_value += pos_val
        total_fees_usd += fees_usd
        if price > 0:
            il_list.append(il_pct)

    # --- Calculate total APR --- #
    apr_total = None
    created_at_str = pos.get('created_at')
    entry_val_for_apr = pos.get('entry_value') or 0.0

    if created_at_str:
        try:
            created_date = datetime.strptime(created_at_str.split('T')[0], '%Y-%m-%d').date()
            days_active = (date.today() - created_date).days
            
            if days_active > 0 and entry_val_for_apr > 0:
                fees_token0_total = float(pos.get('fees_token0_total') or 0.0)
                fees_token1_total = float(pos.get('fees_token1_total') or 0.0)
                total_fees_usd_calc = (fees_token0_total * price) + (fees_token1_total * q_price)

                apr_total = (total_fees_usd_calc / entry_val_for_apr) * (365 / days_active) * 100
                apr_total = max(0, min(200, apr_total))
        except ValueError:
            pass
    pos['apr_total'] = apr_total
    # --- End calculate total APR --- #

    positions_enriched.append(pos)

# ─── Enrich Custom Positions & Calculate Actual APY ─────────────────────────
custom_enriched = []
for raw in custom_raw:
    cpos = dict(raw)
    
    # Calculate actual APY
    initial_body = float(cpos.get('initial_body_usd') or 0.0)
    current_body = float(cpos.get('current_body_usd') or 0.0)
    total_fees = float(cpos.get('total_fees_usd') or 0.0)
    
    created_at = cpos.get('created_at')
    if created_at:
        try:
            created_date = datetime.strptime(created_at[:10], '%Y-%m-%d').date()
            days_active = (date.today() - created_date).days
        except ValueError:
            days_active = 1
    else:
        days_active = 1
    
    if initial_body > 0 and days_active >= 1 and total_fees >= 0:
        actual_apy = calculate_actual_apy(initial_body, current_body, total_fees, days_active)
    else:
        actual_apy = None
    
    cpos['actual_apy'] = actual_apy
    cpos['total_fees_usd'] = total_fees
    
    # Custom APY display
    indicated_apy = cpos.get('apy') or 0.0
    if actual_apy is not None:
        color = "green" if actual_apy > indicated_apy else "red"
        cpos['apy_text'] = f"<span style='color:{color}; font-weight:bold;'> APY (указанный): {indicated_apy:.1f}% | APY (фактический): {actual_apy:.1f}%</span>"
    else:
        cpos['apy_text'] = f"APY (указанный): {indicated_apy:.1f}%"
    
    # Prices
    price_dep = get_current_price(cpos['asset_deposited'], cpos['network'])
    val_dep = cpos['amount_deposited'] * (price_dep or 0.0)
    
    price_borrow = 0.0
    val_borrow = 0.0
    if cpos['asset_borrowed']:
        price_borrow = get_current_price(cpos['asset_borrowed'], cpos['network']) or 0.0
        val_borrow = cpos['amount_borrowed'] * price_borrow
        
    cpos['val_dep'] = val_dep
    cpos['val_borrow'] = val_borrow
    cpos['price_dep'] = price_dep
    cpos['price_borrow'] = price_borrow
    
    # Lending metrics
    if cpos['type'] == 'lending' and val_borrow > 0:
        threshold = cpos.get('liquidation_threshold') or 1.0
        cpos['health_factor'] = (val_dep * threshold) / val_borrow if val_borrow > 0 else 0.0
        cpos['current_ltv'] = (val_borrow / val_dep * 100) if val_dep > 0 else 0.0
    
    # Value for total (collateral only for lending as per request)
    total_value += val_dep
    custom_enriched.append(cpos)

# ─── Load & Enrich V2 Pools ──────────────────────────────────────────────────
if st.session_state.authenticated:
    v2_raw = get_v2_pools(status_filter='active')
else:
    v2_raw = get_public_v2_pools()

v2_enriched = []
for raw in v2_raw:
    pos = dict(raw)
    price0 = get_current_price(pos['token0_symbol'], pos['network']) or 0.0
    price1 = get_current_price(pos['token1_symbol'], pos['network']) or 0.0

    # Текущие количества для отображения (ручная корректировка или начальные)
    curr0 = float(pos.get('token0_current') or pos['token0_initial'])
    curr1 = float(pos.get('token1_current') or pos['token1_initial'])

    # IL рассчитывается строго на начальных количествах (не зависит от ручных правок)
    hold_value = pos['token0_initial'] * price0 + pos['token1_initial'] * price1
    current_price_ratio = price0 / price1 if price1 > 0 else 0.0
    il_percent = calculate_il_v2(pos['initial_price'], current_price_ratio) if current_price_ratio > 0 else 0.0

    # Текущая стоимость на основе актуальных балансов (с учётом ручной корректировки)
    pos_val = curr0 * price0 + curr1 * price1

    pos['current_value'] = pos_val
    pos['il_percent'] = il_percent
    pos['il_usd'] = hold_value * (il_percent / 100) if il_percent != 0 else 0.0
    pos['price0'] = price0
    pos['price1'] = price1
    pos['entry_usd'] = pos['token0_initial'] * pos['initial_price'] + pos['token1_initial']

    fees0 = float(pos.get('fees_token0_total') or 0.0)
    fees1 = float(pos.get('fees_token1_total') or 0.0)
    fees_usd = fees0 * price0 + fees1 * price1
    pos['fees_usd'] = fees_usd

    total_value += pos_val
    total_fees_usd += fees_usd

    v2_enriched.append(pos)

# ─── Sidebar summary ─────────────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.subheader("Портфель")
st.sidebar.metric("Стоимость в пулах",  f"${total_value:,.2f}")
st.sidebar.metric("Накоплено комиссий", f"${total_fees_usd:,.2f}")
avg_il = sum(il_list) / len(il_list) if il_list else 0.0
st.sidebar.metric("Средний IL",         f"{avg_il:.2f}%")

critical_count = sum(1 for p in positions_enriched if p['_rec']['severity'] == 'critical')
if critical_count:
    st.sidebar.error(f"⚠️ {critical_count} позиций требуют внимания!")

# ─── Position Cards ───────────────────────────────────────────────────────────
def render_position_card(pos):
    pair      = pos['pair']
    base_sym  = pair.split('/')[0] if '/' in pair else pair
    quote_sym = pair.split('/')[1] if '/' in pair else 'USDC'
    price     = pos['current_price']
    prox      = pos['_prox']
    rec       = pos['_rec']
    goal_lbl  = GOAL_LABELS.get(pos.get('goal', 'maximize_fees'), '—')

    # Card header
    in_range_icon = "🟢" if prox['in_range'] else "🔴"
    sev_color = severity_color(rec['severity'])

    with st.container(border=True):
        # ── Top row: title + action buttons ──────────────────────────────────
        h_col, b_col = st.columns([4, 2])
        with h_col:
            pos_val = pos.get('current_value', 0.0)
            init0 = float(pos.get('token0_amount_initial') or pos.get('token0_amount') or 0.0)
            init1 = float(pos.get('token1_amount_initial') or pos.get('token1_amount') or 0.0)
            init_p = float(pos.get('initial_price') or 0.0)
            initial_val = (init0 * init_p + init1) if init_p > 0 else 0.0
            fees_usd = pos.get('fees_usd', 0.0)
            total_with_fees = pos_val + fees_usd
            pnl_usd = total_with_fees - initial_val if initial_val > 0 else 0.0
            pnl_pct = (pnl_usd / initial_val * 100) if initial_val > 0 else 0.0
            pnl_sign = "+" if pnl_usd >= 0 else ""
            pnl_color = "#2ecc71" if pnl_usd >= 0 else "#e74c3c"

            val_str = f"${total_with_fees:,.2f}" if total_with_fees > 0 else "—"
            pnl_str = f"<span style='color:{pnl_color};font-size:0.85rem;font-weight:600'>{pnl_sign}${pnl_usd:,.2f} ({pnl_sign}{pnl_pct:.1f}%)</span>" if initial_val > 0 else ""

            public_badge = ""
            if pos.get('is_public') == 1:
                public_badge = "<span style='margin-left: 10px; padding: 2px 8px; background: #2980b9; border-radius: 4px; font-size: 0.7rem;'>🌐 PUBLIC</span>"

            st.markdown(
                f"<div style='display: flex; align-items: center; justify-content: space-between;'>"
                f"<h3 style='margin:0; font-size: 1.25rem; font-family: inherit;'>{in_range_icon} {pair} &nbsp;"
                f"<span style='font-size:0.75rem;color:#888;font-weight:normal;'>{pos['network'].upper()} · {pos['dex']}</span>{public_badge}"
                f"</h3>"
                f"<div style='display: flex; align-items: center;'>"
                f"<span style='font-size:1.1rem;color:#fff;font-weight:600;margin-right:15px;'>{val_str}</span>"
                f"{pnl_str}"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True
            )

        with b_col:
            if st.session_state.authenticated:
                bc1, bc2, bc3, bc4, bc5 = st.columns(5)
                with bc1:
                    if st.button("💰 Комиссии", key=f"fee_{pos['id']}"):
                        fee_dialog(pos, price)
                with bc2:
                    if st.button("⚖️ Ребаланс", key=f"reb_{pos['id']}"):
                        rebalance_dialog(pos, price)
                with bc3:
                    if st.button("✏️ Изменить текущие балансы", key=f"bal_{pos['id']}", help="Изменить текущие балансы"):
                        edit_balance_dialog(pos)
                with bc4:
                    if st.button("🌐", key=f"vis_{pos['id']}", help="Изменить публичность"):
                        visibility_dialog(pos)
                with bc5:
                    if st.button("🗑 Удалить", key=f"del_{pos['id']}"):
                        delete_position(pos['id'])
                        st.rerun()
                
                # Кнопка для изменения даты открытия
                if st.button("📅 Изменить дату", key=f"edit_date_{pos['id']}"):
                    edit_date_dialog(pos)

        st.divider()


        # ── Metrics row ───────────────────────────────────────────────────────
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.metric("Текущая цена", f"${price:,.4f}" if price else "—")
            
            # Отображение даты открытия
            created_at_str = pos.get('created_at')
            created_date_display = "—"
            if created_at_str:
                try:
                    created_date_display = datetime.strptime(created_at_str.split('T')[0], '%Y-%m-%d').strftime('%Y-%m-%d')
                except ValueError:
                    created_date_display = created_at_str[:10]
            st.caption(f"📅 Открыта: {created_date_display}")
            
            # Статус позиции
            status = pos.get('status', 'active')
            if status == 'active': st.markdown("🟢 **Активная**")
            elif status == 'inactive': st.markdown("🔴 **Неактивная**")
            elif status == 'closed': st.markdown("⚫ **Закрытая**")

        with m2:
            st.metric("В пуле сейчас", f"{pos['curr0']:.4g} {base_sym}")
            st.caption(f"+ {pos['curr1']:,.2f} {quote_sym}")
            
            # Общая стоимость позиции и PnL
            pos_val = pos.get('current_value', 0.0)
            init_price = float(pos.get('initial_price') or 0.0)
            init0 = float(pos.get('token0_amount_initial') or pos.get('token0_amount') or 0.0)
            init1 = float(pos.get('token1_amount_initial') or pos.get('token1_amount') or 0.0)
            if init_price > 0:
                entry_value = (init0 * init_price + init1)
                entry_str = f"${entry_value:,.2f}"
                pnl_usd = (pos_val + pos.get('fees_usd', 0.0)) - entry_value if entry_value > 0 else 0.0
                pnl_pct = (pnl_usd / entry_value * 100) if entry_value > 0 else 0.0
                pnl_str = f" <span style='color:{'#2ecc71' if pnl_usd >= 0 else '#e74c3c'}; font-size: 0.9rem; font-weight: bold;'> ({'+' if pnl_usd >= 0 else ''}{pnl_pct:.1f}%)</span>" if entry_value > 0 else ""
            else:
                entry_str = "н/д"
                pnl_str = ""
            st.markdown(f"Стоимость входа: {entry_str}")
            fee_usd_value = pos.get('fees_usd', 0.0)
            total_with_fees = pos_val + fee_usd_value
            st.markdown(f"Текущая стоимость позиции ($): ${total_with_fees:,.2f}{pnl_str}", unsafe_allow_html=True)
            
        with m3:
            il_color = "normal" if pos['il_percent'] >= -settings_cfg.get('il_warning_percent', 3.0) else "inverse"
            st.metric("IL", f"{pos['il_percent']:.2f}%", f"${pos['il_usd']:,.2f}", delta_color=il_color)
        with m4:
            st.metric("Комиссии (всего)", f"{float(pos.get('fees_token0_total') or 0.0):.4g} {base_sym}")
            st.caption(f"+ {float(pos.get('fees_token1_total') or 0.0):,.2f} {quote_sym}")
        with m5:
            apr_raw = pos.get('apr_total')
            apr_total_display = f"{apr_raw:.1f}%" if apr_raw is not None else "—"
            
            st.metric("APR (всё время)", apr_total_display)
        
        # Для кастомных позиций: отображение APY (указанный / фактический)
        if pos.get('apy_text'):
            st.caption(pos['apy_text'], unsafe_allow_html=True)
        g_col, r_col = st.columns([2, 3])
        with g_col:
            target_token  = pos.get('target_token', '')
            target_amount = float(pos.get('target_amount') or 0)
            goal_lbl  = GOAL_LABELS.get(pos.get('goal', 'maximize_fees'), '—')
            goal_str = f"🎯 **{goal_lbl}**"
            if target_token and target_amount > 0:
                target_token_upper = target_token.upper()
                if target_token_upper == base_sym.upper():
                    curr_target = pos.get('curr0', 0.0) or pos.get('token0_amount', 0.0) or pos.get('token0_amount_initial', 0.0)
                else:
                    curr_target = pos.get('curr1', 0.0) or pos.get('token1_amount', 0.0) or pos.get('token1_amount_initial', 0.0)
                delta_pct = (curr_target - target_amount) / target_amount * 100 if target_amount > 0 else 0
                goal_str += f"  \n{curr_target:.4g} {target_token} → цель {target_amount:.4g} ({delta_pct:+.1f}%)"
            st.markdown(goal_str)

            # Кнопки управления статусом для админа
            if st.session_state.authenticated:
                st.write("")
                if status != 'closed':
                    if st.button("🔒 Закрыть позицию", key=f"close_{pos['id']}"):
                        from data.db import update_position_status
                        update_position_status(pos['id'], 'closed')
                        st.rerun()
                else:
                    if st.button("🔓 Открыть снова", key=f"reopen_{pos['id']}"):
                        from data.db import update_position_status
                        update_position_status(pos['id'], 'active')
                        st.rerun()

        with r_col:
            # Средняя цена входа и разница
            init_price = float(pos.get('initial_price') or 0.0)
            avg_entry_str = "—"
            delta_str = ""
            if init_price > 0:
                init0 = float(pos.get('token0_amount') or 0.0)
                init1 = float(pos.get('token1_amount') or 0.0)
                orig_val = init0 * init_price + init1
                curr0 = pos['curr0']
                
                if curr0 > 0:
                    avg_entry = (orig_val - init1) / init0 if init0 > 0 else 0
                    avg_entry_str = f"${avg_entry:,.2f}"

                    # Расчет разницы (прибыль/убыток) в USD
                    # Δ = (current_price - average_price) * token0_current
                    delta_usd = (pos.get('current_price', 0.0) - avg_entry) * curr0
                    delta_sign = "+" if delta_usd >= 0 else ""
                    delta_color = "green" if delta_usd >= 0 else "red"
                    delta_str = f"<span style='color:{delta_color}; font-size: 1.1rem; font-weight: bold;'>📈 Δ {delta_sign}${delta_usd:,.2f}</span>"
            
            st.markdown(f"**Средняя цена входа:** {avg_entry_str} за {base_sym}")
            st.markdown(f"**Текущая цена:** ${price:,.4f}")
            if delta_str:
                st.markdown(delta_str, unsafe_allow_html=True)
            
            # Range progress bar
            lower = float(pos.get('lower_price') or 0)
            upper = float(pos.get('upper_price') or 0)
            if upper > lower and upper > 0:
                pct = prox.get('pct_through', 50)
                bar_pct = max(0.0, min(1.0, (pct or 50) / 100))
                range_label = "🟢 В диапазоне" if prox['in_range'] else "🔴 Вне диапазона"
                st.progress(bar_pct)
                st.caption(f"{range_label} (${lower:,.2f} – ${upper:,.2f})")
        
        # ── Composition at bounds ─────────────────────────────────────────────
        liquidity = float(pos.get('liquidity') or 0.0)
        lower = float(pos.get('lower_price') or 0.0)
        upper = float(pos.get('upper_price') or 0.0)
        
        if liquidity > 0:
            bounds = get_composition_at_bounds(liquidity, lower, upper)
            st.markdown("---")
            st.markdown("**Состав на границах (без комиссий):**")
            b1, b2 = st.columns(2)
            with b1:
                st.markdown(f"🔻 **При ${lower:,.2f}:**")
                st.markdown(f"≈ {bounds['lower']['token0']:.4g} {base_sym}")
                st.caption(f"+ {bounds['lower']['token1']:,.2f} {quote_sym}")
            with b2:
                st.markdown(f"🔺 **При ${upper:,.2f}:**")
                st.markdown(f"≈ {bounds['upper']['token0']:.4g} {base_sym}")
                st.caption(f"+ {bounds['upper']['token1']:,.2f} {quote_sym}")

        else:
            st.info("⚠️ Недостаточно данных для расчёта состава на границах (обновите позицию).")

        # ── Recommendation ────────────────────────────────────────────────────
        st.markdown(
            f"<div style='background:rgba(255,255,255,0.04); border-left:4px solid {sev_color}; "
            f"padding:8px 14px; border-radius:4px; margin-top:6px;'>{rec['message']}</div>",
            unsafe_allow_html=True
        )

        st.caption(f"Открыта {pos.get('created_at', '—')[:10]} · "
                   f"Обновлена {pos.get('last_updated', '—')[:16]}")

# ─── V2 Position Card ────────────────────────────────────────────────────────
@st.dialog("🌐 Публичность V2 пула")
def v2_visibility_dialog(pos: dict):
    current = bool(pos.get('is_public'))
    new_val = st.checkbox("Публичная позиция (видна гостям)", value=current)
    if st.button("Сохранить"):
        update_v2_pool_visibility(pos['id'], int(new_val))
        st.rerun()


@st.dialog("✏️ Изменить текущие балансы V2 пула")
def edit_v2_balance_dialog(pos: dict):
    curr0 = float(pos.get('token0_current') or pos['token0_initial'])
    curr1 = float(pos.get('token1_current') or pos['token1_initial'])
    new0 = st.number_input(f"Текущее количество {pos['token0_symbol']}", value=curr0, min_value=0.0, format="%.8f")
    new1 = st.number_input(f"Текущее количество {pos['token1_symbol']}", value=curr1, min_value=0.0, format="%.2f")
    if st.button("Сохранить"):
        update_v2_pool_balances(pos['id'], new0, new1)
        st.rerun()

def render_v2_position_card(pos):
    pair = pos['pair']
    with st.container(border=True):
        h_col, b_col = st.columns([4, 2])
        with h_col:
            pos_val = pos['current_value']
            fees_usd = pos['fees_usd']
            total_with_fees = pos_val + fees_usd
            entry_usd = pos['entry_usd']
            
            pnl_usd = total_with_fees - entry_usd if entry_usd > 0 else 0.0
            pnl_pct = (pnl_usd / entry_usd * 100) if entry_usd > 0 else 0.0
            pnl_sign = "+" if pnl_usd >= 0 else ""
            pnl_color = "#2ecc71" if pnl_usd >= 0 else "#e74c3c"

            public_badge_v2 = ""
            if pos.get('is_public') == 1:
                public_badge_v2 = " 🌐"
            elif st.session_state.authenticated:
                public_badge_v2 = " 🔒"

            st.markdown(
                f"<div style='display: flex; align-items: center; justify-content: space-between;'>"
                f"<h3 style='margin:0; font-size: 1.25rem;'>🌊 {pair}{public_badge_v2} <span style='font-size:0.75rem;color:#888;'>V2 {pos['dex']}</span></h3>"
                f"<div style='display: flex; align-items: center;'>"
                f"<span style='font-size:1.1rem;color:#fff;font-weight:600;margin-right:15px;'>${total_with_fees:,.2f}</span>"
                f"<span style='color:{pnl_color};font-size:0.85rem;font-weight:600'>{pnl_sign}${pnl_usd:,.2f} ({pnl_sign}{pnl_pct:.1f}%)</span>"
                f"</div></div>", unsafe_allow_html=True
            )
        
        with b_col:
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                if st.button("💰", key=f"v2_fee_{pos['id']}", help="Внести комиссии"):
                    v2_fee_dialog(pos)
            with c2:
                if st.button("📝", key=f"v2_edit_{pos['id']}", help="Редактировать пул"):
                    edit_v2_pool_dialog(pos)
            with c3:
                if st.button("🌐", key=f"v2_vis_{pos['id']}", help="Изменить публичность"):
                    v2_visibility_dialog(pos)
            with c4:
                if st.button("🔒", key=f"v2_close_{pos['id']}", help="Закрыть пул"):
                    soft_delete_v2_pool(pos['id'])
                    st.rerun()
            with c5:
                if st.button("✏️", key=f"v2_bal_{pos['id']}", help="Изменить текущие балансы"):
                    edit_v2_balance_dialog(pos)

        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Price 0 / Price 1 (текущая цена)", f"{pos['price0']/pos['price1']:.4g}" if pos['price1'] > 0 else "—")
            st.caption(f"Цена входа: {pos['initial_price']:.4g}")
        with m2:
            disp0 = float(pos.get('token0_current') or pos.get('token0_initial', 0.0))
            disp1 = float(pos.get('token1_current') or pos.get('token1_initial', 0.0))
            st.metric("Депозит", f"{disp0:.4g} {pos['token0_symbol']}")
            st.caption(f"+ {disp1:.4g} {pos['token1_symbol']}")
            # Добавляем общую стоимость позиции (пул + накопленные комиссии)
            total_value = pos['current_value'] + pos.get('fees_usd', 0.0)
            st.markdown(f"💰 **Общая стоимость позиции:** ${total_value:,.2f}")
        with m3:
            st.metric("IL", f"{pos['il_percent']:.2f}%")
        with m4:
            st.metric("Комиссии (всего)", f"{pos['fees_token0_total']:.4g} {pos['token0_symbol']}")
            st.caption(f"+ {pos['fees_token1_total']:.4g} {pos['token1_symbol']}")


def render_custom_position_card(cpos):
    ctype = cpos['type'].replace("_", " ").title()
    protocol = cpos['protocol']
    network = cpos['network'].upper()
    asset_dep = cpos['asset_deposited']
    amount_dep = cpos['amount_deposited']
    val_dep = cpos['val_dep']

    current_body = float(cpos.get('current_body_usd') or 0.0)
    total_fees = float(cpos.get('total_fees_usd') or 0.0)
    initial_body = float(cpos.get('initial_body_usd') or 0.0)
    actual_apy = cpos.get('actual_apy')
    stated_apy = cpos.get('apy')

    # Icons per type
    icons = {
        "lending": "🏦", "v2_pool": "🌊", "vault": "📦",
        "staking": "🥩", "perp_vault": "📉", "delta_neutral": "⚖️"
    }
    icon = icons.get(cpos['type'], "💰")

    with st.container(border=True):
        col_h, col_b = st.columns([4, 2])
        with col_h:
            pub_badge_custom = ""
            if cpos.get('is_public') == 1:
                pub_badge_custom = " 🌐"
            elif st.session_state.authenticated:
                pub_badge_custom = " 🔒"

            st.markdown(
                f"<div style='display: flex; align-items: center;'>"
                f"<h3 style='margin:0;'>{icon} {protocol}{pub_badge_custom} &nbsp;"
                f"<span style='font-size:0.75rem;color:#888;'>{network} · {ctype}</span>"
                f"</h3></div>",
                unsafe_allow_html=True
            )
            st.markdown(f"**Депозит:** {amount_dep:,.4f} {asset_dep} (${val_dep:,.2f})")
        created_str = cpos.get('created_at', '')
        if created_str:
            try:
                created_short = created_str[:10]
            except (ValueError, TypeError):
                created_short = ''
            if created_short:
                st.caption(f"📅 Открыта: {created_short}")

        with col_b:
            if st.session_state.authenticated:
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    if st.button("📝", key=f"edit_c_{cpos['id']}", help="Редактировать"):
                        edit_custom_position_dialog(cpos)
                with c2:
                    if st.button("🌐", key=f"vis_c_{cpos['id']}", help="Изменить публичность"):
                        custom_visibility_dialog(cpos)
                with c3:
                    if st.button("🔒", key=f"close_c_{cpos['id']}", help="Закрыть"):
                        soft_delete_custom_position(cpos['id'])
                        st.rerun()
                with c4:
                    if st.button("🗑", key=f"del_c_{cpos['id']}", help="Удалить"):
                        hard_delete_custom_position(cpos['id'])
                        st.rerun()

        st.divider()
        metrics_cols = st.columns(4)
        with metrics_cols[0]:
            st.metric("Начальный депозит", f"${initial_body:,.2f}" if initial_body else "—")
        with metrics_cols[1]:
            st.metric("Текущее тело", f"${current_body:,.2f}" if current_body else "—")
        with metrics_cols[2]:
            st.metric("Накопленные комиссии", f"${total_fees:,.2f}")
        with metrics_cols[3]:
            pnl = (current_body + total_fees - initial_body) if initial_body > 0 else 0.0
            pnl_pct = (pnl / initial_body * 100) if initial_body > 0 else 0.0
            pnl_color = "#2ecc71" if pnl >= 0 else "#e74c3c"
            st.markdown(
                f"<span style='font-size:0.85rem;color:#888;'>PnL</span><br>"
                f"<span style='font-size:1.1rem;font-weight:600;color:{pnl_color};'>${pnl:+,.2f} ({pnl_pct:+.1f}%)</span>",
                unsafe_allow_html=True
            )

        if cpos['type'] == 'lending':
            st.divider()
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.markdown(f"**Заём**<br>{cpos['amount_borrowed']:,.4f} {cpos['asset_borrowed']} <span style='font-size:0.85em;color:#888'>(${cpos['val_borrow']:,.2f})</span>", unsafe_allow_html=True)
            with m2:
                st.markdown(f"**Liquidation LTV**<br>{(float(cpos.get('liquidation_threshold') or 0.0) * 100):.1f}%", unsafe_allow_html=True)
            with m3:
                hf = cpos.get('health_factor')
                if hf:
                    if hf < 1.0:
                        hf_str = f"**Health Factor**<br><span style='color:#e74c3c'>{hf:.2f} 🔴</span>"
                    elif hf < 1.5:
                        hf_str = f"**Health Factor**<br><span style='color:#f39c12'>{hf:.2f} 🟡</span>"
                    elif hf > 10:
                        hf_str = f"**Health Factor**<br><span style='color:#2ecc71'>>10 🟢</span>"
                    else:
                        hf_str = f"**Health Factor**<br><span style='color:#2ecc71'>{hf:.2f} 🟢</span>"
                    st.markdown(hf_str, unsafe_allow_html=True)

        apy_parts = []
        if actual_apy is not None:
            apy_color = "#2ecc71" if actual_apy >= 0 else "#e74c3c"
            apy_parts.append(f"<span style='color:{apy_color};font-weight:600;'>APY (факт): {actual_apy:.1f}%</span>")
        if stated_apy:
            apy_parts.append(f"APY (указ): {stated_apy:.1f}%")
        if apy_parts:
            st.markdown(" | ".join(apy_parts), unsafe_allow_html=True)

        if cpos.get('notes'):
            st.caption(f"📝 {cpos['notes']}")

        if st.session_state.authenticated:
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("💼 Обновить тело депозита", key=f"body_{cpos['id']}"):
                    update_custom_body_dialog(cpos)
            with col_b:
                if st.button("💰 Внести комиссии", key=f"cfee_{cpos['id']}"):
                    custom_fee_dialog(cpos)

public_enriched = [p for p in positions_enriched if p.get('is_public') == 1]
private_enriched = [p for p in positions_enriched if p.get('is_public') == 0]

if public_enriched:
    st.subheader("🌐 Публичные позиции")
    for pos in public_enriched:
        render_position_card(pos)

if private_enriched and st.session_state.authenticated:
    if public_enriched:
        st.divider()
    st.subheader("🔐 Мои личные V3 позиции")
    for pos in private_enriched:
        render_position_card(pos)

# ─── V2 Pools Section ────────────────────────────────────────────────────────
public_v2 = [p for p in v2_enriched if p.get('is_public') == 1]
private_v2 = [p for p in v2_enriched if p.get('is_public') == 0]

if public_v2:
    if public_enriched or private_enriched:
        st.divider()
    st.subheader("🌊 Публичные V2 пулы")
    for pos in public_v2:
        render_v2_position_card(pos)

if private_v2 and st.session_state.authenticated:
    st.divider()
    st.subheader("🔐 Мои личные V2 пулы")
    for pos in private_v2:
        render_v2_position_card(pos)

# ─── Custom Positions Section ───────────────────────────────────────────────
public_custom = [c for c in custom_enriched if c.get('is_public') == 1]
private_custom = [c for c in custom_enriched if c.get('is_public') == 0]

if public_custom:
    if public_v2 or private_v2 or public_enriched or private_enriched:
        st.divider()
    st.subheader("🌐 Публичные DeFi-позиции")
    for cpos in public_custom:
        render_custom_position_card(cpos)

if private_custom and st.session_state.authenticated:
    st.divider()
    st.subheader("🔐 Мои личные DeFi-позиции")
    for cpos in private_custom:
        render_custom_position_card(cpos)

# ─── Closed Positions Section ────────────────────────────────────────────────
closed_v3 = [pos for pos in positions_enriched if pos.get('status') == 'closed']
if not closed_v3:
    all_raw = get_all_positions()
    closed_v3 = [dict(r) for r in all_raw if 'status' in r.keys() and r['status'] == 'closed']

closed_v2_raw = get_v2_pools(status_filter='closed')
closed_v2 = [dict(r) for r in closed_v2_raw]

closed_custom_raw = get_custom_positions(status_filter='closed')
closed_custom = [dict(r) for r in closed_custom_raw]

if closed_v3 or closed_v2 or closed_custom:
    if public_custom or private_custom:
        st.divider()
    st.subheader("🔒 Закрытые позиции")

    for pos in closed_v3:
        pair = pos.get('pair', '—')
        network = pos.get('network', '')
        dex = pos.get('dex', '')
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"**{pair}** — {network.upper()} · {dex} (V3)")
        with col2:
            if st.button("Открыть снова", key=f"open_v3_{pos['id']}"):
                update_position_status(pos['id'], 'active')
                st.rerun()

    for pos in closed_v2:
        pair = pos.get('pair', '—')
        network = pos.get('network', '')
        dex = pos.get('dex', '')
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"**{pair}** — {network.upper()} · {dex} (V2)")
        with col2:
            if st.button("Открыть снова", key=f"open_v2_{pos['id']}"):
                update_v2_pool_status(pos['id'], 'active')
                st.rerun()

    for cpos in closed_custom:
        protocol = cpos.get('protocol', '—')
        ctype = cpos.get('type', '')
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"**{protocol}** · {ctype}")
        with col2:
            if st.button("Открыть снова", key=f"open_custom_{cpos['id']}"):
                update_custom_position_status(cpos['id'], 'active')
                st.rerun()

# ─── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.caption("Liquidity Lounge Tracker · Цены: Binance / CoinGecko / DexScreener · Обновление каждые 5 мин")
