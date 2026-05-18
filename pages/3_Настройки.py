import streamlit as st
import json
import os

st.set_page_config(page_title="Настройки", page_icon="⚙️")

st.title("⚙️ Настройки")

settings_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'settings.json')

def load_settings():
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(s):
    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(s, f, indent=2, ensure_ascii=False)

current_settings = load_settings()

with st.form("settings_form"):
    st.subheader("Пороги рекомендаций")
    il_warning = st.number_input("IL Warning (%)", value=current_settings.get("il_warning_percent", 3.0))
    il_critical = st.number_input("IL Critical (%)", value=current_settings.get("il_critical_percent", 5.0))
    fees_reinvest = st.number_input("Fees Reinvest Threshold (%)", value=current_settings.get("fees_reinvest_percent", 10.0))
    
    st.divider()
    if st.form_submit_button("Сохранить настройки"):
        current_settings["il_warning_percent"] = il_warning
        current_settings["il_critical_percent"] = il_critical
        current_settings["fees_reinvest_percent"] = fees_reinvest
        
        try:
            save_settings(current_settings)
            st.success("Настройки успешно сохранены!")
        except Exception as e:
            st.error(f"Ошибка при сохранении: {e}")
