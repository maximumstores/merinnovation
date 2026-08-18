# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — цінова база і планування акцій."""

import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth
from db import (ACCENT, ACCENT2, AMAZON_DOMAINS, cell_link, cur_theme,
                download_csv_button, inject_css, lang_selector, metric_card,
                mp_label, plotly_layout, q, render_html_table, sort_controls,
                t, themed_axis)

st.set_page_config(layout="wide", page_title="Merinnovation · Pricing",
                   page_icon="🐑")

auth.require_auth("10_Pricing")
lang_selector()
inject_css()
auth.sidebar_user_block()

th = cur_theme()
RED = "#ef4444"
AMBER = "#f59e0b"

STATUS_META = {
    "OK": (ACCENT, "У нормі", "готові до акцій"),
    "COOLDOWN": (AMBER, "Охолодження", "база відновлюється"),
    "RISK": (RED, "Ризик збитку", "знижка нижче собівартості"),
    "BROKEN": ("#a855f7", "База збита", "акції за нормальною ціною недоступні"),
}

st.markdown("## Цінова база")

# ------------------------------------------------- перевірка даних ----
tables = q("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema='merinnovation'
      AND table_name IN ('pricing_history','pricing_rules')
""")
existing = set(tables["table_name"]) if not tables.empty else set()

if "pricing_history" not in existing:
    st.info("Історія цін ще не збирається. Запусти на сервері:\n\n"
            "```\npython 15_pricing_history_loader.py\n```")
    st.stop()

depth = q("""
    SELECT COUNT(DISTINCT snapshot_date) AS days,
           MIN(snapshot_date) AS first_day,
           MAX(snapshot_date) AS last_day
    FROM merinnovation.pricing_history
""")
days = int(depth["days"].iloc[0] or 0) if not depth.empty else 0

if days == 0:
    st.info("Знімків цін ще немає — запусти 15_pricing_history_loader.py")
    st.stop()

# Amazon рахує мінімальну ціну за 30 днів. Поки історії менше —
# чесніше показати, скільки залишилось, ніж рахувати на неповних даних.
if days < 30:
    left = 30 - days
    st.markdown(
        f'<div style="background:{th["card"]};border:1px solid {AMBER}55;'
        f'border-left:4px solid {AMBER};border-radius:14px;'
        f'padding:20px 24px;margin-bottom:16px;">'
        f'<div style="color:{th["muted"]};font-size:11px;letter-spacing:.12em;'
        f'text-transform:uppercase;font-weight:700;margin-bottom:8px;">'
        f'⏳ Накопичення історії</div>'
        f'<div style="color:{th["text"]};font-size:22px;font-weight:700;">'
        f'{days} з 30 днів</div>'
        f'<div style="color:{th["muted"]};font-size:13px;margin-top:6px;">'
        f'Amazon рахує мінімальну ціну за ковзні 30 днів. Показники нижче '
        f'попередні — точними стануть через {left} дн.</div></div>',
        unsafe_allow_html=True)

if "pricing_rules" not in existing:
    st.info("Показники ще не розраховані. Запусти:\n\n"
            "```\npython 16_pricing_rules.py\n```")
    st.stop()

rules = q("""
    SELECT r.*, c.image_url
    FROM merinnovation.pricing_rules r
    LEFT JOIN merinnovation.catalog_images c
      ON c.asin = r.asin AND c.marketplace_id = r.marketplace_id
""")

if rules.empty:
    st.info("Розрахунок порожній — запусти 16_pricing_rules.py")
    st.stop()

for col in ["current_price", "lowest_30d", "reference_price", "deal_floor",
            "margin_now_pct", "margin_at_floor_pct", "gap_from_reference_pct",
            "unit_cost", "fba_fee"]:
    rules[col] = pd.to_numeric(rules[col], errors="coerce")

# ============================================ ЕКРАН 1: ПОРТФЕЛЬ ====
tab1, tab2, tab3 = st.tabs(["Огляд каталогу", "Симулятор по товару",
                            "Калькулятор медіани"])

with tab1:
    counts = rules["risk_status"].value_counts()
    n_risk = int(counts.get("RISK", 0))
    n_broken = int(counts.get("BROKEN", 0))
    n_cool = int(counts.get("COOLDOWN", 0))
    n_ok = int(counts.get("OK", 0))
    danger = n_risk + n_broken

    # головна цифра — скільки товарів не можна ставити в акцію
    if danger:
        st.markdown(
            f'<div style="background:{th["card"]};border:1px solid {RED}55;'
            f'border-left:4px solid {RED};border-radius:14px;'
            f'padding:22px 26px;margin-bottom:18px;">'
            f'<div style="color:{th["muted"]};font-size:11px;'
            f'letter-spacing:.12em;text-transform:uppercase;'
            f'font-weight:700;margin-bottom:8px;">'
            f'⚠️ Під загрозою втрати прибутку</div>'
            f'<div style="color:{RED};font-size:40px;font-weight:800;'
            f'line-height:1.05;">{danger} SKU</div>'
            f'<div style="color:{th["muted"]};font-size:13px;margin-top:8px;'
            f'max-width:640px;line-height:1.5;">'
            f'Знижка на розпродажі рахується від найнижчої ціни за 30 днів. '
            f'У цих товарів вона впала настільки, що участь в акції дасть '
            f'мінусову маржу або буде відхилена Amazon.</div></div>',
            unsafe_allow_html=True)
    else:
        st.success("Усі товари готові до акцій — базова ціна не збита")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("У нормі", f"{n_ok}", sub="готові до акцій")
    with c2:
        metric_card("Охолодження", f"{n_cool}", sub="база відновлюється")
    with c3:
        metric_card("Ризик збитку", f"{n_risk}", sub="знижка нижче витрат")
    with c4:
        metric_card("База збита", f"{n_broken}")

    st.markdown("")

    gl, gr = st.columns([1, 1])
    with gl:
        labels, values, colors = [], [], []
        for st_code in ("OK", "COOLDOWN", "RISK", "BROKEN"):
            n = int(counts.get(st_code, 0))
            if n:
                color, label, _ = STATUS_META[st_code]
                labels.append(label)
                values.append(n)
                colors.append(color)
        if values:
            fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.55,
                                   marker=dict(colors=colors),
                                   textinfo="value"))
            lk = plotly_layout(title="Статус цінової бази")
            lk["height"] = 320
            fig.update_layout(**lk)
            st.plotly_chart(fig, use_container_width=True)

    with gr:
        rows_s = []
        total = len(rules)
        for st_code in ("OK", "COOLDOWN", "RISK", "BROKEN"):
            n = int(counts.get(st_code, 0))
            if not n:
                continue
            color, label, hint = STATUS_META[st_code]
            share = n / total * 100 if total else 0
            rows_s.append(
                f'<div style="padding:14px 0;border-bottom:1px solid '
                f'{th["border"]};">'
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:baseline;">'
                f'<span style="color:{th["text"]};font-size:15px;'
                f'font-weight:600;">'
                f'<span style="color:{color};">●</span> {label}</span>'
                f'<span style="color:{color};font-weight:700;font-size:17px;">'
                f'{n}</span></div>'
                f'<div style="color:{th["muted"]};font-size:12px;'
                f'margin-top:4px;">{hint} · {share:.0f}% каталогу</div></div>')
        st.markdown(
            f'<div style="background:{th["card"]};border:1px solid '
            f'{th["border"]};border-radius:12px;padding:4px 20px 8px 20px;">'
            f'{"".join(rows_s)}</div>', unsafe_allow_html=True)

    # ---- матриця ризиків ----
    st.markdown("")
    st.markdown("**Матриця ризиків каталогу**")

    fc1, fc2, _ = st.columns([2, 3, 4])
    with fc1:
        st_filter = st.selectbox(
            "Статус", ["Потребують реакції", "Усі", "OK", "COOLDOWN",
                       "RISK", "BROKEN"], key="pr_status")
    with fc2:
        search = st.text_input("Пошук за SKU / ASIN", "", key="pr_search")

    view = rules.copy()
    if st_filter == "Потребують реакції":
        view = view[view["risk_status"].isin(["RISK", "BROKEN", "COOLDOWN"])]
    elif st_filter != "Усі":
        view = view[view["risk_status"] == st_filter]

    if search.strip():
        import re
        toks = [x.lower() for x in re.split(r"[,\s;]+", search.strip()) if x]
        mask = pd.Series(False, index=view.index)
        for tok in toks:
            mask |= (view["seller_sku"].str.lower().str.contains(tok, na=False)
                     | view["asin"].fillna("").str.lower().str.contains(tok, na=False))
        view = view[mask]

    view["asin_link"] = (
        "https://" + view["marketplace_id"].map(AMAZON_DOMAINS).fillna("amazon.com")
        + "/dp/" + view["asin"].fillna(""))

    st.caption(t("sort_hint"))
    sort_col, sort_asc = sort_controls(
        {"Маржа на порозі": "margin_at_floor_pct",
         "Падіння бази": "gap_from_reference_pct",
         "Поточна ціна": "current_price",
         "SKU": "seller_sku"},
        key="pricing", default_index=0, default_desc=False)
    view = view.sort_values(sort_col, ascending=sort_asc, na_position="last")

    ROW_CLASS = {"RISK": "row-zero", "BROKEN": "row-zero", "COOLDOWN": "row-low"}
    rows_t = []
    for rec in view.to_dict("records"):
        rec["_row_class"] = ROW_CLASS.get(rec["risk_status"], "")
        rows_t.append(rec)

    def fmt_money(key):
        return lambda r: (f"${r[key]:,.2f}" if pd.notna(r.get(key)) else "—")

    def fmt_margin(r):
        v = r.get("margin_at_floor_pct")
        if pd.isna(v):
            return "—"
        return f"{v:.0f}%"

    def fmt_status(r):
        code = r.get("risk_status")
        _, label, _ = STATUS_META.get(code, ("", code, ""))
        return label

    columns = [
        ("SKU", lambda r: str(r.get("seller_sku") or "")[:26]),
        ("ASIN", lambda r: cell_link(r.get("asin_link"), r.get("asin") or "")),
        ("Ref price", fmt_money("reference_price")),
        ("Мін. 30д", fmt_money("lowest_30d")),
        ("Поріг акції", fmt_money("deal_floor")),
        ("Маржа на порозі", fmt_margin),
        ("Статус", fmt_status),
    ]
    render_html_table(rows_t, columns, height=520)
    download_csv_button(
        view[["seller_sku", "asin", "current_price", "reference_price",
              "lowest_30d", "deal_floor", "margin_at_floor_pct",
              "risk_status"]],
        "pricing_rules", key="pricing")

    st.caption("Поріг акції — ціна, до якої доведеться впасти, щоб Amazon "
               "допустив товар до розпродажу (знижка від найнижчої ціни "
               "за 30 днів). Маржа рахується з урахуванням FBA і комісії.")

# ============================================ ЕКРАН 2: СИМУЛЯТОР ====
with tab2:
    sku_list = rules.sort_values("seller_sku")["seller_sku"].tolist()
    sel_sku = st.selectbox("Товар", sku_list, key="sim_sku")

    row = rules[rules["seller_sku"] == sel_sku].iloc[0]
    detail = row["detail"]
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except Exception:
            detail = {}
    detail = detail or {}

    color, label, hint = STATUS_META.get(row["risk_status"],
                                         (th["muted"], "—", ""))

    st.markdown(
        f'<div style="display:flex;gap:18px;align-items:center;'
        f'margin:6px 0 18px 0;">'
        f'<div style="width:5px;height:52px;border-radius:3px;'
        f'background:{color};"></div>'
        f'<div><div style="color:{th["muted"]};font-size:12px;">'
        f'{row["asin"] or ""} · {mp_label(row["marketplace_id"])}</div>'
        f'<div style="color:{th["text"]};font-size:22px;font-weight:700;">'
        f'{label} <span style="color:{th["muted"]};font-size:14px;'
        f'font-weight:400;">— {hint}</span></div></div></div>',
        unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        metric_card("Reference price",
                    f"${row['reference_price']:,.2f}"
                    if pd.notna(row["reference_price"]) else "—",
                    sub="база для знижки")
    with m2:
        metric_card("Мінімум за 30 днів",
                    f"${row['lowest_30d']:,.2f}"
                    if pd.notna(row["lowest_30d"]) else "—",
                    sub=(f"від {row['lowest_30d_date']}"
                         if pd.notna(row["lowest_30d_date"]) else None))
    with m3:
        metric_card("Поріг для акції",
                    f"${row['deal_floor']:,.2f}"
                    if pd.notna(row["deal_floor"]) else "—",
                    sub=f"-{detail.get('deal_discount_pct', 20)}% від мінімуму")
    with m4:
        mv = row["margin_at_floor_pct"]
        metric_card("Маржа на порозі",
                    f"{mv:.1f}%" if pd.notna(mv) else "—",
                    sub="після FBA і комісії")

    # попередження — головна цінність екрана
    if row["risk_status"] in ("RISK", "BROKEN"):
        st.markdown(
            f'<div style="background:{RED}0d;border:1px solid {RED}55;'
            f'border-left:4px solid {RED};border-radius:12px;'
            f'padding:18px 22px;margin:16px 0;">'
            f'<div style="color:{RED};font-size:12px;letter-spacing:.1em;'
            f'text-transform:uppercase;font-weight:700;margin-bottom:8px;">'
            f'Попередження</div>'
            f'<div style="color:{th["text"]};font-size:15px;line-height:1.6;">'
            f'{detail.get("reason", "")}</div></div>',
            unsafe_allow_html=True)

    # ---- історія цін ----
    hist = q("""
        SELECT snapshot_date,
               COALESCE(landed_price, listing_price) AS price,
               buybox_price
        FROM merinnovation.pricing_history
        WHERE seller_sku = %s
        ORDER BY snapshot_date
    """, (sel_sku,))

    if not hist.empty and len(hist) > 1:
        hist["label"] = pd.to_datetime(hist["snapshot_date"]).dt.strftime("%d.%m")
        fig = go.Figure()
        fig.add_scatter(x=hist["label"], y=hist["price"], name="Наша ціна",
                        mode="lines+markers", line=dict(color=ACCENT2, width=2))
        if hist["buybox_price"].notna().any():
            fig.add_scatter(x=hist["label"], y=hist["buybox_price"],
                            name="Buy Box", mode="lines",
                            line=dict(color=th["muted"], width=1, dash="dot"))

        # три горизонталі, на яких і будується рішення
        if pd.notna(row["reference_price"]):
            fig.add_hline(y=float(row["reference_price"]), line_dash="dash",
                          line_color=ACCENT, opacity=0.7,
                          annotation_text="Reference")
        if pd.notna(row["lowest_30d"]):
            fig.add_hline(y=float(row["lowest_30d"]), line_dash="dot",
                          line_color=AMBER, opacity=0.7,
                          annotation_text="Мін. 30д")
        if pd.notna(row["deal_floor"]):
            fig.add_hline(y=float(row["deal_floor"]), line_dash="dot",
                          line_color=RED, opacity=0.7,
                          annotation_text="Поріг акції")

        lk = plotly_layout(title="Рух ціни і межі")
        lk["height"] = 380
        lk["xaxis"] = themed_axis(type="category", showgrid=False)
        fig.update_layout(**lk)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Для графіка потрібно щонайменше 2 дні історії")

    # ---- симуляція знижки ----
    st.markdown("")
    st.markdown("**Що буде, якщо дати знижку**")

    sc1, sc2, _ = st.columns([2, 2, 4])
    with sc1:
        disc = st.slider("Знижка, %", 0, 60, 15, step=5, key="sim_disc")
    with sc2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        current = float(row["current_price"]) if pd.notna(row["current_price"]) else 0
        promo_price = round(current * (1 - disc / 100), 2)

    unit_cost = float(row["unit_cost"] or 0)
    fba = float(row["fba_fee"] or 0)
    referral_pct = 15

    def margin_at(price):
        if price <= 0:
            return None
        net = price - unit_cost - fba - price * referral_pct / 100
        return net / price * 100

    promo_margin = margin_at(promo_price)
    # ось головне: після цієї акції мінімум за 30 днів стане promo_price,
    # і наступна знижка рахуватиметься вже від неї
    future_lowest = min(float(row["lowest_30d"] or promo_price), promo_price)
    future_floor = round(future_lowest * 0.8, 2)
    future_margin = margin_at(future_floor)

    r1, r2, r3 = st.columns(3)
    with r1:
        metric_card("Ціна з промо", f"${promo_price:,.2f}",
                    sub=f"маржа {promo_margin:.1f}%"
                    if promo_margin is not None else None)
    with r2:
        metric_card("Новий мінімум 30д", f"${future_lowest:,.2f}",
                    sub="діятиме наступні 30 днів")
    with r3:
        metric_card("Поріг майбутніх акцій", f"${future_floor:,.2f}",
                    sub=f"маржа {future_margin:.1f}%"
                    if future_margin is not None else None)

    if future_margin is not None and future_margin < 0:
        st.markdown(
            f'<div style="background:{RED}0d;border:1px solid {RED}55;'
            f'border-left:4px solid {RED};border-radius:12px;'
            f'padding:16px 20px;margin-top:12px;">'
            f'<div style="color:{th["text"]};font-size:15px;line-height:1.6;">'
            f'Ця знижка опустить мінімальну ціну до '
            f'<b>${future_lowest:,.2f}</b>. Наступні 30 днів Amazon '
            f'вимагатиме для акцій ціну <b>${future_floor:,.2f}</b>, '
            f'а це маржа <b>{future_margin:.1f}%</b> — участь у '
            f'великих розпродажах стане збитковою.</div></div>',
            unsafe_allow_html=True)
    elif promo_margin is not None and promo_margin < 0:
        st.warning(f"Сама акція вже збиткова: маржа {promo_margin:.1f}%")
    else:
        st.success(f"Знижка безпечна: після неї поріг майбутніх акцій "
                   f"${future_floor:,.2f} з маржею {future_margin:.1f}%")




# ==================================== ЕКРАН 3: КАЛЬКУЛЯТОР МЕДІАНИ ====
with tab3:
    st.markdown("**Скільки тримати ціну, щоб підняти медіану**")
    st.caption(
        "З травня 2026 Amazon допускає до Best Deal за МЕДІАННОЮ ціною "
        "у вікні 90 днів. Медіана рахується за кількістю проданих одиниць: "
        "щоб її підняти, треба продати більше половини вікна за новою ціною."
    )

    # чи є розрахована медіана
    has_median = q("""
        SELECT COUNT(*) AS n FROM information_schema.tables
        WHERE table_schema='merinnovation' AND table_name='median_price'
    """)
    median_ready = not has_median.empty and int(has_median["n"].iloc[0]) > 0

    med_row = None
    if median_ready:
        med_list = q("""
            SELECT seller_sku, median_price, current_price, velocity_per_day,
                   units_total, min_price_in_window, max_price_in_window
            FROM merinnovation.median_price
            ORDER BY units_total DESC
        """)
        if not med_list.empty:
            pick = st.selectbox(
                "Підставити дані з бази", ["— ввести вручну —"]
                + med_list["seller_sku"].tolist(), key="calc_sku")
            if pick != "— ввести вручну —":
                med_row = med_list[med_list["seller_sku"] == pick].iloc[0]

    st.markdown("")
    st.markdown("**Вводні**")
    st.caption("Швидкість при новій ціні — головний параметр. "
               "Якщо не знаєте, запустіть тест на 7 днів і підставте факт.")

    i1, i2, i3, i4 = st.columns(4)
    with i1:
        cur_price = st.number_input(
            "Поточна ціна, $", min_value=0.01, step=0.01, format="%.2f",
            value=float(med_row["current_price"]) if med_row is not None
            else 24.99, key="calc_cur")
    with i2:
        target_price = st.number_input(
            "Цільова медіана, $", min_value=0.01, step=0.01, format="%.2f",
            value=float(med_row["current_price"]) if med_row is not None
            else 29.99, key="calc_target",
            help="Ціна, до якої хочемо підняти базу")
    with i3:
        v_now = st.number_input(
            "Швидкість зараз, од/день", min_value=0.0, step=0.1,
            value=float(med_row["velocity_per_day"]) if med_row is not None
            else 20.0, key="calc_vnow")
    with i4:
        v_new = st.number_input(
            "Швидкість при новій ціні", min_value=0.0, step=0.1,
            value=(round(float(med_row["velocity_per_day"]) * 0.6, 2)
                   if med_row is not None else 12.0), key="calc_vnew",
            help="Скільки реально продаватимете за новою ціною. "
                 "Це головне число — від нього залежить усе.")

    j1, j2, j3, j4 = st.columns(4)
    with j1:
        already_pct = st.number_input(
            "Продажів уже ≥ цільової, %", min_value=0.0, max_value=100.0,
            step=1.0, value=0.0, key="calc_already",
            help="Яка частка вікна вже продана за цільовою ціною або вище")
    with j2:
        days_since_low = st.number_input(
            "Днів з останньої низької ціни", min_value=0, step=1, value=0,
            key="calc_since")
    with j3:
        deal_type = st.selectbox(
            "Тип дедлайну — ціновий пол",
            ["Звичайний Best Deal (30 дн)", "Prime Day / BFCM (60 дн)"],
            key="calc_deal")
    with j4:
        buffer_days = st.number_input(
            "Буфер на перерахунок, днів", min_value=0, step=1, value=5,
            key="calc_buffer",
            help="Amazon перераховує медіану не миттєво")

    # ---------------------------------------------------- розрахунок ----
    import math

    WINDOW = 90
    floor_days = 60 if "Prime" in deal_type else 30

    # Уже наявні одиниці за цільовою ціною скорочують шлях: вони теж
    # рахуються в половину вікна.
    effective_low = v_now * (1 - already_pct / 100)

    if v_new <= 0:
        days_median = float("inf")
    elif effective_low <= 0:
        days_median = 0
    else:
        days_median = math.ceil(WINDOW * effective_low / (v_new + effective_low))

    days_median_total = (days_median + buffer_days
                         if days_median != float("inf") else float("inf"))

    # ціновий пол рахується від останньої низької ціни
    days_floor = max(floor_days - days_since_low, 0)

    total_days = (max(days_median_total, days_floor)
                  if days_median_total != float("inf") else float("inf"))

    binding = ("медіана" if days_median_total >= days_floor else "ціновий пол")

    st.markdown("---")
    st.markdown("**Результат**")

    if total_days == float("inf"):
        st.error("За нульової швидкості продажів медіана не підніметься "
                 "ніколи. Введіть очікувану швидкість більше нуля.")
    else:
        ready_date = (datetime.now() + timedelta(days=int(total_days))).date()

        st.markdown(
            f'<div style="display:flex;align-items:baseline;gap:14px;'
            f'margin:8px 0 6px 0;">'
            f'<span style="color:{th["text"]};font-size:58px;font-weight:800;'
            f'line-height:1;font-variant-numeric:tabular-nums;">'
            f'{int(total_days)}</span>'
            f'<span style="color:{th["muted"]};font-size:20px;">днів</span>'
            f'</div>'
            f'<div style="color:{th["muted"]};font-size:14px;'
            f'margin-bottom:14px;">Тримати ціну ${target_price:,.2f} '
            f'починаючи з сьогодні. Подавати заявку на дедлайн можна '
            f'з <b style="color:{th["text"]};">'
            f'{ready_date.strftime("%d.%m.%Y")}</b></div>',
            unsafe_allow_html=True)

        note_color = AMBER if binding == "медіана" else ACCENT2
        note_text = (
            f"Зв'язує медіана. Ціновий пол звільниться через "
            f"{int(days_floor)} дн."
            if binding == "медіана" else
            f"Зв'язує ціновий пол ({floor_days} дн). "
            f"Медіана підніметься за {int(days_median_total)} дн.")
        st.markdown(
            f'<div style="background:{th["card"]};border:1px solid '
            f'{note_color}55;border-left:3px solid {note_color};'
            f'border-radius:10px;padding:12px 18px;margin-bottom:18px;">'
            f'<span style="color:{th["text"]};font-size:14px;">'
            f'● {note_text}</span></div>', unsafe_allow_html=True)

        undersold = (v_now - v_new) * total_days
        rev_stay = v_now * total_days * cur_price
        rev_raise = v_new * total_days * target_price
        delta_rev = rev_raise - rev_stay

        r1, r2, r3, r4 = st.columns(4)
        with r1:
            metric_card("Строк по медіані",
                        f"{int(days_median_total)} дн"
                        if days_median_total != float("inf") else "—")
        with r2:
            metric_card("Строк по ціновому полу", f"{int(days_floor)} дн")
        with r3:
            metric_card("Недопродано одиниць", f"{undersold:,.0f}",
                        sub="проти поточної швидкості")
        with r4:
            metric_card("Δ виручки за період", f"${delta_rev:,.0f}",
                        sub="підняття ціни проти теперішнього")

        # ---- як змінюється склад вікна ----
        st.markdown("")
        st.markdown("**Як змінюється склад 90-денного вікна**")
        st.caption("Медіана піднімається в той момент, коли одиниці за "
                   "цільовою ціною займають більше половини вікна. "
                   "Пунктир — поріг 50%.")

        horizon = int(min(max(total_days + 20, 40), 120))
        xs, share = [], []
        for d in range(horizon + 1):
            units_new = v_new * d
            units_old = effective_low * max(WINDOW - d, 0)
            tot = units_new + units_old
            xs.append(d)
            share.append(units_new / tot * 100 if tot > 0 else 0)

        figc = go.Figure()
        figc.add_scatter(x=xs, y=share, mode="lines", name="Частка нової ціни",
                         line=dict(color=ACCENT, width=3),
                         fill="tozeroy", fillcolor=f"{ACCENT}22")
        figc.add_hline(y=50, line_dash="dash", line_color=AMBER,
                       annotation_text="поріг 50%")
        if days_median != float("inf"):
            figc.add_vline(x=int(days_median), line_dash="dot",
                           line_color=th["muted"],
                           annotation_text=f"{int(days_median)} дн")
        lk = plotly_layout()
        lk["height"] = 320
        lk["xaxis"] = themed_axis(title="днів від сьогодні", showgrid=False)
        lk["yaxis"] = themed_axis(title="частка вікна, %", ticksuffix="%")
        figc.update_layout(**lk)
        st.plotly_chart(figc, use_container_width=True)

        if v_new >= v_now:
            st.info("Швидкість при новій ціні задана не нижчою за поточну. "
                    "Зазвичай підняття ціни зменшує продажі — перевірте, "
                    "чи це реалістично.")

        st.caption(
            f"Формула: D = 90 × V_поточна / (V_нова + V_поточна), "
            f"округлення вгору, плюс буфер {int(buffer_days)} дн. "
            f"Мінімальний строк для {deal_type.split('(')[0].strip()} — "
            f"{floor_days} днів незалежно від обсягу продажів."
        )


st.caption("Розрахунок на щоденних знімках виставленої ціни та медіані "
           "за проданими одиницями. Amazon рахує допуск до акцій "
           "саме за медіаною у вікні 90 днів.")
