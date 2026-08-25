# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — звірка з Seller Central.

Навіщо: система рахує з SP-API, Seller Central показує своє. Поки ніхто
не звірив — ми не знаємо, чи цифри правильні. Розбіжність у 5% може бути
різницею методик, у 50% — помилкою в коді.

Вводить людина, яка веде магазин: браузерний агент теж може помилитись
при читанні, і тоді ми звіряли б одну автоматику з іншою.
"""

import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth
from db import (ACCENT, ACCENT2, cur_theme, get_conn, inject_css,
                lang_selector, metric_card, plotly_layout, q, themed_axis)

st.set_page_config(layout="wide", page_title="Merinnovation · Verify",
                   page_icon="🐑")

user = auth.require_auth("12_Verify")
lang_selector()
inject_css()
auth.sidebar_user_block()

th = cur_theme()
RED = "#ef4444"
AMBER = "#f59e0b"

st.markdown("## Звірка з Seller Central")
st.caption("Раз на тиждень: відкрий Seller Central, впиши фактичні числа. "
           "Система покаже, де вона розходиться з реальністю.")


# ------------------------------------------------------------ таблиця ----
def init_table():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS merinnovation.verification (
                id BIGSERIAL PRIMARY KEY,
                check_date DATE DEFAULT CURRENT_DATE,
                metric_key TEXT,
                our_value NUMERIC,
                actual_value NUMERIC,
                diff_pct NUMERIC,
                note TEXT,
                checked_by TEXT,
                created_at TIMESTAMPTZ DEFAULT now()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_verification_date
            ON merinnovation.verification (check_date DESC, metric_key);
        """)
    conn.commit()
    conn.close()


# Таблицю створюємо раз на сесію: на кожному переході це зайвий похід
# у базу. Плюс з'єднання може протухнути між запитами — тоді скидаємо
# кеш і пробуємо ще раз, а не лякаємо користувача помилкою.
if not st.session_state.get("_verify_inited"):
    try:
        init_table()
        st.session_state["_verify_inited"] = True
    except Exception:
        try:
            from db import _new_conn
            _new_conn.clear()
            init_table()
            st.session_state["_verify_inited"] = True
        except Exception as e:
            st.error(f"База недоступна: {e}")
            st.stop()

# ------------------------------------------- наші поточні значення ----
# Кожна метрика: (ключ, підпис, де шукати в Seller Central, формат)
METRICS = [
    ("orders_7d", "Замовлень за 7 днів",
     "Business Reports → Sales Dashboard", "int"),
    ("revenue_7d", "Виручка за 7 днів, $",
     "Business Reports → Sales Dashboard", "money"),
    ("sessions_7d", "Сесій за 7 днів",
     "Business Reports → Detail Page Sales and Traffic", "int"),
    ("units_total", "Одиниць на складі (fulfillable)",
     "Inventory → Manage FBA Inventory", "int"),
    ("sku_zero", "SKU з нульовим залишком",
     "Inventory → фільтр Available = 0", "int"),
    ("ads_spend_7d", "Витрати на рекламу за 7 днів, $",
     "Campaign Manager → період 7 днів", "money"),
    ("ads_sales_7d", "Продажі від реклами за 7 днів, $",
     "Campaign Manager → період 7 днів", "money"),
    ("returns_30d", "Повернень за 30 днів, шт",
     "Reports → Return Reports", "int"),
]


@st.cache_data(ttl=300)
def our_values():
    """Те, що показує наша система — з тих самих таблиць, що й дашборд."""
    out = {}
    try:
        r = q("""
            SELECT COUNT(*) AS n
            FROM merinnovation.orders
            WHERE purchase_date >= NOW() - INTERVAL '7 days'
              AND order_status <> 'Canceled'
        """)
        out["orders_7d"] = float(r["n"].iloc[0] or 0)
    except Exception:
        pass

    try:
        r = q("""
            SELECT COALESCE(SUM(ordered_product_sales), 0) AS v
            FROM merinnovation.sales_traffic_daily
            WHERE report_date >= CURRENT_DATE - 7
        """)
        out["revenue_7d"] = float(r["v"].iloc[0] or 0)
    except Exception:
        pass

    try:
        r = q("""
            SELECT COALESCE(SUM(sessions), 0) AS v
            FROM merinnovation.sales_traffic_daily
            WHERE report_date >= CURRENT_DATE - 7
        """)
        out["sessions_7d"] = float(r["v"].iloc[0] or 0)
    except Exception:
        pass

    try:
        r = q("""
            SELECT COALESCE(SUM(fulfillable_quantity), 0) AS v,
                   COUNT(*) FILTER (WHERE fulfillable_quantity = 0) AS z
            FROM merinnovation.fba_inventory
            WHERE snapshot_date = (
                SELECT MAX(snapshot_date) FROM merinnovation.fba_inventory)
        """)
        out["units_total"] = float(r["v"].iloc[0] or 0)
        out["sku_zero"] = float(r["z"].iloc[0] or 0)
    except Exception:
        pass

    try:
        r = q("""
            SELECT COALESCE(SUM(cost), 0) AS spend,
                   COALESCE(SUM("sales7d"), 0) AS sales
            FROM merinnovation.ads_sp_campaign
            WHERE "date" >= CURRENT_DATE - 7
        """)
        out["ads_spend_7d"] = float(r["spend"].iloc[0] or 0)
        out["ads_sales_7d"] = float(r["sales"].iloc[0] or 0)
    except Exception:
        pass

    try:
        r = q("""
            SELECT COALESCE(SUM(quantity), 0) AS v
            FROM merinnovation.returns
            WHERE return_date >= CURRENT_DATE - 30
        """)
        out["returns_30d"] = float(r["v"].iloc[0] or 0)
    except Exception:
        pass

    return out


ours = our_values()

# --------------------------------------------- остання звірка ----
last = q("""
    SELECT metric_key, our_value, actual_value, diff_pct, check_date
    FROM merinnovation.verification v1
    WHERE check_date = (SELECT MAX(check_date) FROM merinnovation.verification)
""")
last_map = ({r["metric_key"]: r for _, r in last.iterrows()}
            if not last.empty else {})

if last_map:
    last_date = pd.to_datetime(last["check_date"].iloc[0]).date()
    days_ago = (datetime.now().date() - last_date).days
    big = [r for r in last_map.values()
           if r["diff_pct"] is not None and abs(float(r["diff_pct"])) > 10]

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Остання звірка", last_date.strftime("%d.%m.%Y"),
                    sub=f"{days_ago} дн. тому")
    with c2:
        metric_card("Метрик перевірено", f"{len(last_map)}")
    with c3:
        metric_card("Розбіжність > 10%", f"{len(big)}",
                    sub="потребує розбору" if big else "усе сходиться")

    if days_ago > 10:
        st.warning(f"Останню звірку робили {days_ago} днів тому. "
                   f"Дані змінились — варто перевірити знову.")
else:
    st.info("Звірки ще не було. Це перший запуск — впиши фактичні числа "
            "з Seller Central, і система покаже, де вона розходиться.")

st.markdown("---")

# ------------------------------------------------------------ форма ----
st.markdown("**Введи фактичні значення з Seller Central**")
st.caption("Порожнє поле — метрику пропускаємо. Заповнюй те, що можеш "
           "швидко подивитись.")

entries = {}
notes = {}

for key, label, where, fmt in METRICS:
    our = ours.get(key)
    prev = last_map.get(key)

    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])

    with c1:
        st.markdown(
            f'<div style="padding-top:8px;">'
            f'<span style="color:{th["text"]};font-size:15px;">{label}</span>'
            f'<div style="color:{th["muted"]};font-size:12px;margin-top:2px;">'
            f'{where}</div></div>', unsafe_allow_html=True)

    with c2:
        our_txt = ("—" if our is None else
                   (f"${our:,.2f}" if fmt == "money" else f"{our:,.0f}"))
        st.markdown(
            f'<div style="padding-top:10px;">'
            f'<span style="color:{th["muted"]};font-size:11px;'
            f'text-transform:uppercase;letter-spacing:.08em;">У нас</span>'
            f'<div style="color:{th["text"]};font-size:17px;font-weight:600;'
            f'font-variant-numeric:tabular-nums;">{our_txt}</div></div>',
            unsafe_allow_html=True)

    with c3:
        entries[key] = st.number_input(
            f"Факт · {label}", min_value=0.0, step=1.0,
            value=None, key=f"vf_{key}", label_visibility="collapsed",
            placeholder="з Seller Central")

    with c4:
        val = entries[key]
        if val is not None and our is not None and our > 0:
            diff = (val - our) / our * 100
            color = (ACCENT if abs(diff) <= 5
                     else AMBER if abs(diff) <= 15 else RED)
            st.markdown(
                f'<div style="padding-top:12px;color:{color};'
                f'font-size:17px;font-weight:700;'
                f'font-variant-numeric:tabular-nums;">'
                f'{diff:+.1f}%</div>', unsafe_allow_html=True)
        elif prev is not None and prev["diff_pct"] is not None:
            st.markdown(
                f'<div style="padding-top:14px;color:{th["muted"]};'
                f'font-size:13px;">минулого разу '
                f'{float(prev["diff_pct"]):+.1f}%</div>',
                unsafe_allow_html=True)

    st.markdown(f'<div style="height:1px;background:{th["border"]};'
                f'margin:6px 0 10px 0;"></div>', unsafe_allow_html=True)

note = st.text_area("Нотатка (необов'язково)",
                    placeholder="Наприклад: сесії дивився за іншу дату, "
                                "бо звіт ще не оновився",
                    key="verify_note", height=80)

filled = {k: v for k, v in entries.items() if v is not None}

if st.button("Зберегти звірку", type="primary", disabled=not filled):
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            for key, actual in filled.items():
                our = ours.get(key)
                diff = ((actual - our) / our * 100
                        if our and our > 0 else None)
                cur.execute("""
                    INSERT INTO merinnovation.verification
                        (metric_key, our_value, actual_value, diff_pct,
                         note, checked_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (key, our, actual, diff, note or None,
                      user["username"]))
        conn.commit()
        conn.close()
        auth.log_action("verification", f"{len(filled)} метрик")
        q.clear()
        our_values.clear()
        st.success(f"Збережено {len(filled)} метрик")
        st.rerun()
    except Exception as e:
        st.error(f"Не вдалось зберегти: {e}")

# ------------------------------------------------------------ історія ----
st.markdown("---")
st.markdown("**Історія розбіжностей**")

hist = q("""
    SELECT check_date, metric_key, our_value, actual_value, diff_pct
    FROM merinnovation.verification
    ORDER BY check_date DESC, metric_key
    LIMIT 200
""")

if hist.empty:
    st.caption("Ще немає даних")
else:
    labels = {k: lbl for k, lbl, _, _ in METRICS}
    fmts = {k: f for k, _, _, f in METRICS}

    # графік: як розбіжність змінюється в часі
    plot_df = hist[hist["diff_pct"].notna()].copy()
    if len(plot_df) > 2:
        plot_df["label"] = plot_df["metric_key"].map(
            lambda k: labels.get(k, k))
        fig = go.Figure()
        for key in plot_df["metric_key"].unique():
            sub = plot_df[plot_df["metric_key"] == key].sort_values("check_date")
            if len(sub) < 2:
                continue
            fig.add_scatter(
                x=pd.to_datetime(sub["check_date"]).dt.strftime("%d.%m"),
                y=sub["diff_pct"].astype(float),
                mode="lines+markers", name=labels.get(key, key))
        fig.add_hline(y=0, line_color=ACCENT, opacity=0.5)
        fig.add_hline(y=10, line_dash="dot", line_color=AMBER, opacity=0.5)
        fig.add_hline(y=-10, line_dash="dot", line_color=AMBER, opacity=0.5)
        lk = plotly_layout(title="Розбіжність із Seller Central, %")
        lk["height"] = 340
        lk["xaxis"] = themed_axis(type="category", showgrid=False)
        lk["yaxis"] = themed_axis(ticksuffix="%")
        fig.update_layout(**lk)
        st.plotly_chart(fig, use_container_width=True)

    rows = []
    for _, r in hist.iterrows():
        d = r["diff_pct"]
        color = th["muted"]
        if d is not None:
            d = float(d)
            color = (ACCENT if abs(d) <= 5
                     else AMBER if abs(d) <= 15 else RED)
        fmt = fmts.get(r["metric_key"], "int")

        def f(v):
            if v is None:
                return "—"
            v = float(v)
            return f"${v:,.2f}" if fmt == "money" else f"{v:,.0f}"

        rows.append(
            f'<div style="display:flex;gap:16px;align-items:baseline;'
            f'padding:9px 0;border-bottom:1px solid {th["border"]};'
            f'font-size:13px;">'
            f'<span style="color:{th["muted"]};min-width:74px;">'
            f'{pd.to_datetime(r["check_date"]):%d.%m.%Y}</span>'
            f'<span style="color:{th["text"]};min-width:230px;">'
            f'{labels.get(r["metric_key"], r["metric_key"])}</span>'
            f'<span style="color:{th["muted"]};min-width:110px;'
            f'font-variant-numeric:tabular-nums;">у нас {f(r["our_value"])}'
            f'</span>'
            f'<span style="color:{th["muted"]};min-width:110px;'
            f'font-variant-numeric:tabular-nums;">факт {f(r["actual_value"])}'
            f'</span>'
            + (f'<span style="color:{color};font-weight:700;'
               f'font-variant-numeric:tabular-nums;">{d:+.1f}%</span>'
               if d is not None else "")
            + '</div>')
    st.markdown("".join(rows), unsafe_allow_html=True)

with st.expander("Як читати розбіжності"):
    st.markdown("""
**До 5%** — норма. SP-API і Seller Central рахують у різних часових
зонах і по-різному обробляють незакриті дні.

**5-15%** — варто подивитись. Можливо, різні періоди або фільтри:
Seller Central за замовчуванням показує один маркетплейс, а ми — усі.

**Понад 15%** — швидше за все помилка в нашому коді. Напиши в нотатці,
що саме дивився, і розберемось.

---

**Чого не варто чекати:**

Виручка ніколи не збігається до цента: ми беремо Ordered Product Sales
із Sales & Traffic, а дашборд Amazon може показувати Shipped.

Реклама розходиться, бо Amazon перераховує атрибуцію протягом
кількох днів після події.

Залишки збігаються лише якщо знімок свіжий: він робиться двічі на день.
""")

st.caption("Дані звірки зберігаються — з часом видно, чи стабільна "
           "розбіжність, чи це разовий випадок.") 
