# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — алерти системи (те саме, що йде в Telegram)."""

import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import (ACCENT, cur_theme, inject_css, lang_selector, metric_card, q, t)

st.set_page_config(layout="wide", page_title="Merinnovation · Alerts",
                   page_icon="🐑")
lang_selector()
inject_css()

th = cur_theme()

LEVEL = {
    "CRITICAL": ("#ef4444", "🔴"),
    "WARNING": ("#f59e0b", "🟠"),
    "INFO": (ACCENT, "🔵"),
}

st.markdown(f"## {t('alerts_title')}")

exists = q("""
    SELECT COUNT(*) AS n FROM information_schema.tables
    WHERE table_schema='merinnovation' AND table_name='alerts'
""")
if exists.empty or int(exists["n"].iloc[0]) == 0:
    st.info(t("no_alerts_data"))
    st.stop()

# ------------------------------------------------------------ відкриті ----
open_alerts = q("""
    SELECT code, level, message, first_seen, last_seen, occurrences,
           EXTRACT(EPOCH FROM (now() - first_seen))/3600 AS hours_open
    FROM merinnovation.alerts
    WHERE resolved_at IS NULL
    ORDER BY CASE level WHEN 'CRITICAL' THEN 1 WHEN 'WARNING' THEN 2
                        ELSE 3 END, first_seen
""")

n_crit = int((open_alerts["level"] == "CRITICAL").sum()) if not open_alerts.empty else 0
n_warn = int((open_alerts["level"] == "WARNING").sum()) if not open_alerts.empty else 0

last_run = q("""
    SELECT MAX(last_seen) AS ts FROM merinnovation.alerts
""")
ts = pd.to_datetime(last_run["ts"].iloc[0]) if not last_run.empty else None

c1, c2, c3 = st.columns(3)
with c1:
    metric_card(t("alerts_critical"), f"{n_crit}",
                sub=t("alerts_need_action") if n_crit else None)
with c2:
    metric_card(t("alerts_warning"), f"{n_warn}")
with c3:
    metric_card(t("alerts_last_check"),
                ts.strftime("%d.%m %H:%M") if ts is not None else "—")

st.markdown("")

info_alerts = (open_alerts[open_alerts["level"] == "INFO"]
               if not open_alerts.empty else open_alerts)
action_alerts = (open_alerts[open_alerts["level"] != "INFO"]
                 if not open_alerts.empty else open_alerts)

if action_alerts.empty:
    st.success(t("alerts_all_clear"))
else:
    for _, r in action_alerts.iterrows():
        color, icon = LEVEL.get(r["level"], LEVEL["INFO"])
        hours = float(r["hours_open"] or 0)
        dur = (f"{hours:.0f} {t('alerts_hours')}" if hours < 48
               else f"{hours / 24:.0f} {t('alerts_days')}")
        msg = str(r["message"] or "").replace("<", "&lt;")
        code = str(r["code"] or "")

        st.markdown(
            f'<div style="background:{th["card"]};border:1px solid {th["border"]};'
            f'border-left:4px solid {color};border-radius:12px;'
            f'padding:16px 20px;margin-bottom:10px;">'
            f'<div style="color:{th["text"]};font-size:15px;line-height:1.5;">'
            f'{icon} {msg}</div>'
            f'<div style="color:{th["muted"]};font-size:12px;margin-top:8px;">'
            f'{t("alerts_ongoing")} {dur} · {t("alerts_seen")} '
            f'{int(r["occurrences"])} · <code>{code}</code></div></div>',
            unsafe_allow_html=True)

# --------------------------------------------------------------- INFO ----
if not info_alerts.empty:
    with st.expander(f"{t('alerts_info_block')} ({len(info_alerts)})"):
        st.caption(t("alerts_info_note"))
        for _, r in info_alerts.iterrows():
            st.markdown(f"🔵 {r['message']}")

# ------------------------------------------------------------ історія ----
st.markdown("")
with st.expander(t("alerts_resolved")):
    resolved = q("""
        SELECT code, level, message, first_seen, resolved_at, occurrences,
               EXTRACT(EPOCH FROM (resolved_at - first_seen))/3600 AS hours_lasted
        FROM merinnovation.alerts
        WHERE resolved_at IS NOT NULL
        ORDER BY resolved_at DESC LIMIT 30
    """)
    if resolved.empty:
        st.caption(t("alerts_no_resolved"))
    else:
        for _, r in resolved.iterrows():
            _, icon = LEVEL.get(r["level"], LEVEL["INFO"])
            h = float(r["hours_lasted"] or 0)
            dur = f"{h:.0f} {t('alerts_hours')}" if h < 48 else f"{h/24:.0f} {t('alerts_days')}"
            fixed = pd.to_datetime(r["resolved_at"]).strftime("%d.%m %H:%M")
            st.markdown(f"{icon} {r['message']}")
            st.caption(f"{t('alerts_lasted')} {dur} · "
                       f"{t('alerts_fixed_at')} {fixed}")
            st.markdown("---")

# ------------------------------------------------- найчастіші проблеми ----
with st.expander(t("alerts_frequent")):
    freq = q("""
        SELECT code, level, COUNT(*) AS times,
               SUM(occurrences) AS total_occurrences,
               MAX(last_seen) AS last_time
        FROM merinnovation.alerts
        GROUP BY code, level
        HAVING COUNT(*) > 1 OR SUM(occurrences) > 3
        ORDER BY total_occurrences DESC LIMIT 20
    """)
    if freq.empty:
        st.caption(t("alerts_no_frequent"))
    else:
        st.caption(t("alerts_frequent_note"))
        for _, r in freq.iterrows():
            _, icon = LEVEL.get(r["level"], LEVEL["INFO"])
            last = pd.to_datetime(r["last_time"]).strftime("%d.%m %H:%M")
            st.markdown(
                f"{icon} `{r['code']}` — {t('alerts_seen')} "
                f"{int(r['total_occurrences'])}, {t('alerts_last')} {last}")

st.caption(t("alerts_cache_note"))
