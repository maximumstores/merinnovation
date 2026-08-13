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


# ------------------------------------------------- власний пароль ----
with st.expander("🔑 Мій пароль"):
    st.caption("Ти вже увійшов у систему, тому старий пароль не потрібен. "
               "Впиши новий або згенеруй.")

    if st.button("Згенерувати", key="gen_own_pw",
                 icon=":material/casino:"):
        st.session_state["own_pw_value"] = auth.generate_password()
        st.rerun()

    with st.form("own_pw"):
        oc1, oc2 = st.columns([3, 1])
        with oc1:
            new_pw = st.text_input(
                "Новий пароль",
                value=st.session_state.get("own_pw_value", ""),
                key="own_pw_input")
        with oc2:
            st.markdown("<div style='height:28px'></div>",
                        unsafe_allow_html=True)
            save_own = st.form_submit_button("Зберегти", type="primary",
                                             use_container_width=True)

    if save_own:
        if len(new_pw) < 8:
            st.error("Пароль має бути не коротшим за 8 символів")
        else:
            auth.set_password(user["username"], new_pw, force_change=False)
            auth.remember_password(user["username"], new_pw, user["username"])
            auth.log_action("password_change_own")
            st.session_state.pop("own_pw_value", None)
            st.success(f"Пароль змінено: **{new_pw}**")

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
                help="Згенеровано автоматично — можеш вписати свій")
            keep_pw = st.checkbox(
                "Залишити цей пароль", value=True,
                help="Якщо зняти — при першому вході людина задасть свій "
                     "пароль, і ти його вже не знатимеш")

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
                                 new_role, user["username"],
                                 must_change=not keep_pw)
                if keep_pw:
                    auth.remember_password(login, gen_pass, user["username"])
                auth.log_action("user_create", login)
                st.success("Користувача створено")
                tail = ("" if keep_pw else
                        "\n\nПри першому вході людина задасть свій пароль.")
                st.info(f"Дані для входу:\n\n"
                        f"Логін: **{login}**\n\n"
                        f"Пароль: **{gen_pass}**{tail}")
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
        created = (pd.to_datetime(u["created_at"]).strftime("%d.%m.%Y")
                   if pd.notna(u["created_at"]) else "—")
        must_change = bool(u["must_change_password"])
        note = auth.get_password_note(u["username"])

        title = (f"{u['full_name'] or u['username']}"
                 f"{' (це ви)' if is_self else ''}  ·  {role_label}"
                 f"{'' if u['is_active'] else '  ·  вимкнено'}")

        with st.expander(title, expanded=False):
            st.markdown(
                f'<div style="border-left:3px solid {status_color};'
                f'padding-left:16px;margin-bottom:14px;">'
                f'<div style="color:{th["muted"]};font-size:13px;'
                f'line-height:1.9;">'
                f'Логін: <b style="color:{th["text"]};">{u["username"]}</b><br>'
                f'Роль: <b style="color:{th["text"]};">{role_label}</b> · '
                f'{status_text}<br>'
                f'Створено: {created} ({u["created_by"] or "—"})<br>'
                f'Останній вхід: {last} · всього входів: '
                f'{int(u["login_count"] or 0)}<br>'
                f'</div></div>', unsafe_allow_html=True)

            # Пароль, який задав адмін. Показуємо лише поки людина не
            # змінила його сама — після цього запис нечинний, і чесніше
            # сказати про це, ніж показувати застарілий рядок.
            if note and not note[2]:
                pw_val, pw_at, _ = note
                st.markdown(
                    f'<div style="background:{th["card"]};'
                    f'border:1px solid {ACCENT}55;border-radius:10px;'
                    f'padding:12px 16px;margin-bottom:12px;">'
                    f'<span style="color:{th["muted"]};font-size:12px;'
                    f'letter-spacing:.08em;text-transform:uppercase;">'
                    f'Поточний пароль</span><br>'
                    f'<code style="color:{ACCENT};font-size:17px;'
                    f'font-weight:700;letter-spacing:.5px;">{pw_val}</code>'
                    f'<span style="color:{th["muted"]};font-size:12px;'
                    f'margin-left:12px;">задано '
                    f'{pd.to_datetime(pw_at):%d.%m %H:%M}'
                    f'{" · змінить при вході" if must_change else ""}</span>'
                    f'</div>', unsafe_allow_html=True)
            elif note and note[2]:
                st.caption("Користувач змінив пароль сам — поточний "
                           "невідомий. Задай новий, якщо потрібен доступ.")
            elif is_self:
                st.caption("Свій пароль — у блоці «Мій пароль» вище")
            else:
                st.caption("Пароль задано до появи блокнота. "
                           "Задай новий, щоб він тут відображався.")

            bc1, bc2, bc3, bc4 = st.columns(4)

            with bc1:
                if is_self:
                    st.button("Пароль", key=f"pw_{u['username']}",
                              disabled=True, use_container_width=True,
                              help="Свій пароль — у блоці «Мій пароль» вище")
                else:
                    if st.button("Задати пароль", key=f"pw_{u['username']}",
                                 use_container_width=True):
                        st.session_state[f"setpw_{u['username']}"] = True
                        st.rerun()

            with bc2:
                if is_self:
                    st.button("—", key=f"na_{u['username']}", disabled=True,
                              use_container_width=True)
                elif u["is_active"]:
                    if st.button("Вимкнути", key=f"off_{u['username']}",
                                 use_container_width=True):
                        auth.set_active(u["username"], False)
                        auth.log_action("user_disable", u["username"])
                        st.rerun()
                else:
                    if st.button("Увімкнути", key=f"on_{u['username']}",
                                 use_container_width=True):
                        auth.set_active(u["username"], True)
                        auth.log_action("user_enable", u["username"])
                        st.rerun()

            with bc3:
                if is_self:
                    st.button("—", key=f"nr_{u['username']}", disabled=True,
                              use_container_width=True,
                              help="Свою роль змінити не можна")
                elif u["role"] == "admin":
                    if st.button("Зробити користувачем",
                                 key=f"rl_{u['username']}",
                                 use_container_width=True):
                        auth.set_role(u["username"], "user")
                        auth.log_action("role_change", f"{u['username']}→user")
                        st.rerun()
                else:
                    if st.button("Зробити адміном", key=f"rl_{u['username']}",
                                 use_container_width=True):
                        auth.set_role(u["username"], "admin")
                        auth.log_action("role_change", f"{u['username']}→admin")
                        st.rerun()

            with bc4:
                if is_self:
                    st.button("—", key=f"nd_{u['username']}", disabled=True,
                              use_container_width=True)
                elif st.session_state.get(f"confirm_del_{u['username']}"):
                    if st.button("Точно видалити?", key=f"delc_{u['username']}",
                                 type="primary", use_container_width=True):
                        auth.delete_user(u["username"])
                        auth.log_action("user_delete", u["username"])
                        st.rerun()
                else:
                    if st.button("Видалити", key=f"del_{u['username']}",
                                 use_container_width=True):
                        st.session_state[f"confirm_del_{u['username']}"] = True
                        st.rerun()

            # форма задання пароля
            if st.session_state.get(f"setpw_{u['username']}"):
                st.markdown("")
                with st.form(f"setpw_form_{u['username']}"):
                    manual_pw = st.text_input(
                        f"Новий пароль для {u['username']}",
                        value=auth.generate_password(),
                        key=f"mp_{u['username']}",
                        help="Згенеровано автоматично — можеш вписати свій")
                    force = st.checkbox(
                        "Хай змінить сам при вході", value=False,
                        key=f"fc_{u['username']}",
                        help="Тоді пароль знатиме тільки він")
                    fc1, fc2 = st.columns(2)
                    with fc1:
                        apply_pw = st.form_submit_button(
                            "Застосувати", type="primary",
                            use_container_width=True)
                    with fc2:
                        cancel_pw = st.form_submit_button(
                            "Скасувати", use_container_width=True)

                if apply_pw:
                    if len(manual_pw) < 8:
                        st.error("Пароль не коротший за 8 символів")
                    else:
                        auth.set_password(u["username"], manual_pw,
                                          force_change=force)
                        if not force:
                            # запам'ятовуємо лише якщо пароль робочий:
                            # якщо людина зараз же його змінить, запис
                            # був би оманою
                            auth.remember_password(u["username"], manual_pw,
                                                   user["username"])
                        auth.log_action("password_set", u["username"])
                        st.session_state[f"shown_pw_{u['username']}"] = manual_pw
                        st.session_state.pop(f"setpw_{u['username']}", None)
                        st.rerun()
                if cancel_pw:
                    st.session_state.pop(f"setpw_{u['username']}", None)
                    st.rerun()

            shown = st.session_state.get(f"shown_pw_{u['username']}")
            if shown:
                st.success(f"Пароль для **{u['username']}**: **{shown}**")
                st.caption("Передай особисто. Після закриття цього "
                           "повідомлення пароль більше не показати — "
                           "у базі зберігається лише хеш.")
                if st.button("Зрозуміло", key=f"hide_{u['username']}"):
                    st.session_state.pop(f"shown_pw_{u['username']}", None)
                    st.rerun()

# ------------------------------------------------------------ журнал ----
st.markdown("")

ACTION_LABELS = {
    "page_open": "відкрив",
    "user_create": "створив користувача",
    "user_delete": "видалив користувача",
    "user_disable": "вимкнув",
    "user_enable": "увімкнув",
    "password_reset": "скинув пароль",
    "password_set": "задав пароль",
    "password_change_own": "змінив свій пароль",
    "role_change": "змінив роль",
}
PAGE_LABELS = {
    "app": "Огляд", "1_Stock": "Залишки", "2_Traffic": "Трафік",
    "3_Finance": "Фінанси", "4_Forecast": "Прогноз", "5_Reviews": "Відгуки",
    "6_AI": "AI-аналітик", "7_Alerts": "Алерти", "8_Ads": "Реклама",
    "9_Users": "Користувачі",
}

with st.expander("Хто що робив"):
    # Таблиця створюється в init_auth(). Якщо база вже існувала до появи
    # журналу, її може ще не бути — перевіряємо, а не падаємо трейсбеком.
    has_log = q("""
        SELECT COUNT(*) AS n FROM information_schema.tables
        WHERE table_schema='merinnovation' AND table_name='activity_log'
    """)
    if has_log.empty or int(has_log["n"].iloc[0]) == 0:
        acts = pd.DataFrame()
        st.caption("Журнал ще порожній — записи з'являться після дій "
                   "користувачів")
    else:
        acts = q("""
            SELECT username, action, target, at
            FROM merinnovation.activity_log
            ORDER BY at DESC LIMIT 80
        """)

    if acts.empty:
        st.caption("Записів ще немає")
    else:
        for _, r in acts.iterrows():
            label = ACTION_LABELS.get(r["action"], r["action"])
            tgt = r["target"] or ""
            if r["action"] == "page_open":
                tgt = PAGE_LABELS.get(tgt, tgt)
            st.markdown(
                f'<div style="display:flex;gap:14px;padding:6px 0;'
                f'border-bottom:1px solid {th["border"]};font-size:13px;">'
                f'<span style="color:{th["muted"]};min-width:88px;'
                f'font-variant-numeric:tabular-nums;">'
                f'{pd.to_datetime(r["at"]):%d.%m %H:%M}</span>'
                f'<span style="color:{th["text"]};font-weight:600;'
                f'min-width:120px;">{r["username"]}</span>'
                f'<span style="color:{th["muted"]};">{label} '
                f'<b style="color:{th["text"]};">{tgt}</b></span></div>',
                unsafe_allow_html=True)

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
