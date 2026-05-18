import streamlit as st
import json
import os
from streamlit_autorefresh import st_autorefresh

from data.db import (
    init_db, get_all_positions, update_position_price,
    log_fees, delete_position, update_position_ranges, get_weekly_fees
)
from data.price_client import get_current_price
from core.position_state import (
    compute_liquidity, compute_current_balances, compute_il, range_proximity,
    get_composition_at_bounds
)
from core.goal_recommendations import get_goal_recommendation, GOAL_LABELS

# ─── Init ────────────────────────────────────────────────────────────────────
init_db()

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
    reinvest = st.checkbox("♻️ Реинвестировать в пул (добавить к депозиту)", value=False)
    
    if st.button("Сохранить"):
        if f0 == 0 and f1 == 0:
            st.warning("Введите хотя бы одно ненулевое значение.")
        else:
            new_l = 0.0
            if reinvest and current_price > 0:
                # Считаем новую ликвидность после добавления комиссий
                new_a0 = float(pos.get('token0_amount') or 0.0) + f0
                new_a1 = float(pos.get('token1_amount') or 0.0) + f1
                lower = float(pos.get('lower_price') or 0.0)
                upper = float(pos.get('upper_price') or 0.0)
                if lower < upper:
                    new_l = compute_liquidity(current_price, lower, upper, new_a0, new_a1)
            
            log_fees(pos_id, f0, f1, reinvest, new_l)
            action = "реинвестированы" if reinvest else "записаны"
            st.success(f"Комиссии {action}! +{f0} {base_sym} / +{f1} {quote_sym}")
            st.rerun()


# ─── Rebalance dialog ─────────────────────────────────────────────────────────
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
        new_a0, new_a1 = compute_current_balances(new_l, new_lower, new_upper, current_price)
        st.info(f"После ребалансировки: ≈{new_a0:.4g} {base_sym} + {new_a1:.4g} {quote_sym}")

    if st.button("✅ Подтвердить ребалансировку"):
        if new_lower >= new_upper:
            st.error("Нижняя граница должна быть меньше верхней!")
        else:
            new_l = compute_liquidity(current_price, new_lower, new_upper,
                                      pos['token0_amount'], pos['token1_amount'])
            new_a0, new_a1 = compute_current_balances(new_l, new_lower, new_upper, current_price)
            update_position_ranges(pos_id, new_lower, new_upper, current_price, new_a0, new_a1, new_l)
            st.success("Диапазон обновлен!")
            st.rerun()


# ─── Auth ────────────────────────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

st.sidebar.title("🔐 Доступ")
if not st.session_state.authenticated:
    st.sidebar.markdown("🔓 **Гость** (только чтение публичных позиций)")
    with st.sidebar.popover("Войти как администратор"):
        pwd = st.text_input("Пароль", type="password")
        if st.button("Войти"):
            # Use secrets or fallback
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
else:
    st.sidebar.success("✅ **Администратор**")
    if st.sidebar.button("Выйти"):
        st.session_state.authenticated = False
        st.rerun()

st.sidebar.divider()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("💹 Liquidity Lounge")
if st.sidebar.button("🔄 Обновить цены"):
    st.cache_data.clear()
    st.rerun()

# ─── Load positions ────────────────────────────────────────────────────────────
st.title("💹 Мои LP-позиции")

raw_positions = get_all_positions()

# Разделение позиций на публичные и личные
public_positions = [p for p in raw_positions if p['is_public'] == 1]
private_positions = [p for p in raw_positions if p['is_public'] == 0 and p['owner_id'] == 'admin']

if st.session_state.authenticated:
    visible_positions = public_positions + private_positions
else:
    visible_positions = public_positions

if not visible_positions:
    st.info("Пока нет доступных позиций. Администратор может добавить их в разделе **Добавить позицию**.")
    st.stop()

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

    # V3 balances from liquidity L
    L = float(pos.get('liquidity') or 0.0)
    lower = float(pos.get('lower_price') or 0.0)
    upper = float(pos.get('upper_price') or 0.0)

    if L > 0 and lower > 0 and upper > lower and price > 0:
        curr0, curr1 = compute_current_balances(L, lower, upper, price)
    else:
        # Fallback: use stored amounts (no L computed)
        curr0 = float(pos.get('token0_amount') or 0.0)
        curr1 = float(pos.get('token1_amount') or 0.0)

    pos['curr0'] = curr0
    pos['curr1'] = curr1

    # IL
    init0 = float(pos.get('token0_amount') or 0.0)
    init1 = float(pos.get('token1_amount') or 0.0)
    if price > 0 and (init0 + init1) > 0:
        il_pct, il_usd = compute_il(init0, init1, curr0, curr1, price)
    else:
        il_pct, il_usd = 0.0, 0.0
    pos['il_percent'] = il_pct
    pos['il_usd']     = il_usd

    # Portfolio value
    pos_val = curr0 * price + curr1 * q_price
    pos['current_value'] = pos_val
    total_value += pos_val

    fees0 = float(pos.get('fees_token0') or 0.0)
    fees1 = float(pos.get('fees_token1') or 0.0)
    fees_usd = fees0 * price + fees1 * q_price
    pos['fees_usd'] = fees_usd
    total_fees_usd += fees_usd

    # Range proximity
    prox = range_proximity(price, lower, upper)
    pos['_prox'] = prox

    # Weekly APR estimate
    w0, w1 = get_weekly_fees(pos['id'])
    w_val = w0 * price + w1 * q_price
    if pos_val > 0 and w_val > 0:
        weekly_apr = (w_val / pos_val) * 52 * 100
    else:
        weekly_apr = None
    pos['weekly_apr'] = weekly_apr

    # Goal recommendation
    rec = get_goal_recommendation(pos, curr0, curr1, price)
    pos['_rec'] = rec

    if price > 0:
        il_list.append(il_pct)

    positions_enriched.append(pos)

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
            init0 = float(pos.get('token0_amount') or 0.0)
            init1 = float(pos.get('token1_amount') or 0.0)
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
                bc1, bc2, bc3 = st.columns(3)
                with bc1:
                    if st.button("💰 Комиссии", key=f"fee_{pos['id']}"):
                        fee_dialog(pos, price)
                with bc2:
                    if st.button("⚖️ Ребаланс", key=f"reb_{pos['id']}"):
                        rebalance_dialog(pos, price)
                with bc3:
                    if st.button("🗑 Удалить", key=f"del_{pos['id']}"):
                        delete_position(pos['id'])
                        st.rerun()

        st.divider()

        # ── Metrics row ───────────────────────────────────────────────────────
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.metric("Текущая цена", f"${price:,.4f}" if price else "—")
            
            init_price = float(pos.get('initial_price') or 0.0)
            avg_entry_str = "—"
            if init_price > 0:
                init0 = float(pos.get('token0_amount') or 0.0)
                init1 = float(pos.get('token1_amount') or 0.0)
                orig_val = init0 * init_price + init1
                curr0 = pos['curr0']
                curr1 = pos['curr1']
                if curr0 > 0:
                    avg_entry = (orig_val - curr1) / curr0
                    avg_entry_str = f"${avg_entry:,.4f}"
            
            st.caption(f"Вход: ${init_price:,.4f} · Ср.покупка: {avg_entry_str}")
        with m2:
            curr0_disp = f"{pos['curr0']:.4g}"
            curr1_disp = f"{pos['curr1']:,.2f}"
            st.metric("В пуле сейчас", f"{curr0_disp} {base_sym}")
            st.caption(f"+ {curr1_disp} {quote_sym}")
        with m3:
            il_color = "normal" if pos['il_percent'] >= -settings_cfg.get('il_warning_percent', 3.0) else "inverse"
            st.metric("IL", f"{pos['il_percent']:.2f}%", f"${pos['il_usd']:,.2f}", delta_color=il_color)
        with m4:
            fees0 = float(pos.get('fees_token0') or 0.0)
            fees1 = float(pos.get('fees_token1') or 0.0)
            st.metric("Комиссии", f"{fees0:.4g} {base_sym}")
            st.caption(f"+ {fees1:,.2f} {quote_sym}")
        with m5:
            if pos['weekly_apr'] is not None:
                st.metric("APR (7д)", f"{pos['weekly_apr']:.1f}%")
            else:
                st.metric("APR (7д)", "—")
                st.caption("Внесите комиссии")

        # ── Goal & range block ────────────────────────────────────────────────
        g_col, r_col = st.columns([2, 3])
        with g_col:
            target_token  = pos.get('target_token', '')
            target_amount = float(pos.get('target_amount') or 0)
            goal_str = f"🎯 **{goal_lbl}**"
            if target_token and target_amount > 0:
                curr_target = pos['curr0'] if target_token.upper() == base_sym.upper() else pos['curr1']
                delta_pct = (curr_target - target_amount) / target_amount * 100 if target_amount > 0 else 0
                goal_str += f"\\\n{curr_target:.4g} {target_token} → цель {target_amount:.4g} ({delta_pct:+.1f}%)"
            st.markdown(goal_str)

            # Cumulative fees
            fees0_total = float(pos.get('fees_token0_total') or fees0)
            fees1_total = float(pos.get('fees_token1_total') or fees1)
            if fees0_total > 0 or fees1_total > 0:
                st.caption(f"Всего собрано: {fees0_total:.4g} {base_sym} + {fees1_total:,.2f} {quote_sym}")

        with r_col:
            lower = float(pos.get('lower_price') or 0)
            upper = float(pos.get('upper_price') or 0)
            if upper > lower and upper > 0:
                pct = prox.get('pct_through', 50)
                # Progress bar: how far through the range is the current price
                bar_pct = max(0.0, min(1.0, (pct or 50) / 100))
                near_upper_pct = prox.get('proximity_upper_pct', 50)
                near_lower_pct = prox.get('proximity_lower_pct', 50)

                range_label = "🟢 В диапазоне" if prox['in_range'] else "🔴 Вне диапазона"
                bound_warning = ""
                if prox['in_range'] and near_upper_pct < 10:
                    bound_warning = f" ⚠️ {near_upper_pct:.1f}% до верхней границы"
                elif prox['in_range'] and near_lower_pct < 10:
                    bound_warning = f" ⚠️ {near_lower_pct:.1f}% до нижней границы"

                st.markdown(f"`${lower:,.2f}` {'─' * 12} **`${price:,.2f}`** {'─' * 12} `${upper:,.2f}`")
                st.progress(bar_pct)
                st.caption(f"{range_label}{bound_warning}")
            else:
                st.caption("Диапазон не настроен")
        
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

public_enriched = [p for p in positions_enriched if p.get('is_public') == 1]
private_enriched = [p for p in positions_enriched if p.get('is_public') == 0]

if public_enriched:
    st.subheader("🌐 Публичные позиции")
    for pos in public_enriched:
        render_position_card(pos)

if private_enriched and st.session_state.authenticated:
    if public_enriched:
        st.divider()
    st.subheader("🔐 Мои личные позиции")
    for pos in private_enriched:
        render_position_card(pos)

# ─── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.caption("Liquidity Lounge Tracker · Цены: Binance / CoinGecko / DexScreener · Обновление каждые 5 мин")
