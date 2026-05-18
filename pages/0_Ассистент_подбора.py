import streamlit as st
import pandas as pd
from core.pre_position_analyzer import analyze_pair

st.set_page_config(page_title="Ассистент подбора диапазона", page_icon="🎯", layout="wide")

st.title("🎯 Ассистент подбора диапазона")
st.markdown("Помогает рассчитать оптимальные границы LP-позиции на основе волатильности и стратегии.")

# Инициализация стейта
if 'pre_fill' not in st.session_state:
    st.session_state.pre_fill = None
if 'analysis_result' not in st.session_state:
    st.session_state.analysis_result = None
if 'last_params' not in st.session_state:
    st.session_state.last_params = {}

# Sidebar для параметров
with st.sidebar:
    st.header("Параметры анализа")
    popular_pairs = ["ETH/USDC", "WBTC/USDC", "SOL/USDC", "AVAX/USDC", "MATIC/USDC", "SUI/USDC"]
    pair = st.selectbox("Выберите или введите пару", popular_pairs + ["Другая (введите ниже)"])
    
    if pair == "Другая (введите ниже)":
        pair = st.text_input("Введите пару (например, ARB/USDC)", value="ARB/USDC").upper()
        
    network = st.selectbox("Сеть", ["ethereum", "arbitrum", "optimism", "polygon", "base", "bsc", "solana", "sui", "avalanche"])
    strategy = st.radio("Стратегия", ["active", "balanced", "passive"], index=1, 
                        help="Active: узкий дипазон (±30д), Balanced: сбалансированный (±90д), Passive: широкий (±180д)")
    
    deposit = st.number_input("Планируемый депозит ($)", min_value=10.0, value=1000.0, step=100.0)
    
    st.divider()
    goal = st.selectbox("🎯 Ваша цель", [
        "reinvest", 
        "accumulation", 
        "cashflow", 
        "hybrid_50_50"
    ], format_func=lambda x: {
        "reinvest": "Реинвест (Стандарт)",
        "accumulation": "Накопление актива (Широкий)",
        "cashflow": "Кэшфлоу (Узкий)",
        "hybrid_50_50": "Кэшфлоу 50% / Реинвест 50%"
    }.get(x))
    
    analyze_btn = st.button("🚀 Начать анализ", use_container_width=True)

if analyze_btn:
    with st.spinner(f"Анализируем {pair} на {network}..."):
        result = analyze_pair(pair, network, strategy, deposit, goal)
        if "error" in result:
            st.error(result["error"])
        else:
            st.session_state.analysis_result = result
            st.session_state.last_params = {"pair": pair, "network": network, "strategy": strategy, "deposit": deposit, "goal": goal}

if st.session_state.analysis_result:
    result = st.session_state.analysis_result
    params = st.session_state.last_params
    
    # Основной дашборд анализа
    st.divider()
    

    # Основные метрики пары
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Текущая цена", f"${result['current_price']:,.2f}")
    with col2:
        st.metric("Волатильность (год)", f"{result['volatility_annual']:.1f}%")
    with col3:
        st.metric("Объем (24ч)", f"${result['volume_24h']:,.0f}")
        
    # Добавляем блок с историческими границами
    st.markdown(f"""
    <div style="background-color: rgba(255, 255, 255, 0.05); padding: 15px; border-radius: 10px; border-left: 5px solid #2e7d32; margin-bottom: 20px;">
        <p style="margin: 0; font-size: 0.9rem; color: #aaa;">Исторические границы за последние <b>{result['history_days']} дней</b>:</p>
        <p style="margin: 5px 0; font-size: 1.2rem; font-weight: bold;">
            <span style="color: #ff5252;">${result['historical_min']:,.2f}</span> — 
            <span style="color: #4caf50;">${result['historical_max']:,.2f}</span>
        </p>
        <p style="margin: 0; font-size: 0.85rem; font-style: italic;">
            💡 <b>Рекомендация по безопасности:</b> Консервативный вариант учитывает эти границы + 5% запас, чтобы минимизировать риск выхода.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.subheader("Рекомендуемые варианты")
    
    # Отображение карточек
    cols = st.columns(len(result["suggestions"]))
    for i, sug in enumerate(result["suggestions"]):
        with cols[i]:
            # Цветовое оформление
            color = "green" if sug['type'] == "conservative" else "blue" if sug['type'] == "balanced" else "orange"
            st.markdown(f"### :{color}[{sug['type'].capitalize()}]")
            
            st.markdown(f"**Диапазон:**")
            st.markdown(f"📉 `${sug['lower']:,.2f}` — 📈 `${sug['upper']:,.2f}`")
            st.markdown(f"Ширина: `{sug['width_perc']:.1f}%` от цены")
            
            st.divider()
            st.metric("Ожидаемая APR", f"~{sug['expected_apr']:.1f}%")
            st.markdown(f"**Fee Tier:** `{sug['fee_tier']}%`")
            st.caption(f"Источник: {sug.get('source', 'LLC Model')}")
            
            with st.expander("ℹ️ Обоснование тира"):
                st.write(sug.get("fee_tier_rationale", "Стандартная рекомендация"))
                if sug.get("fee_tier_alternatives"):
                    st.write("**Альтернативы:** " + ", ".join([f"{a}%" for a in sug["fee_tier_alternatives"]]))
                    
            if sug.get("debug_info"):
                with st.expander("🛠 Детали расчёта бэктеста"):
                    dbg = sug["debug_info"]
                    st.write(f"**Анализируемых дней:** {dbg.get('actual_days', 'н/д')}")
                    st.write(f"**Дней в диапазоне:** {dbg.get('days_in_range', 'н/д')}")
                    avg_share = dbg.get('avg_share', 0)
                    st.write(f"**Средняя доля от пула:** {avg_share*100:.3f}%")
                    st.write(f"**Суммарные комиссии:** ${dbg.get('total_fees', 0):.2f}")
                    if dbg.get("is_anomaly"):
                        st.warning("Внимание: зафиксирована аномальная доходность, APR снижен на 20%.")
            
            # Измеритель риска
            risk = sug['risk_score']
            risk_label = "Низкий" if risk < 10 else "Средний" if risk < 30 else "Высокий"
            st.write(f"Риск выхода: **{risk_label}** ({risk:.1f}%)")
            
            if st.session_state.get("authenticated"):
                if st.button(f"Выбрать {sug['type']}", key=f"btn_{i}"):
                    st.session_state.pre_fill = {
                        "network": params['network'],
                        "pair": params['pair'],
                        "lower_price": sug['lower'],
                        "upper_price": sug['upper'],
                        "dex": "uniswap_v3"
                    }
                    st.success("Данные подготовлены! Перейдите на страницу 'Добавить позицию'.")

if st.session_state.pre_fill and st.session_state.get("authenticated"):
    st.info(f"💡 Вы выбрали диапазон для {st.session_state.pre_fill['pair']}. Нажмите кнопку ниже, чтобы продолжить.")
    if st.button("Перейти к добавлению позиции"):
        st.switch_page("pages/1_Добавить_позицию.py")

st.divider()
st.info("ℹ️ Расчёты основаны на исторических данных DexScreener и могут не гарантировать доходность в будущем.")
