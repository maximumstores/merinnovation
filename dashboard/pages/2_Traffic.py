# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — Sales & Traffic (сесії, конверсія, Buy Box %)."""

import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth

from db import (ACCENT, ACCENT2, AMAZON_DOMAINS, cell_link, cell_photo,
                download_csv_button, inject_css, lang_selector, metric_card,
                mp_label, plotly_layout, q, render_html_table, sort_controls,
                t, themed_axis)

st.set_page_config(layout="wide", page_title="Merinnovation · Traffic", page_icon="🐑")

auth.require_auth("2_Traffic")
lang_selector()
inject_css()
auth.sidebar_user_block()

st.markdown(f"## {t('traffic_title')}")

# ------------------------------------------------------------ фільтри ----
mps = q("SELECT DISTINCT marketplace_id FROM merinnovation.sales_traffic_daily ORDER BY 1")
if mps.empty:
    st.info(t("no_traffic_data"))
    st.stop()

mp_options = ["All"] + mps["marketplace_id"].dropna().tolist()

fc1, fc2, _ = st.columns([2, 2, 6])
with fc1:
    mp_sel = st.selectbox(t("marketplace"), mp_options, format_func=mp_label, key="tr_mp")
with fc2:
    period = st.selectbox(t("period"), [7, 14, 30], index=1,
                          format_func=lambda d: f"{d} {t('days')}", key="tr_period")

mp_where = "" if mp_sel == "All" else "AND marketplace_id = %s"
mp_params: tuple = () if mp_sel == "All" else (mp_sel,)

date_condition = f"report_date >= (CURRENT_DATE - INTERVAL '{period} days')"

# ------------------------------------------------------------- дані ----
daily = q(f"""
    SELECT report_date, marketplace_id, ordered_product_sales,
           ordered_product_sales_currency, units_ordered, sessions, page_views,
           buy_box_percentage, unit_session_percentage
    FROM merinnovation.sales_traffic_daily
    WHERE {date_condition}
      {mp_where}
    ORDER BY report_date
""", mp_params)

if daily.empty:
    st.info(t("no_traffic_data"))
    st.stop()

daily["report_date"] = pd.to_datetime(daily["report_date"])

total_sessions = int(daily["sessions"].sum())
total_page_views = int(daily["page_views"].sum())
total_units = int(daily["units_ordered"].sum())
avg_buy_box = daily["buy_box_percentage"].mean()
conversion = (total_units / total_sessions * 100) if total_sessions else 0

rev_by_cur = (daily.groupby("ordered_product_sales_currency")["ordered_product_sales"]
             .sum().sort_values(ascending=False))
rev_by_cur = rev_by_cur[rev_by_cur.index.notna()]
main_cur, main_rev, other = ("", 0.0, "")
if len(rev_by_cur):
    main_cur = rev_by_cur.index[0]
    main_rev = rev_by_cur.iloc[0]
    other = " · ".join(f"{v:,.0f} {c}" for c, v in rev_by_cur.iloc[1:].items())

# ------------------------------------------------------------ картки ----
c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card(f"{t('revenue')} · {period} {t('days')}", f"{main_rev:,.0f} {main_cur}",
                sub=other if other else None)
with c2:
    metric_card(t("sessions_total"), f"{total_sessions:,}",
                sub=f"{total_page_views:,} {t('pageviews_label')}")
with c3:
    metric_card(t("conversion_label"), f"{conversion:.1f}%",
                sub=f"{total_units:,} {t('units_label')}")
with c4:
    metric_card(t("buybox_label"),
                f"{avg_buy_box:.1f}%" if pd.notna(avg_buy_box) else "—")

st.markdown("")

# ------------------------------------------------------ графік: дні ----
by_date = (daily.groupby("report_date")
          .agg(sessions=("sessions", "sum"),
               units=("units_ordered", "sum")).reset_index())
by_date["conversion"] = by_date.apply(
    lambda r: (r["units"] / r["sessions"] * 100) if r["sessions"] else 0, axis=1)

fig = go.Figure()
fig.add_bar(x=by_date["report_date"].dt.strftime("%Y-%m-%d"), y=by_date["sessions"],
           name=t("sessions_total"), marker_color=ACCENT, opacity=0.85)
fig.add_scatter(x=by_date["report_date"].dt.strftime("%Y-%m-%d"), y=by_date["conversion"],
               name=t("conversion_label"), yaxis="y2", mode="lines+markers",
               line=dict(color=ACCENT2, width=2))

layout_kwargs = plotly_layout(title=t("traffic_chart_title"))
layout_kwargs["xaxis"] = themed_axis(type="category", showgrid=False)
layout_kwargs["yaxis2"] = themed_axis(overlaying="y", side="right",
                                      showgrid=False, ticksuffix="%")
fig.update_layout(**layout_kwargs)
st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------- таблиця SKU ----
st.markdown(f"**{t('traffic_by_sku')}**")

by_sku = q(f"""
    SELECT s.marketplace_id, s.seller_sku, s.asin,
           s.ordered_product_sales, s.ordered_product_sales_currency,
           s.units_ordered, s.sessions, s.page_views,
           s.buy_box_percentage, s.unit_session_percentage,
           c.image_url
    FROM merinnovation.sales_traffic_by_sku s
    LEFT JOIN merinnovation.catalog_images c
      ON c.asin = s.asin AND c.marketplace_id = s.marketplace_id
    WHERE s.report_date = (
        SELECT MAX(report_date) FROM merinnovation.sales_traffic_by_sku
        WHERE 1=1 {mp_where}
    )
    {mp_where}
""", (*mp_params, *mp_params))

if by_sku.empty:
    st.info(t("no_traffic_data"))
else:
    search = st.text_input(t("search"), "", key="tr_search")
    if search.strip():
        import re
        tokens = [tok.lower() for tok in re.split(r"[,\s;]+", search.strip()) if tok]
        mask = pd.Series(False, index=by_sku.index)
        for tok in tokens:
            mask |= (
                by_sku["seller_sku"].str.lower().str.contains(tok, na=False)
                | by_sku["asin"].str.lower().str.contains(tok, na=False)
            )
        by_sku = by_sku[mask]

    by_sku["asin_link"] = (
        "https://" + by_sku["marketplace_id"].map(AMAZON_DOMAINS).fillna("amazon.com")
        + "/dp/" + by_sku["asin"].fillna("")
    )
    by_sku["market_label"] = by_sku["marketplace_id"].map(mp_label)
    by_sku["sales_label"] = by_sku.apply(
        lambda r: f"{r['ordered_product_sales']:,.2f} {r['ordered_product_sales_currency'] or ''}"
        if pd.notna(r["ordered_product_sales"]) else "—", axis=1)
    by_sku["conv_label"] = by_sku.apply(
        lambda r: f"{(r['units_ordered'] / r['sessions'] * 100):.1f}%"
        if r["sessions"] else "—", axis=1)
    by_sku["bb_label"] = by_sku["buy_box_percentage"].apply(
        lambda v: f"{v:.0f}%" if pd.notna(v) else "—")

    st.caption(t("sort_hint"))
    sort_col, sort_asc = sort_controls(
        {t("revenue"): "ordered_product_sales", t("sessions_total"): "sessions",
         t("conversion_label"): "conv_label", "SKU": "seller_sku"},
        key="traffic", default_index=0, default_desc=True,
    )
    by_sku = by_sku.sort_values(sort_col, ascending=sort_asc)

    rows = by_sku.to_dict("records")
    columns = [
        ("", lambda r: cell_photo(r.get("image_url"))),
        ("SKU", lambda r: r.get("seller_sku") or ""),
        ("ASIN", lambda r: cell_link(r.get("asin_link"), r.get("asin") or "")),
        (t("col_market"), lambda r: r.get("market_label") or ""),
        (t("revenue"), lambda r: r.get("sales_label") or ""),
        (t("units_label"), lambda r: str(int(r.get("units_ordered", 0)))),
        (t("sessions_total"), lambda r: str(int(r.get("sessions", 0)))),
        (t("conversion_label"), lambda r: r.get("conv_label") or ""),
        (t("buybox_label"), lambda r: r.get("bb_label") or ""),
    ]
    render_html_table(rows, columns, height=560)
    download_csv_button(
        by_sku[["seller_sku", "asin", "market_label", "sales_label",
               "units_ordered", "sessions", "conv_label", "bb_label"]],
        "traffic_by_sku", key="traffic",
    )

st.caption(t("traffic_cache_note"))
