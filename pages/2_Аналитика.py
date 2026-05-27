import streamlit as st
import pandas as pd
import plotly.express as px
from data.db import get_all_positions_objs
from data.dexscreener_client import get_pool_info
from core.backtest import run_backtest

st.set_page_config(page_title="Аналитика и Бэктест", page_icon="📈", layout="wide")

st.title("📈 Аналитика и Бэктестинг")

# Загрузка позиций
raw_positions = get_all_positions_objs()

if st.session_state.get("authenticated"):
    positions = raw_positions
else:
    positions = [p for p in raw_positions if p.is_public]

if not positions:
    if st.session_state.get("authenticated", False):
        st.info("У вас пока нет созданных позиций. Добавьте их в меню слева.")
    else:
        st.info("Пока нет доступных публичных позиций. Вы можете запустить 'What-if' анализ ниже.")
    selected_pos = None
else:
    pos_options = {f"{p.network} | {p.dex} | {p.pair}": p for p in positions}
    selected_pos_label = st.selectbox("Выберите позицию для анализа", ["-- What-if Анализ --"] + list(pos_options.keys()))
    selected_pos = pos_options.get(selected_pos_label)

st.divider()

# Форма параметров бэктеста
with st.expander("⚙️ Параметры Бэктеста", expanded=True):
    col1, col2, col3 = st.columns(3)
    
    if selected_pos:
        default_pair = selected_pos.pair
        default_network = selected_pos.network
        default_lower = float(selected_pos.lower_price or 0.0)
        default_upper = float(selected_pos.upper_price or 0.0)
        price_ref = float(selected_pos.last_price or 1.0)
        t0 = float(selected_pos.token0_amount or 0.0)
        t1 = float(selected_pos.token1_amount or 0.0)
        default_deposit = t0 * price_ref + t1
        if default_deposit <= 0:
            default_deposit = 1000.0
    else:
        default_pair = "ETH/USDC"
        default_network = "ethereum"
        default_lower = 2000.0
        default_upper = 3000.0
        default_deposit = 1000.0

    with col1:
        pair = st.text_input("Пара", value=default_pair)
        network = st.selectbox("Сеть", ["ethereum", "arbitrum", "optimism", "polygon", "base", "bsc", "solana"], index=0)
        days = st.slider("Период (дней)", 7, 180, 30)
        
    with col2:
        lower = st.number_input("Нижняя граница", value=default_lower, format="%.4f")
        upper = st.number_input("Верхняя граница", value=default_upper, format="%.4f")
        deposit = st.number_input("Депозит ($)", value=default_deposit)
        
    with col3:
        fee_tier = st.selectbox("Fee Tier (%)", [0.01, 0.05, 0.3, 1.0], index=2) / 100.0
        # Пытаемся получить данные пула автоматом
        pool_data = get_pool_info(pair, network)
        if pool_data:
            st.success(f"Данные пула найдены (TVL: ${pool_data['liquidity_usd']:,.0f})")
            tvl_input = st.number_input("Pool TVL ($)", value=pool_data['liquidity_usd'])
            vol_input = st.number_input("Avg 24h Volume ($)", value=pool_data['volume_24h'])
        else:
            st.warning("Пул не найден. Введите данные вручную.")
            tvl_input = st.number_input("Pool TVL ($)", value=10000000.0)
            vol_input = st.number_input("Avg 24h Volume ($)", value=1000000.0)

    run_btn = st.button("📊 Запустить Анализ", width='stretch')

if run_btn:
    with st.spinner("Симуляция работы позиции..."):
        backtest_result = run_backtest(
            symbol=pair,
            lower_price=lower,
            upper_price=upper,
            initial_deposit=deposit,
            days=days,
            fee_tier=fee_tier,
            avg_volume_24h=vol_input,
            pool_tvl=tvl_input
        )
        
        if "error" in backtest_result:
            st.error(backtest_result["error"])
        else:
            # Explanation block
            our_share = backtest_result.get('our_share_pct', 0)
            st.info(
                f"""
**Как считается PnL:**  
• **Стоимость позиции** = IL учтён: как изменился состав {pair} от начального баланса 50/50  
• **Комиссии за день** = объём торгов × fee tier × ваша доля в пуле ({our_share:.4f}%)  
• **Финальная стоимость** = позиция (с IL) + накопленные комиссии  
• **PnL** = финальная стоимость − начальный депозит  

⚠️ *Это симуляция на исторических ценах. Реальные данные о вашей позиции — на главной странице.*
                """
            )
            
            # Metrics
            m1, m2, m3, m4, m5 = st.columns(5)
            # Total PnL
            m1.metric("Общий PnL ($)", f"${backtest_result['net_pnl_usd']:.2f}",
                      delta=f"{backtest_result['net_pnl_perc']:.2f}%")
            
            # HODL PnL (Price impact)
            hodl_pnl = backtest_result['hodl_pnl_usd']
            m2.metric("Рост цены (HODL)", f"${hodl_pnl:.2f}", 
                      help="Сколько бы вы заработали, просто удерживая активы вне пула")
            
            # LP Delta (Fees + IL)
            lp_delta = backtest_result['total_fees'] + backtest_result['il_usd']
            m3.metric("Эффект LP (Комиссии + IL)", f"${lp_delta:.2f}",
                      delta=f"${backtest_result['il_usd']:.2f} IL",
                      help="Чистый результат участия в пуле (Собранные комиссии минус Impermanent Loss)")
            
            m4.metric("Собрано комиссий", f"${backtest_result['total_fees']:.2f}")
            m5.metric("Доля в пуле", f"{our_share:.4f}%")
            
            st.write("---")
            c1, c2 = st.columns(2)
            c1.metric("Финальная стоимость", f"${backtest_result['final_value']:.2f}")
            c2.metric("Загрузка диапазона", f"{backtest_result['range_utilization']:.1f}%")
            
            # Chart
            df = backtest_result["df"]
            
            st.subheader("Визуализация бэктеста")
            
            # График цены и границ
            fig_price = px.line(df, x="day", y="price", title="Движение цены и границы диапазона")
            fig_price.add_hline(y=lower, line_dash="dash", line_color="red", annotation_text="Lower")
            fig_price.add_hline(y=upper, line_dash="dash", line_color="green", annotation_text="Upper")
            st.plotly_chart(fig_price)
            
            # График доходности
            fig_value = px.line(df, x="day", y=["value_hold", "value_pool_no_fees", "total_value"], 
                               title="Сравнение доходности: HODL vs LP",
                               labels={"value": "Стоимость ($)", "variable": "Стратегия"})
            
            # Настройка подписей легенды для понятности
            new_names = {
                "value_hold": "Просто держать (HODL)",
                "value_pool_no_fees": "Позиция в пуле (без комиссий)",
                "total_value": "Итого в пуле (с комиссиями)"
            }
            fig_value.for_each_trace(lambda t: t.update(name = new_names.get(t.name, t.name)))
            st.plotly_chart(fig_value)
            
            st.divider()
            st.subheader("Таблица данных")
            st.dataframe(df.style.highlight_max(axis=0), width='stretch')

st.divider()
st.info("Профессиональный совет: Высокое использование диапазона (Range Utilization) обычно коррелирует с более высокой доходностью, но повышает риск IL.")
