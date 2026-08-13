# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — керування користувачами (тільки адмін)."""

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth
from db import ACCENT, cur_theme, inject_css, lang_selector, metric_card, q

st.set_page_config(layout="wide", page_title="Merinnovation · Users",
                   page_icon="🐑")

user = auth.require_auth("9_Users")
if user["role"] != "admin":
    st.error("Доступ лише для адміністратора")
    st.stop()

lang_selector()
inject_css()
auth.sidebar_user_block()

th = cur_theme()

st.markdown("## Користувачі")

# ------------------------------------------------------------ список ----
users = auth.list_users()

c1, c2, c3 = st.columns(3)
with c1:
    metric_card("Всього", f"{len(users)}")
with c2:
    metric_card("Активних", f"{int(users['is_active'].sum())}")
with c3:
    metric_card("Адміністраторів",
                f"{int((users['role'] == 'admin').sum())}")

st.markdown("")

# --------------------------------------------------- створення нового ----
with st.expander("➕ Додати користувача", expanded=len(users) <= 1):
    with st.form("new_user"):
        nc1, nc2 = st.columns(2)
        with nc1:
            new_login = st.text_input("Логін (латиницею, без пробілів)")
            new_name = st.text_input("Ім'я")
        with nc2:
            new_role = st.selectbox("Роль", ["user", "admin"],
                                    format_func=lambda r: (
                                        "Користувач — без Алертів"
                                        if r == "user"
                                        else "Адміністратор — повний доступ"))
            gen_pass = st.text_input(
                "Пароль", value=auth.generate_password(),
                help="Згенеровано автоматично — можна замінити своїм")

        created = st.form_submit_button("Створити", type="primary")

    if created:
        login = (new_login or "").strip().lower()
        if not login or not login.replace("_", "").replace(".", "").isalnum():
            st.error("Логін лише з латинських літер, цифр, крапки і підкреслення")
        elif len(gen_pass) < 8:
            st.error("Пароль не коротший за 8 символів")
        elif auth.get_user(login):
            st.error("Такий логін уже існує")
        else:
            try:
                auth.create_user(login, gen_pass, new_name or login,
                                 new_role, user["username"])
                st.success("Користувача створено")
                st.info(f"Передай ці дані особисто:\n\n"
                        f"Логін: **{login}**\n\n"
                        f"Пароль: **{gen_pass}**\n\n"
                        f"При першому вході система попросить змінити пароль.")
            except Exception as e:
                st.error(f"Не вдалось створити: {e}")

st.markdown("")

# ------------------------------------------------------------ таблиця ----
st.markdown("**Список**")

if users.empty:
    st.caption("Користувачів немає")
else:
    for _, u in users.iterrows():
        is_self = u["username"] == user["username"]
        role_label = "Адмін" if u["role"] == "admin" else "Користувач"
        status_color = ACCENT if u["is_active"] else "#ef4444"
        status_text = "активний" if u["is_active"] else "вимкнено"
        last = (pd.to_datetime(u["last_login"]).strftime("%d.%m %H:%M")
                if pd.notna(u["last_login"]) else "жодного разу")

        with st.container():
            uc1, uc2 = st.columns([3, 2])
            with uc1:
                st.markdown(
                    f'<div style="background:{th["card"]};'
                    f'border:1px solid {th["border"]};'
                    f'border-left:3px solid {status_color};'
                    f'border-radius:10px;padding:14px 18px;">'
                    f'<div style="color:{th["text"]};font-size:15px;'
                    f'font-weight:600;">{u["full_name"] or u["username"]}'
                    f'{" (це ви)" if is_self else ""}</div>'
                    f'<div style="color:{th["muted"]};font-size:12px;'
                    f'margin-top:4px;">{u["username"]} · {role_label} · '
                    f'{status_text} · вхід: {last} '
                    f'({int(u["login_count"] or 0)})</div></div>',
                    unsafe_allow_html=True)

            with uc2:
                bc1, bc2, bc3 = st.columns(3)
                with bc1:
                    if st.button("Пароль", key=f"pw_{u['username']}",
                                 use_container_width=True):
                        newp = auth.generate_password()
                        auth.set_password(u["username"], newp)
                        st.session_state[f"shown_pw_{u['username']}"] = newp
                        st.rerun()
                with bc2:
                    if is_self:
                        st.button("—", key=f"na_{u['username']}",
                                  disabled=True, use_container_width=True)
                    elif u["is_active"]:
                        if st.button("Вимкнути", key=f"off_{u['username']}",
                                     use_container_width=True):
                            auth.set_active(u["username"], False)
                            st.rerun()
                    else:
                        if st.button("Увімкнути", key=f"on_{u['username']}",
                                     use_container_width=True):
                            auth.set_active(u["username"], True)
                            st.rerun()
                with bc3:
                    if is_self:
                        st.button("—", key=f"nd_{u['username']}",
                                  disabled=True, use_container_width=True)
                    else:
                        if st.button("Видалити", key=f"del_{u['username']}",
                                     use_container_width=True):
                            auth.delete_user(u["username"])
                            st.rerun()

            shown = st.session_state.get(f"shown_pw_{u['username']}")
            if shown:
                st.info(f"Новий пароль для **{u['username']}**: **{shown}** "
                        f"— передай особисто, при вході попросить змінити")
                if st.button("Приховати", key=f"hide_{u['username']}"):
                    st.session_state.pop(f"shown_pw_{u['username']}", None)
                    st.rerun()

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ------------------------------------------------------------ журнал ----
st.markdown("")
with st.expander("Журнал входів"):
    log = q("""
        SELECT username, success, at
        FROM merinnovation.login_log
        ORDER BY at DESC LIMIT 50
    """)
    if log.empty:
        st.caption("Записів немає")
    else:
        fails = int((~log["success"]).sum())
        if fails:
            st.caption(f"Невдалих спроб серед останніх 50: {fails}")
        for _, r in log.iterrows():
            icon = "✅" if r["success"] else "❌"
            st.markdown(
                f'<div style="color:{th["muted"]};font-size:13px;'
                f'padding:4px 0;">{icon} {r["username"]} · '
                f'{pd.to_datetime(r["at"]):%d.%m %H:%M}</div>',
                unsafe_allow_html=True)

st.caption("Паролі зберігаються хешем — відновити їх неможливо, "
           "лише згенерувати новий")
