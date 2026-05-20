import streamlit as st
import pandas as pd
from data.db import get_all_positions, get_v2_pools, get_custom_positions, get_public_v2_pools, get_public_custom_positions
from data.price_client import get_current_price
from core.il_calculator import calculate_il_v2

# Page config
st.set_page_config(page_title="Сводка портфеля", page_icon="📋", layout="wide")

st.title("📋 Сводная таблица портфеля")

# Page visible to all, but filtered by is_public for non-admin
show_all = st.session_state.get('authenticated', False)

# Controls
col_f1, col_f2 = st.columns(2)
with col_f1:
    status_filter = st.selectbox("Статус", ["Все", "Активные", "Закрытые"])
with col_f2:
    if st.button("🔄 Обновить цены и пересчитать"):
        st.cache_data.clear()
        st.rerun()

st.divider()

# --- Collect Data ---
summary_data = []
total_current_value = 0.0
total_pnl = 0.0
total_fees = 0.0

# 1. V3 Positions
if show_all:
    raw_positions = get_all_positions()
else:
    raw_positions = get_all_positions()  # only V3 from positions table
    # filter only rows from positions table that are public
    raw_positions = [p for p in raw_positions if p['is_public']]

for pos in raw_positions:
    if status_filter != "Все":
        if (status_filter == "Активные" and pos['status'] == 'closed') or \
           (status_filter == "Закрытые" and pos['status'] != 'closed'):
            continue
            
    pair = pos['pair']
    base_sym = pair.split('/')[0] if '/' in pair else pair
    price = get_current_price(base_sym, pos['network']) or float(pos['last_price'] or 0.0)
    
    init0 = float(pos['token0_amount'] or 0.0)
    init1 = float(pos['token1_amount'] or 0.0)
    init_p = float(pos['initial_price'] or 0.0)
    entry_usd = (init0 * init_p + init1) if init_p > 0 else 0.0
    
    curr0 = float(pos['token0_amount'] or init0)
    curr1 = float(pos['token1_amount'] or init1)
    current_value = curr0 * price + curr1
    
    fees0 = float(pos['fees_token0_total'] or 0.0)
    fees1 = float(pos['fees_token1_total'] or 0.0)
    fees_usd = fees0 * price + fees1
    
    pnl = current_value + fees_usd - entry_usd if entry_usd > 0 else 0.0
    pnl_pct = (pnl / entry_usd * 100) if entry_usd > 0 else 0.0
    
    summary_data.append({
        "Тип": "V3 LP",
        "Протокол / Пара": f"{pos['dex']} {pair}",
        "Сеть": pos['network'].capitalize(),
        "Вход ($)": entry_usd,
        "Текущая ($)": current_value,
        "Комиссии ($)": fees_usd,
        "PnL ($)": pnl,
        "PnL (%)": pnl_pct,
        "Статус": "🟢 Активная" if pos['status'] != 'closed' else "⚫ Закрыта",
        "ID": f"v3_{pos['id']}"
    })
    if pos['status'] != 'closed':
        total_current_value += current_value
        total_fees += fees_usd
        total_pnl += pnl

# 2. V2 Pools
v2_pools_raw = get_public_v2_pools() if not show_all else get_v2_pools()
for pos in v2_pools_raw:
    if status_filter != "Все":
        if (status_filter == "Активные" and pos['status'] == 'closed') or \
           (status_filter == "Закрытые" and pos['status'] != 'closed'):
            continue

    price0 = get_current_price(pos['token0_symbol'], pos['network']) or 0.0
    price1 = get_current_price(pos['token1_symbol'], pos['network']) or 0.0

    entry_usd = pos['token0_initial'] * pos['initial_price'] + pos['token1_initial']

    current_price_ratio = price0 / price1 if price1 > 0 else 0.0
    il_percent = calculate_il_v2(pos['initial_price'], current_price_ratio) if current_price_ratio > 0 else 0.0
    hold_value = pos['token0_initial'] * price0 + pos['token1_initial'] * price1
    current_value = hold_value * (1 + il_percent/100) if hold_value > 0 else 0.0

    fees0 = float(pos['fees_token0_total'] or 0.0)
    fees1 = float(pos['fees_token1_total'] or 0.0)
    fees_usd = fees0 * price0 + fees1 * price1

    pnl = current_value + fees_usd - entry_usd if entry_usd > 0 else 0.0
    pnl_pct = (pnl / entry_usd * 100) if entry_usd > 0 else 0.0
    
    summary_data.append({
        "Тип": "V2 Pool",
        "Протокол / Пара": f"{pos['dex']} {pos['pair']}",
        "Сеть": pos['network'].capitalize(),
        "Вход ($)": entry_usd,
        "Текущая ($)": current_value,
        "Комиссии ($)": fees_usd,
        "PnL ($)": pnl,
        "PnL (%)": pnl_pct,
        "Статус": "🟢 Активная" if pos['status'] != 'closed' else "⚫ Закрыта",
        "ID": f"v2_{pos['id']}"
    })
    if pos['status'] != 'closed':
        total_current_value += current_value
        total_fees += fees_usd
        total_pnl += pnl

# 3. Custom Positions
custom_raw = get_public_custom_positions() if not show_all else get_custom_positions()
for cpos in custom_raw:
    if status_filter != "Все":
        if (status_filter == "Активные" and cpos['status'] == 'closed') or \
           (status_filter == "Закрытые" and cpos['status'] != 'closed'):
            continue
            
    price_dep = get_current_price(cpos['asset_deposited'], cpos['network']) or 0.0
    val_dep = cpos['amount_deposited'] * price_dep
    
    ctype = cpos['type'].replace("_", " ").title()
    entry_usd = val_dep
    pnl = 0.0
    pnl_pct = 0.0
    
    summary_data.append({
        "Тип": ctype,
        "Протокол / Пара": f"{cpos['protocol']} {cpos['asset_deposited']}",
        "Сеть": cpos['network'].capitalize(),
        "Вход ($)": entry_usd,
        "Текущая ($)": val_dep,
        "Комиссии ($)": 0.0,
        "PnL ($)": pnl,
        "PnL (%)": pnl_pct,
        "Статус": "🟢 Активная" if cpos['status'] != 'closed' else "⚫ Закрыта",
        "ID": f"custom_{cpos['id']}"
    })
    if cpos['status'] != 'closed':
        total_current_value += val_dep

# --- Render ---
if summary_data:
    df = pd.DataFrame(summary_data)
    cols = ["Тип", "Протокол / Пара", "Сеть", "Вход ($)", "Текущая ($)", "Комиссии ($)", "PnL ($)", "PnL (%)", "Статус"]
    df = df[cols]
    
    st.dataframe(
        df.style.format({
            "Вход ($)": "${:,.2f}",
            "Текущая ($)": "${:,.2f}",
            "Комиссии ($)": "${:,.2f}",
            "PnL ($)": "${:,.2f}",
            "PnL (%)": "{:,.2f}%"
        }).apply(
            lambda row: [
                ('color: #2ecc71;' if row['PnL ($)'] > 0 else 'color: #e74c3c;' if row['PnL ($)'] < 0 else '') if pd.notna(row['PnL ($)']) else '',
                ('color: #2ecc71;' if row['PnL (%)'] > 0 else 'color: #e74c3c;' if row['PnL (%)'] < 0 else '') if pd.notna(row['PnL (%)']) else ''
            ],
            axis=1,
            subset=["PnL ($)", "PnL (%)"]
        ),
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Нет данных для отображения.")

st.divider()

# --- Totals ---
col_t1, col_t2, col_t3 = st.columns(3)
with col_t1:
    st.metric("Общая текущая стоимость", f"${total_current_value:,.2f}")
with col_t2:
    st.metric("Общий PnL (Активные)", f"${total_pnl:,.2f}")
with col_t3:
    st.metric("Комиссии (Активные)", f"${total_fees:,.2f}")
