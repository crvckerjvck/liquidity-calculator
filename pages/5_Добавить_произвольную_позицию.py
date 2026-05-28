import streamlit as st
from datetime import date
from data.db import add_custom_position, add_v2_pool
from data.price_client import get_current_price

# Page config
st.set_page_config(page_title="Добавить произвольную позицию", page_icon="➕")

st.title("➕ Добавить произвольную DeFi-позицию")

# Authentication check
if not st.session_state.get('authenticated', False):
    st.warning("Эта страница доступна только после входа.")
    if st.button("Перейти к авторизации"):
        st.switch_page("app.py")
    st.stop()

# Header navigation
st.page_link("app.py", label="Вернуться к дашборду", icon="🏠")
st.divider()

# ── Тип позиции вне формы – для реактивного условного рендеринга ────────────
pos_type = st.selectbox(
    "Тип позиции",
    ["V2 Pool", "Lending", "Vault", "Staking", "Perp Vault", "Delta Neutral"]
)

# ── Основная форма ───────────────────────────────────────────────────────────
with st.form("custom_position_form"):
    protocol = st.text_input("Протокол (напр., Uniswap, Aave, GMX)", placeholder="Uniswap")
    network = st.selectbox("Сеть", ["Ethereum", "Arbitrum", "Solana", "Optimism", "Polygon", "Base", "BNB Chain"])
    st.divider()

    if pos_type == "V2 Pool":
        st.subheader("💧 Параметры V2 Пула")
        v2_col1, v2_col2 = st.columns(2)
        with v2_col1:
            token0 = st.text_input("Актив 1 (например, ETH)", placeholder="ETH")
            amount0 = st.number_input("Количество Актива 1", min_value=0.0, step=0.01, format="%.6f")
        with v2_col2:
            token1 = st.text_input("Актив 2 (например, USDC)", placeholder="USDC")
            amount1 = st.number_input("Количество Актива 2", min_value=0.0, step=0.01, format="%.6f")
        
        initial_price = st.number_input("Цена входа (token0 в token1)", min_value=0.0, format="%.6f", help="Цена токена 1 выраженная в токене 2 при открытии позиции")
        apy = st.number_input("APY (%) - опционально", min_value=0.0, step=0.1)

    else:
        st.subheader("📦 Параметры Депозита")
        col1, col2 = st.columns(2)
        with col1:
            asset_dep = st.text_input("Актив депозита", placeholder="USDC")
        with col2:
            amount_dep = st.number_input("Количество депозита", min_value=0.0, step=0.1, format="%.6f")
        apy = st.number_input("APY (%)", min_value=0.0, step=0.1, help="Ожидаемая годовая доходность")

        # ── Поля займа — только для Lending
        asset_borrow = None
        amount_borrow = 0.0
        liq_threshold = None

        if pos_type == "Lending":
            st.divider()
            st.subheader("🏦 Параметры займа (Lending)")
            l_col1, l_col2 = st.columns(2)
            with l_col1:
                asset_borrow = st.text_input("Актив займа", placeholder="USDT")
                amount_borrow = st.number_input("Количество займа", min_value=0.0, step=0.1, format="%.6f")
            with l_col2:
                liq_threshold = st.number_input(
                    "Порог ликвидации (0.0–1.0)",
                    min_value=0.0, max_value=1.0, value=0.75, step=0.01,
                    help="Коэффициент залога, при котором наступает ликвидация (например, 0.75 означает 75%)"
                )
        else:
            st.info(f"ℹ️ Для типа **{pos_type}** поля займа не требуются.")

    st.divider()
    created_at = st.date_input("Дата открытия", value=date.today())
    is_public = st.checkbox("🌐 Сделать позицию публичной (видят все)", value=False, help="Публичные позиции видны всем пользователям без пароля.")
    notes = st.text_area("Заметки", placeholder="Любая дополнительная информация...")

    submit = st.form_submit_button("💾 Сохранить позицию")

    if submit:
        if not protocol:
            st.error("Укажите протокол!")
        elif pos_type == "V2 Pool":
            if not token0 or not token1 or amount0 <= 0 or amount1 <= 0 or initial_price <= 0:
                st.error("Заполните все поля V2 пула (оба токена, их количество и цену входа).")
            else:
                try:
                    add_v2_pool(
                        network=network.lower(),
                        dex=protocol,
                        pair=f"{token0.upper()}/{token1.upper()}",
                        token0_symbol=token0.upper(),
                        token1_symbol=token1.upper(),
                        token0_initial=amount0,
                        token1_initial=amount1,
                        initial_price=initial_price,
                        created_at=created_at.isoformat(),
                        apy=apy,
                        is_public=is_public
                    )
                    st.success("✅ V2 Пул успешно добавлен!")
                    st.balloons()
                except Exception as e:
                    st.error(f"Ошибка при сохранении: {e}")
        else:
            # Logic for Custom Positions (Lending, Vault, etc.)
            if not asset_dep or amount_dep <= 0:
                st.error("Пожалуйста, заполните Актив и Количество депозита.")
            elif pos_type == "Lending" and amount_borrow > 0 and not asset_borrow:
                st.error("Укажите актив займа, если введено количество.")
            else:
                try:
                    # Fetch current price for USD value calculation
                    usd_price = get_current_price(asset_dep.upper(), network.lower()) or 0.0
                    val_dep = amount_dep * usd_price if usd_price > 0 else amount_dep
                    add_custom_position(
                        _type=pos_type.lower().replace(" ", "_"),
                        protocol=protocol,
                        network=network.lower(),
                        asset_deposited=asset_dep.upper(),
                        amount_deposited=amount_dep,
                        asset_borrowed=asset_borrow.upper() if asset_borrow else None,
                        amount_borrowed=amount_borrow if pos_type == "Lending" else None,
                        liquidation_threshold=liq_threshold if pos_type == "Lending" else None,
                        apy=apy,
                        notes=notes,
                        is_public=is_public,
                        created_at=created_at.isoformat(),
                        val_dep=val_dep,
                    )
                    st.success("✅ Позиция успешно добавлена!")
                    st.balloons()
                except Exception as e:
                    st.error(f"Ошибка при сохранении: {e}")
