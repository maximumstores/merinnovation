# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — налаштування розрахунків."""

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth
from db import ACCENT, cur_theme, get_conn, inject_css, lang_selector, q

st.set_page_config(layout="wide", page_title="Merinnovation · Settings",
                   page_icon="🐑")

user = auth.require_auth("11_Settings")
lang_selector()
inject_css()
auth.sidebar_user_block()

th = cur_theme()
is_admin = user["role"] == "admin"

st.markdown("## Налаштування розрахунків")
st.caption("Числа, на яких будуються прогноз, маржа і калькулятор акцій. "
           "Змінюються тут, а не в коді — скрипти читають їх при кожному "
           "запуску.")

try:
    exists = q("""
        SELECT COUNT(*) AS n FROM information_schema.tables
        WHERE table_schema='merinnovation' AND table_name='settings'
    """)
except Exception as e:
    st.error(f"Не вдалось прочитати базу: {e}")
    st.stop()

if exists.empty or int(exists["n"].iloc[0]) == 0:
    st.info("Таблиця налаштувань ще не створена. Запусти на сервері:\n\n"
            "```\npython 18_settings.py\n```")
    st.stop()

rows = q("""
    SELECT key, value, unit, grp, label, help_text, updated_at, updated_by
    FROM merinnovation.settings ORDER BY grp, key
""")

if rows.empty:
    st.info("Налаштувань немає — запусти 18_settings.py")
    st.stop()

if not is_admin:
    st.caption("Тільки перегляд — змінювати може адміністратор")

GROUP_HINTS = {
    "Юніт-економіка": "Впливає на маржу скрізь: прогноз, втрати, ціни",
    "Постачання": "Впливає на прогноз і оцінку розривів",
    "Акції": "Впливає на поріг допуску до Best Deal",
    "Реклама": "Впливає на оцінку кампаній ІІ-агентом",
    "Ціни": "Впливає на калькулятор медіани",
}

SUFFIX = {"pct": "%", "days": " дн", "ratio": ""}

changed = {}

for grp in rows["grp"].dropna().unique():
    st.markdown("")
    st.markdown(
        f'<div style="color:{th["text"]};font-size:17px;font-weight:700;">'
        f'{grp}</div>'
        f'<div style="color:{th["muted"]};font-size:13px;margin-bottom:10px;">'
        f'{GROUP_HINTS.get(grp, "")}</div>', unsafe_allow_html=True)

    grp_rows = rows[rows["grp"] == grp]
    for _, r in grp_rows.iterrows():
        key = r["key"]
        unit = r["unit"]
        val = float(r["value"])
        modified = r["updated_by"] != "default"

        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown(
                f'<div style="padding-top:6px;">'
                f'<span style="color:{th["text"]};font-size:15px;">'
                f'{r["label"]}</span>'
                + (f'<span style="color:{ACCENT};font-size:11px;'
                   f'margin-left:10px;">змінено</span>' if modified else "")
                + f'<div style="color:{th["muted"]};font-size:12px;'
                f'line-height:1.5;margin-top:2px;">{r["help_text"]}</div>'
                f'</div>', unsafe_allow_html=True)
        with c2:
            step = 0.01 if unit == "ratio" else (1.0 if unit == "days" else 0.5)
            fmt = "%.2f" if unit == "ratio" else "%.1f"
            new_val = st.number_input(
                f"{r['label']}", value=val, step=step, format=fmt,
                key=f"set_{key}", disabled=not is_admin,
                label_visibility="collapsed")
            if abs(new_val - val) > 1e-9:
                changed[key] = new_val

        st.markdown(f'<div style="height:1px;background:{th["border"]};'
                    f'margin:8px 0;"></div>', unsafe_allow_html=True)

# ------------------------------------------------------------ збереження ----
if is_admin:
    st.markdown("")
    if changed:
        st.warning(f"Незбережених змін: {len(changed)}")
        for k, v in changed.items():
            label = rows[rows["key"] == k]["label"].iloc[0]
            old = float(rows[rows["key"] == k]["value"].iloc[0])
            st.markdown(f"· {label}: **{old:g} → {v:g}**")

    sc1, sc2, _ = st.columns([1, 1, 4])
    with sc1:
        if st.button("Зберегти", type="primary", use_container_width=True,
                     disabled=not changed):
            try:
                conn = get_conn()
                with conn.cursor() as cur:
                    for k, v in changed.items():
                        cur.execute("""
                            UPDATE merinnovation.settings
                            SET value = %s, updated_at = now(), updated_by = %s
                            WHERE key = %s
                        """, (v, user["username"], k))
                conn.commit()
                auth.log_action("settings_change",
                                ", ".join(f"{k}={v:g}" for k, v in changed.items()))
                q.clear()
                st.success("Збережено. Нові числа застосуються при "
                           "наступному розрахунку.")
                st.rerun()
            except Exception as e:
                st.error(f"Не вдалось зберегти: {e}")

    with sc2:
        if st.button("Скинути до типових", use_container_width=True):
            st.session_state["_confirm_reset"] = True
            st.rerun()

    if st.session_state.get("_confirm_reset"):
        st.warning("Повернути всі значення до типових?")
        rc1, rc2, _ = st.columns([1, 1, 4])
        with rc1:
            if st.button("Так, скинути", type="primary",
                         use_container_width=True):
                try:
                    conn = get_conn()
                    with conn.cursor() as cur:
                        cur.execute("""
                            DELETE FROM merinnovation.settings
                        """)
                    conn.commit()
                    auth.log_action("settings_reset")
                    st.session_state.pop("_confirm_reset", None)
                    q.clear()
                    st.info("Скинуто. Запусти 18_settings.py на сервері, "
                            "щоб відновити типові значення.")
                except Exception as e:
                    st.error(f"{e}")
        with rc2:
            if st.button("Скасувати", use_container_width=True):
                st.session_state.pop("_confirm_reset", None)
                st.rerun()

# ------------------------------------------------------------ важливе ----
st.markdown("")
with st.expander("Що на що впливає"):
    st.markdown("""
**Собівартість** — найважливіше число. Від нього залежить уся маржа:
чи вигідна акція, чи не збиткова реклама, скільки насправді втрачається
на стокаутах. Якщо поставити приблизно, усі висновки будуть приблизними.

**Строк постачання** визначає, наскільки завчасно система попереджає
про розриви. Найбільша стаття втрат у розрахунку — «буде розрив
до приходу поставки» — рахується саме від нього.

**Падіння швидкості при підвищенні ціни** — оцінка за замовчуванням
у калькуляторі медіани. Точного числа не знає ніхто; надійніше підняти
ціну на тиждень і підставити факт.

---

Зміни застосуються при наступному запуску розрахунків:
`09_forecast.py`, `13_money_leaks.py`, `16_pricing_rules.py`,
`17_median_price.py`. За розкладом це 13:00–13:30, або запусти вручну.
""")

if not rows.empty:
    last = pd.to_datetime(rows["updated_at"]).max()
    st.caption(f"Останнє оновлення: {last:%d.%m.%Y %H:%M}")
