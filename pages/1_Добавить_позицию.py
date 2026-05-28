import streamlit as st
from data.db import add_position
from data.price_client import get_current_price
from core.position_state import compute_liquidity
from core.goal_recommendations import GOAL_LABELS
from core.il_calculator import calculate_required_amounts

if not st.session_state.get("authenticated", False):
    st.warning("⚠️ Эта страница доступна только для администратора.")
    st.info("Пожалуйста, войдите в систему через сайдбар на главной странице.")
    st.stop()

st.set_page_config(page_title="Добавить позицию", page_icon="➕")
st.title("➕ Добавить новую позицию")

st.header("Ручной ввод данных")

# ── Pre-fill from Assistant ──────────────────────────────────────────
default_network = "ethereum"
default_dex     = "uniswap_v3"
default_pair    = "ETH/USDC"
default_lower   = 0.0
default_upper   = 0.0
default_init_price = 0.0

if st.session_state.get('pre_fill'):
    pf = st.session_state.pre_fill
    default_network = pf.get('network', default_network)
    default_dex     = pf.get('dex', default_dex)
    default_pair    = pf.get('pair', default_pair)
    default_lower   = pf.get('lower_price', 0.0)
    default_upper   = pf.get('upper_price', 0.0)
    st.success(f"📦 Подставлены данные из ассистента для {default_pair}")

# ── Position basics ──────────────────────────────────────────────────
col1, col2 = st.columns(2)
NETWORKS = ["ethereum", "arbitrum", "optimism", "polygon", "base", "bsc", "solana", "sui", "aptos"]
DEXES    = ["uniswap_v3", "pancakeswap_v3", "aerodrome", "raydium_clmm", "cetus", "orca"]

with col1:
    network = st.selectbox(
        "Сеть", NETWORKS,
        index=NETWORKS.index(default_network) if default_network in NETWORKS else 0
    )
    dex = st.selectbox(
        "DEX", DEXES,
        index=DEXES.index(default_dex) if default_dex in DEXES else 0
    )
    pair = st.text_input("Пара (например, ETH/USDC или SOL/USDC)", value=default_pair)

with col2:
    lower_price = st.number_input("Нижняя граница (Lower Price)", min_value=0.0, format="%.6f", value=default_lower, key='_lower_input')
    upper_price = st.number_input("Верхняя граница (Upper Price)", min_value=0.0, format="%.6f", value=default_upper, key='_upper_input')
    initial_price = st.number_input(
        "Цена на момент открытия позиции",
        min_value=0.0, format="%.6f", value=default_init_price,
        key='_price_input',
        help="Используется для точного расчёта ликвидности L. Если 0 — будет определена автоматически."
    )

# ── Smart mutual token amount calculation ────────────────────────────
base_sym  = pair.split('/')[0].upper() if '/' in pair else pair.upper()
quote_sym = pair.split('/')[1].upper() if '/' in pair else 'USDC'

# Auto-fetch price for calculation hint
calc_price = initial_price if initial_price > 0 else (
    get_current_price(base_sym, network) or ((lower_price + upper_price) / 2) if lower_price > 0 and upper_price > 0 else 0.0
)

col3, col4 = st.columns(2)

with col3:
    def _on_change_token0():
        a0 = st.session_state.get('_tk0_input', 0.0)
        a1 = st.session_state.get('_tk1_input', 0.0)
        l  = st.session_state.get('_lower_input', 0.0)
        u  = st.session_state.get('_upper_input', 0.0)
        p  = st.session_state.get('_price_input', 0.0)
        if p <= 0 or l <= 0 or u <= l:
            return
        if a0 > 0:
            _, comp1, _, _ = calculate_required_amounts(l, u, p, amount0=a0)
            st.session_state['_tk1_hint'] = comp1
            st.session_state['_tk0_hint'] = None
        elif a1 == 0:
            st.session_state['_tk1_hint'] = None
            st.session_state['_tk0_hint'] = None

    st.session_state['_tk0_input'] = default_tk0 = st.session_state.get('_tk0_input', 0.0)
    token0_amount = st.number_input(
        f"Кол-во {base_sym} (Token0)",
        min_value=0.0, format="%.8f", value=default_tk0,
        key='_tk0_input',
        on_change=_on_change_token0
    )

with col4:
    def _on_change_token1():
        a0 = st.session_state.get('_tk0_input', 0.0)
        a1 = st.session_state.get('_tk1_input', 0.0)
        l  = st.session_state.get('_lower_input', 0.0)
        u  = st.session_state.get('_upper_input', 0.0)
        p  = st.session_state.get('_price_input', 0.0)
        if p <= 0 or l <= 0 or u <= l:
            return
        if a1 > 0:
            comp0, _, _, _ = calculate_required_amounts(l, u, p, amount1=a1)
            st.session_state['_tk0_hint'] = comp0
            st.session_state['_tk1_hint'] = None
        elif a0 == 0:
            st.session_state['_tk1_hint'] = None
            st.session_state['_tk0_hint'] = None

    st.session_state['_tk1_input'] = default_tk1 = st.session_state.get('_tk1_input', 0.0)
    token1_amount = st.number_input(
        f"Кол-во {quote_sym} (Token1)",
        min_value=0.0, format="%.8f", value=default_tk1,
        key='_tk1_input',
        on_change=_on_change_token1
    )

# Show hint for the complementary token
hint0 = st.session_state.get('_tk0_hint')
hint1 = st.session_state.get('_tk1_hint')
if hint1 is not None and hint1 > 0:
    st.info(f"💡 Для {token0_amount:.6f} {base_sym} требуется ≈ **{hint1:.6f} {quote_sym}**")
elif hint0 is not None and hint0 > 0:
    st.info(f"💡 Для {token1_amount:.6f} {quote_sym} требуется ≈ **{hint0:.6f} {base_sym}**")
elif token0_amount > 0 and token1_amount > 0 and calc_price > 0 and lower_price > 0 and upper_price > lower_price:
    v0, v1, L_calc, src = calculate_required_amounts(lower_price, upper_price, calc_price, amount0=token0_amount)
    if src == 'token0' and abs(v1 - token1_amount) > 0.001 * token1_amount:
        st.warning(f"⚠️ Пропорция неверна: нужно ≈ **{v1:.6f} {quote_sym}** на {token0_amount:.6f} {base_sym}")

st.divider()

# ── Keep the rest inside a form for clean submission ────────────────
with st.form("manual_add_form"):
    from datetime import date
    creation_date = st.date_input("Дата открытия", value=date.today(), format="YYYY-MM-DD")

    st.subheader("🎯 Цель позиции")
    goal = st.selectbox(
        "Выберите цель",
        list(GOAL_LABELS.keys()),
        format_func=lambda k: GOAL_LABELS[k]
    )

    target_token  = ''
    target_amount = 0.0

    if goal in ('preserve_asset', 'accumulate_stable'):
        col5, col6 = st.columns(2)
        with col5:
            target_token = st.text_input(
                "Целевой токен (например, SOL или USDC)",
                value=base_sym if goal == 'preserve_asset' else quote_sym
            )
        if goal == 'preserve_asset':
            with col6:
                target_amount = st.number_input(
                    f"Целевое количество {target_token}",
                    min_value=0.0, format="%.4f",
                    value=float(token0_amount) if token0_amount > 0 else 0.0
                )

    st.divider()

    wallet_address = st.text_input("Адрес кошелька (опционально)")
    is_public = st.checkbox("🌐 Сделать позицию публичной", value=False, help="Публичные позиции видны всем пользователям (без пароля).")

    submit_button = st.form_submit_button("💾 Сохранить позицию")

    if submit_button:
        if lower_price >= upper_price:
            st.error("Ошибка: Нижняя граница должна быть меньше верхней!")
        elif token0_amount == 0 and token1_amount == 0:
            st.error("Ошибка: Введите количество токенов!")
        else:
            # Auto-fetch price if not provided
            save_price = initial_price
            if save_price == 0.0:
                fetched = get_current_price(base_sym, network)
                save_price = fetched if fetched else ((lower_price + upper_price) / 2)

            # Compute L
            liquidity = compute_liquidity(save_price, lower_price, upper_price, token0_amount, token1_amount)

            owner_id = None

            try:
                add_position(
                    network=network,
                    dex=dex,
                    pair=pair.upper(),
                    lower_price=lower_price,
                    upper_price=upper_price,
                    token0_amount=token0_amount,
                    token1_amount=token1_amount,
                    wallet_address=wallet_address if wallet_address else None,
                    initial_price=save_price,
                    goal=goal,
                    target_token=target_token,
                    target_amount=target_amount,
                    liquidity=liquidity,
                    is_public=is_public,
                    owner_id=owner_id,
                    created_at=creation_date.isoformat(),
                )
                st.success(f"✅ Позиция {pair.upper()} добавлена! L = {liquidity:.4f}")
                st.balloons()
                # Clear hints after successful save
                for k in ['_tk0_input', '_tk1_input', '_tk0_hint', '_tk1_hint']:
                    if k in st.session_state:
                        del st.session_state[k]
            except Exception as e:
                st.error(f"Ошибка при сохранении в БД: {e}")
