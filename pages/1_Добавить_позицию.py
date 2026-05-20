import streamlit as st
from data.db import add_position
from data.price_client import get_current_price
from core.position_state import compute_liquidity
from core.goal_recommendations import GOAL_LABELS

if not st.session_state.get("authenticated", False):
    st.warning("⚠️ Эта страница доступна только для администратора.")
    st.info("Пожалуйста, войдите в систему через сайдбар на главной странице.")
    st.stop()

st.set_page_config(page_title="Добавить позицию", page_icon="➕")
st.title("➕ Добавить новую позицию")

st.header("Ручной ввод данных")

with st.form("manual_add_form"):
    # ── Pre-fill from Assistant ──────────────────────────────────────────
        default_network = "ethereum"
        default_dex     = "uniswap_v3"
        default_pair    = "ETH/USDC"
        default_lower   = 0.0
        default_upper   = 0.0

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
            lower_price = st.number_input("Нижняя граница (Lower Price)", min_value=0.0, format="%.6f", value=default_lower)
            upper_price = st.number_input("Верхняя граница (Upper Price)", min_value=0.0, format="%.6f", value=default_upper)
            initial_price = st.number_input(
                "Цена на момент открытия позиции",
                min_value=0.0, format="%.6f", value=0.0,
                help="Используется для точного расчёта ликвидности L. Если 0 — будет определена автоматически."
            )

        # Добавляем ввод даты открытия позиции
        from datetime import date
        creation_date = st.date_input("Дата открытия", value=date.today(), format="YYYY-MM-DD")

        st.divider()

        # ── Token amounts ────────────────────────────────────────────────────
        col3, col4 = st.columns(2)
        base_sym  = pair.split('/')[0].upper() if '/' in pair else pair.upper()
        quote_sym = pair.split('/')[1].upper() if '/' in pair else 'USDC'

        with col3:
            token0_amount = st.number_input(f"Кол-во {base_sym} (Token0)", min_value=0.0, format="%.8f")
        with col4:
            token1_amount = st.number_input(f"Кол-во {quote_sym} (Token1)", min_value=0.0, format="%.8f")

        st.divider()

        # ── Goal ─────────────────────────────────────────────────────────────
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

        # ── Optional ─────────────────────────────────────────────────────────
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
                if initial_price == 0.0:
                    fetched = get_current_price(base_sym, network)
                    initial_price = fetched if fetched else ((lower_price + upper_price) / 2)

                # Compute L
                liquidity = compute_liquidity(initial_price, lower_price, upper_price, token0_amount, token1_amount)

                owner_id = 'public' if is_public else 'admin'

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
                        initial_price=initial_price,
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
                except Exception as e:
                    st.error(f"Ошибка при сохранении в БД: {e}")
