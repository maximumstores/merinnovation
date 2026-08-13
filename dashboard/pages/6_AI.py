# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — ІІ-аналітик.

Порядок читання: вердикт → гроші → що робити → докази → напрями.
Спершу відповідь, потім обґрунтування — власник має зрозуміти за 30 секунд.
"""

import json
import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import (ACCENT, ACCENT2, cur_theme, get_conn, inject_css,
                lang_selector, plotly_layout, q, t, themed_axis)

st.set_page_config(layout="wide", page_title="Merinnovation · AI", page_icon="🐑")
lang_selector()
inject_css()

th = cur_theme()
RED = "#ef4444"
AMBER = "#f59e0b"

SEV = {
    "critical": (RED, "🔴"),
    "warning": (AMBER, "🟠"),
    "ok": (ACCENT, "🟢"),
}
AGENT_ICONS = {"main": "🧠", "money": "💸", "sales": "📈", "stock": "📦",
               "forecast": "🔮", "finance": "💰", "traffic": "🔍"}
AGENT_ORDER = ["main", "money", "stock", "forecast", "sales", "finance", "traffic"]

# додаткові стилі сторінки: табличні цифри для сум, тонкі роздільники
st.markdown(f"""
<style>
.rp-num {{ font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }}
.rp-eyebrow {{ color:{th["muted"]}; font-size:11px; letter-spacing:.14em;
  text-transform:uppercase; font-weight:700; }}
.rp-rule {{ height:1px; background:{th["border"]}; margin:26px 0 20px 0; }}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------- перевірка таблиці ----
exists = q("""
    SELECT COUNT(*) AS n FROM information_schema.tables
    WHERE table_schema='merinnovation' AND table_name='ai_insights'
""")
if exists.empty or int(exists["n"].iloc[0]) == 0:
    st.info(t("no_ai_data"))
    st.stop()

dates = q("""
    SELECT DISTINCT report_date FROM merinnovation.ai_insights
    ORDER BY report_date DESC LIMIT 30
""")
if dates.empty:
    st.info(t("no_ai_data"))
    st.stop()

date_options = pd.to_datetime(dates["report_date"]).dt.date.tolist()

has_lang_col = q("""
    SELECT COUNT(*) AS n FROM information_schema.columns
    WHERE table_schema='merinnovation' AND table_name='ai_insights'
      AND column_name='lang'
""")
lang_supported = not has_lang_col.empty and int(has_lang_col["n"].iloc[0]) > 0

# ------------------------------------------------------------ панель ----
fc1, fc2, fc3, fc4 = st.columns([2, 2, 3, 2])
with fc1:
    sel_date = st.selectbox(t("ai_report_date"), date_options,
                            format_func=lambda d: d.strftime("%d.%m.%Y"),
                            key="ai_date")

ui_lang = st.session_state.get("lang", "uk")
sel_lang = ui_lang
if lang_supported:
    la = q("""
        SELECT DISTINCT COALESCE(lang,'uk') AS lang
        FROM merinnovation.ai_insights WHERE report_date = %s
    """, (sel_date,))
    available = la["lang"].tolist() if not la.empty else ["uk"]
    sel_lang = ui_lang if ui_lang in available else available[0]
    if len(available) > 1:
        with fc2:
            names = {"uk": "Українська", "ru": "Русский", "en": "English"}
            sel_lang = st.selectbox(t("ai_text_lang"), available,
                                    index=available.index(sel_lang),
                                    format_func=lambda x: names.get(x, x),
                                    key="ai_lang")

_queued = None
_queued_err = None
with fc4:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    if st.button(t("ai_refresh"), key="ai_refresh_btn",
                 icon=":material/refresh:", use_container_width=True):
        try:
            q.clear()
            with get_conn().cursor() as cur:
                cur.execute("""
                    INSERT INTO merinnovation.job_queue (script, requested_by)
                    VALUES ('10_ai_analyst.py', 'dashboard')
                """)
            _queued = t("ai_refresh_queued")
        except Exception as e:
            _queued_err = str(e)

# повідомлення поза колонками — на всю ширину, інакше розтягує колонку
if _queued:
    st.success(_queued, icon="⏳")
if _queued_err:
    st.error(f"{t('ai_refresh_failed')}: {_queued_err}")

try:
    lj = q("""
        SELECT status, requested_at FROM merinnovation.job_queue
        WHERE script = '10_ai_analyst.py'
        ORDER BY requested_at DESC LIMIT 1
    """)
    if not lj.empty:
        j = lj.iloc[0]
        age_min = (pd.Timestamp.now(tz="UTC")
                   - pd.to_datetime(j["requested_at"], utc=True)).total_seconds() / 60
        if j["status"] in ("pending", "running") and age_min < 30:
            st.info(t("ai_job_running") if j["status"] == "running"
                    else t("ai_job_pending"))
except Exception:
    pass

# -------------------------------------------------------------- дані ----
if lang_supported:
    insights = q("""
        SELECT DISTINCT ON (agent) agent, title, content, structured,
               model, created_at
        FROM merinnovation.ai_insights
        WHERE report_date = %s AND COALESCE(lang,'uk') = %s
        ORDER BY agent, created_at DESC
    """, (sel_date, sel_lang))
else:
    insights = q("""
        SELECT DISTINCT ON (agent) agent, title, content, structured,
               model, created_at
        FROM merinnovation.ai_insights
        WHERE report_date = %s ORDER BY agent, created_at DESC
    """, (sel_date,))

# Якщо за обрану дату/мову порожньо — не показуємо "немає даних",
# а беремо останній наявний звіт. База може бути в іншій часовій зоні,
# і report_date не збігається з "сьогодні" у кабінеті.
if insights.empty and lang_supported:
    insights = q("""
        SELECT DISTINCT ON (agent) agent, title, content, structured,
               model, created_at
        FROM merinnovation.ai_insights
        WHERE report_date = %s
        ORDER BY agent, created_at DESC
    """, (sel_date,))

if insights.empty:
    fallback = q("""
        SELECT MAX(report_date) AS d FROM merinnovation.ai_insights
    """)
    if not fallback.empty and pd.notna(fallback["d"].iloc[0]):
        real_date = pd.to_datetime(fallback["d"].iloc[0]).date()
        insights = q("""
            SELECT DISTINCT ON (agent) agent, title, content, structured,
                   model, created_at
            FROM merinnovation.ai_insights
            WHERE report_date = %s
            ORDER BY agent, created_at DESC
        """, (real_date,))
        if not insights.empty and real_date != sel_date:
            st.caption(t("ai_showing_date").format(
                d=real_date.strftime("%d.%m.%Y")))

if insights.empty:
    st.info(t("no_ai_data"))
    st.stop()


def parsed_of(row) -> dict:
    s = row.get("structured")
    if isinstance(s, dict):
        return s
    if isinstance(s, str) and s.strip():
        try:
            return json.loads(s)
        except Exception:
            pass
    return {"headline": (row.get("content") or "")[:400],
            "severity": "ok", "findings": [], "actions": []}


def esc(x) -> str:
    return str(x or "").replace("<", "&lt;").replace(">", "&gt;")


main_row = insights[insights["agent"] == "main"]
main = parsed_of(main_row.iloc[0]) if not main_row.empty else None

# ================================================== 1. ВЕРДИКТ ====
if main:
    color, icon = SEV.get(main.get("severity", "ok"), SEV["ok"])
    label = {"critical": t("sev_critical"), "warning": t("sev_warning"),
             "ok": t("sev_ok")}.get(main.get("severity", "ok"), "")

    st.markdown(
        f'<div style="display:flex;gap:20px;align-items:stretch;'
        f'margin:6px 0 4px 0;">'
        # вертикальна смуга стану — як позначка на полях у звіті
        f'<div style="width:5px;border-radius:3px;background:{color};'
        f'flex-shrink:0;"></div>'
        f'<div style="flex:1;">'
        f'<div class="rp-eyebrow" style="color:{color};margin-bottom:12px;">'
        f'{icon} {label} · {sel_date.strftime("%d.%m.%Y")}</div>'
        f'<div style="color:{th["text"]};font-size:30px;font-weight:700;'
        f'line-height:1.28;letter-spacing:-0.02em;max-width:1000px;">'
        f'{esc(main.get("headline"))}</div>'
        f'</div></div>', unsafe_allow_html=True)

st.markdown('<div class="rp-rule"></div>', unsafe_allow_html=True)

# ============================== 2. ГРОШОВИЙ РЕЄСТР (фірмовий блок) ====
leak_ok = q("""
    SELECT COUNT(*) AS n FROM information_schema.columns
    WHERE table_schema='merinnovation' AND table_name='money_leaks'
      AND column_name='category'
""")
has_leaks = not leak_ok.empty and int(leak_ok["n"].iloc[0]) > 0

LEAK_LABELS = {
    "STOCKOUT_NOW": t("leak_stockout_now"),
    "STOCKOUT_SOON": t("leak_stockout_soon"),
    "CONVERSION_GAP": t("leak_conversion"),
    "REFUNDS": t("leak_refunds"),
    "FEE_BURDEN": t("leak_fees"),
    "DEAD_STOCK": t("leak_dead_stock"),
}

if has_leaks:
    by_type = q("""
        SELECT category, leak_type, COUNT(*) AS sku_count, SUM(amount_usd) AS usd
        FROM merinnovation.money_leaks GROUP BY 1,2 ORDER BY 4 DESC
    """)
    if not by_type.empty:
        lost = by_type[by_type["category"] == "lost_revenue"]
        frozen = by_type[by_type["category"] == "frozen_capital"]
        tot_lost = float(lost["usd"].sum()) if not lost.empty else 0.0
        tot_frozen = float(frozen["usd"].sum()) if not frozen.empty else 0.0

        # рядки розкладки втрат
        breakdown = "".join(
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:baseline;padding:7px 0;">'
            f'<span style="color:{th["muted"]};font-size:13px;">'
            f'{LEAK_LABELS.get(r["leak_type"], r["leak_type"])}'
            f'<span style="opacity:.6;"> · {int(r["sku_count"])} SKU</span></span>'
            f'<span class="rp-num" style="color:{th["text"]};font-size:14px;'
            f'font-weight:600;">${float(r["usd"]):,.0f}</span></div>'
            for _, r in lost.sort_values("usd", ascending=False).iterrows())

        st.markdown(
            f'<div style="display:grid;grid-template-columns:1.15fr 1fr;'
            f'gap:18px;margin-bottom:8px;">'

            # ліворуч: втрачено — головна цифра звіту
            f'<div style="border:1px solid {RED}44;border-radius:16px;'
            f'padding:22px 26px;background:{th["card"]};">'
            f'<div class="rp-eyebrow">{t("leaks_lost_title")}</div>'
            f'<div class="rp-num" style="color:{RED};font-size:44px;'
            f'font-weight:800;line-height:1.05;margin:10px 0 2px 0;'
            f'letter-spacing:-0.03em;">${tot_lost:,.0f}</div>'
            f'<div style="color:{th["muted"]};font-size:12px;'
            f'margin-bottom:14px;">{t("leaks_lost_note")}</div>'
            f'<div style="border-top:1px solid {th["border"]};padding-top:6px;">'
            f'{breakdown}</div></div>'

            # праворуч: заморожено — навмисно тихіше, це не втрата
            f'<div style="border:1px solid {th["border"]};border-radius:16px;'
            f'padding:22px 26px;background:{th["card"]};">'
            f'<div class="rp-eyebrow">{t("leaks_frozen_title")}</div>'
            f'<div class="rp-num" style="color:{ACCENT2};font-size:44px;'
            f'font-weight:800;line-height:1.05;margin:10px 0 2px 0;'
            f'letter-spacing:-0.03em;">${tot_frozen:,.0f}</div>'
            f'<div style="color:{th["muted"]};font-size:12px;">'
            f'{t("leaks_frozen_note")}</div>'
            f'<div style="margin-top:18px;padding-top:14px;'
            f'border-top:1px solid {th["border"]};color:{th["muted"]};'
            f'font-size:12px;line-height:1.6;">{t("leaks_frozen_hint")}</div>'
            f'</div></div>', unsafe_allow_html=True)

# ================================================ 3. ЩО РОБИТИ ====
if main and (main.get("actions") or []):
    st.markdown('<div class="rp-rule"></div>', unsafe_allow_html=True)
    items = "".join(
        f'<div style="display:flex;gap:14px;align-items:flex-start;'
        f'padding:12px 0;border-bottom:1px solid {th["border"]};">'
        f'<span class="rp-num" style="color:{ACCENT};font-weight:800;'
        f'font-size:13px;min-width:22px;padding-top:1px;">{i:02d}</span>'
        f'<span style="color:{th["text"]};font-size:15px;line-height:1.5;">'
        f'{esc(a)}</span></div>'
        for i, a in enumerate(main["actions"], 1))
    st.markdown(
        f'<div class="rp-eyebrow" style="color:{ACCENT};margin-bottom:6px;">'
        f'{t("ai_actions")}</div>'
        f'<div style="border-left:3px solid {ACCENT};padding-left:20px;">'
        f'{items}</div>', unsafe_allow_html=True)

# ================================================== 4. ДОКАЗИ ====
if main and (main.get("findings") or []):
    st.markdown('<div class="rp-rule"></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="rp-eyebrow" style="margin-bottom:8px;">'
                f'{t("ai_evidence")}</div>', unsafe_allow_html=True)

    rows = []
    for f in main["findings"]:
        d = f.get("direction")
        arrow = {"up": "▲", "down": "▼"}.get(d, "")
        col = {"up": ACCENT, "down": RED}.get(d, th["muted"])
        metric = esc(f.get("metric"))
        rows.append(
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:baseline;gap:24px;padding:13px 0;'
            f'border-bottom:1px solid {th["border"]};">'
            f'<span style="color:{th["text"]};font-size:15px;line-height:1.5;">'
            f'{esc(f.get("text"))}</span>'
            + (f'<span class="rp-num" style="color:{col};font-weight:750;'
               f'font-size:17px;white-space:nowrap;">{arrow} {metric}</span>'
               if metric else "")
            + '</div>')
    st.markdown("".join(rows), unsafe_allow_html=True)

# ============================================= 5. ЗА НАПРЯМАМИ ====
others = insights[insights["agent"] != "main"].copy()
if not others.empty:
    st.markdown('<div class="rp-rule"></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="rp-eyebrow" style="margin-bottom:14px;">'
                f'{t("ai_by_agent")}</div>', unsafe_allow_html=True)

    others["ord"] = others["agent"].apply(
        lambda a: AGENT_ORDER.index(a) if a in AGENT_ORDER else 99)
    others = others.sort_values("ord")

    for _, row in others.iterrows():
        d = parsed_of(row)
        color, icon = SEV.get(d.get("severity", "ok"), SEV["ok"])
        title = esc(row["title"])
        head = esc(d.get("headline"))

        with st.expander(f"{AGENT_ICONS.get(row['agent'], '•')} {title}",
                         expanded=False):
            st.markdown(
                f'<div style="border-left:3px solid {color};padding-left:16px;'
                f'margin-bottom:14px;">'
                f'<div style="color:{th["text"]};font-size:16px;'
                f'font-weight:600;line-height:1.4;">{head}</div></div>',
                unsafe_allow_html=True)

            fr = []
            for f in (d.get("findings") or []):
                dd = f.get("direction")
                arrow = {"up": "▲", "down": "▼"}.get(dd, "")
                col = {"up": ACCENT, "down": RED}.get(dd, th["muted"])
                metric = esc(f.get("metric"))
                fr.append(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'align-items:baseline;gap:18px;padding:9px 0;'
                    f'border-bottom:1px solid {th["border"]};">'
                    f'<span style="color:{th["text"]};font-size:14px;'
                    f'line-height:1.5;">{esc(f.get("text"))}</span>'
                    + (f'<span class="rp-num" style="color:{col};'
                       f'font-weight:700;white-space:nowrap;">'
                       f'{arrow} {metric}</span>' if metric else "")
                    + '</div>')
            if fr:
                st.markdown("".join(fr), unsafe_allow_html=True)

            acts = d.get("actions") or []
            if acts:
                st.markdown(
                    f'<div style="margin-top:12px;color:{ACCENT};'
                    f'font-size:11px;letter-spacing:.12em;'
                    f'text-transform:uppercase;font-weight:700;">'
                    f'{t("ai_actions")}</div>'
                    + "".join(
                        f'<div style="color:{th["text"]};font-size:14px;'
                        f'padding:6px 0;">→ {esc(a)}</div>' for a in acts),
                    unsafe_allow_html=True)

# ============================================ 6. ОПОРНІ ЦИФРИ ====
st.markdown('<div class="rp-rule"></div>', unsafe_allow_html=True)
st.markdown(f'<div class="rp-eyebrow" style="margin-bottom:10px;">'
            f'{t("ai_supporting_data")}</div>', unsafe_allow_html=True)

daily = q("""
    SELECT purchase_date::date AS day, COUNT(*) AS orders
    FROM merinnovation.orders
    WHERE purchase_date >= NOW() - INTERVAL '30 days'
      AND order_status <> 'Canceled'
    GROUP BY 1 ORDER BY 1
""")
if not daily.empty:
    daily["label"] = pd.to_datetime(daily["day"]).dt.strftime("%d.%m")
    fig = go.Figure(go.Bar(x=daily["label"], y=daily["orders"],
                           marker_color=ACCENT))
    lk = plotly_layout(title=t("ai_orders_chart"))
    lk["height"] = 240
    lk["xaxis"] = themed_axis(type="category", showgrid=False)
    fig.update_layout(**lk)
    st.plotly_chart(fig, use_container_width=True)

if not main_row.empty:
    r = main_row.iloc[0]
    st.caption(f"{t('ai_model')}: {r['model']} · "
               f"{pd.to_datetime(r['created_at']):%d.%m.%Y %H:%M}")

# ------------------------------------------------------------ історія ----
with st.expander(t("ai_history")):
    if lang_supported:
        hist = q("""
            SELECT report_date, structured, content
            FROM merinnovation.ai_insights
            WHERE agent='main' AND COALESCE(lang,'uk')=%s
            ORDER BY created_at DESC LIMIT 14
        """, (sel_lang,))
    else:
        hist = q("""
            SELECT report_date, structured, content
            FROM merinnovation.ai_insights
            WHERE agent='main' ORDER BY created_at DESC LIMIT 14
        """)
    if hist.empty:
        st.caption(t("no_ai_data"))
    else:
        for _, r in hist.iterrows():
            d = parsed_of(r)
            day = pd.to_datetime(r["report_date"]).strftime("%d.%m")
            color, icon = SEV.get(d.get("severity", "ok"), SEV["ok"])
            st.markdown(
                f'<div style="display:flex;gap:14px;padding:10px 0;'
                f'border-bottom:1px solid {th["border"]};">'
                f'<span class="rp-num" style="color:{th["muted"]};'
                f'font-size:13px;min-width:44px;">{day}</span>'
                f'<span style="color:{th["text"]};font-size:14px;'
                f'line-height:1.5;">{icon} {esc(d.get("headline"))}</span>'
                f'</div>', unsafe_allow_html=True)

st.caption(t("ai_cache_note"))
