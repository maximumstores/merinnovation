# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — Прогноз запасів / автозамовлення."""

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

st.set_page_config(layout="wide", page_title="Merinnovation · Forecast",
                   page_icon="🐑")

auth.require_auth("4_Forecast")
lang_selector()
inject_css()
auth.sidebar_user_block()

st.markdown(f"## {t('forecast_title')}")

# ------------------------------------------------------------- дані ----
fc = q("""
    SELECT f.marketplace_id, f.seller_sku, f.asin, f.product_name,
           f.units_7d, f.units_30d,
           f.velocity_weighted, f.trend_pct,
           f.fulfillable, f.inbound, f.total_available,
           f.days_of_cover, f.lead_time_days, f.reorder_point,
           f.recommended_qty, f.stockout_date, f.status,
           f.calculated_at,
           c.image_url
    FROM merinnovation.forecast_sku f
    LEFT JOIN merinnovation.catalog_images c
      ON c.asin = f.asin AND c.marketplace_id = f.marketplace_id
""")

if fc.empty:
    st.info(t("no_forecast_data"))
    st.stop()

calculated_at = pd.to_datetime(fc["calculated_at"]).max()

for col in ["fulfillable", "inbound", "total_available", "units_7d", "units_30d",
            "recommended_qty"]:
    fc[col] = pd.to_numeric(fc[col], errors="coerce").fillna(0).astype(int)
for col in ["velocity_weighted", "days_of_cover", "trend_pct", "reorder_point"]:
    fc[col] = pd.to_numeric(fc[col], errors="coerce")

# ------------------------------------------------------------ фільтри ----
fc1, fc2, _ = st.columns([2, 3, 5])
with fc1:
    mp_options = ["All"] + sorted(fc["marketplace_id"].dropna().unique().tolist())
    mp_sel = st.selectbox(t("marketplace"), mp_options, format_func=mp_label,
                          key="fc_mp")
with fc2:
    status_options = ["All", "REORDER_NOW", "REORDER_SOON", "OUT_OF_STOCK",
                      "LIMITED_HISTORY", "INCOMING_NO_SALES", "OVERSTOCK",
                      "OK", "NO_SALES", "NO_SALES_NO_STOCK"]
    status_sel = st.selectbox(t("status_filter"), status_options, key="fc_status")

df = fc.copy()
if mp_sel != "All":
    df = df[df["marketplace_id"] == mp_sel]

# ------------------------------------------------------------ картки ----
n_now = int((df["status"] == "REORDER_NOW").sum())
n_soon = int((df["status"] == "REORDER_SOON").sum())
n_oos = int((df["status"] == "OUT_OF_STOCK").sum())
n_over = int((df["status"] == "OVERSTOCK").sum())
units_to_order = int(df.loc[df["status"].isin(
    ["REORDER_NOW", "REORDER_SOON", "OUT_OF_STOCK"]), "recommended_qty"].sum())

c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card(t("reorder_now_label"), f"{n_now}",
                sub=f"{t('reorder_soon_label')}: {n_soon}")
with c2:
    metric_card(t("out_of_stock_label"), f"{n_oos}")
with c3:
    metric_card(t("units_to_order_label"), f"{units_to_order:,}")
with c4:
    metric_card(t("overstock_label"), f"{n_over}")

st.caption(f"{t('calculated_at')}: {calculated_at:%Y-%m-%d %H:%M}")
st.markdown("")

# --------------------------------------------- графік: ризик по днях ----
risk = df[(df["days_of_cover"].notna()) & (df["velocity_weighted"] > 0)].copy()
if not risk.empty:
    bins = [0, 15, 30, 45, 60, 90, 10_000]
    labels = ["<15", "15-30", "30-45", "45-60", "60-90", "90+"]
    risk["bucket"] = pd.cut(risk["days_of_cover"], bins=bins, labels=labels,
                            right=False)
    counts = risk["bucket"].value_counts().reindex(labels).fillna(0)

    colors = ["#ef4444", "#f59e0b", "#f59e0b", ACCENT, ACCENT, ACCENT2]
    fig = go.Figure(go.Bar(
        x=list(labels), y=counts.values, marker_color=colors,
        text=counts.values.astype(int), textposition="outside",
    ))
    layout_kwargs = plotly_layout(title=t("cover_distribution"))
    layout_kwargs["xaxis"] = themed_axis(type="category", showgrid=False,
                                         title=t("days_of_cover_axis"))
    fig.update_layout(**layout_kwargs)
    st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------ таблиця ----
st.markdown(f"**{t('forecast_by_sku')}**")

if status_sel != "All":
    df = df[df["status"] == status_sel]

search = st.text_input(t("search"), "", key="fc_search")
if search.strip():
    import re
    tokens = [tok.lower() for tok in re.split(r"[,\s;]+", search.strip()) if tok]
    mask = pd.Series(False, index=df.index)
    for tok in tokens:
        mask |= (
            df["seller_sku"].str.lower().str.contains(tok, na=False)
            | df["asin"].str.lower().str.contains(tok, na=False)
            | df["product_name"].str.lower().str.contains(tok, na=False)
        )
    df = df[mask]

df["asin_link"] = (
    "https://" + df["marketplace_id"].map(AMAZON_DOMAINS).fillna("amazon.com")
    + "/dp/" + df["asin"].fillna("")
)
df["market_label"] = df["marketplace_id"].map(mp_label)

st.caption(t("sort_hint"))
sort_col, sort_asc = sort_controls(
    {t("col_recommended"): "recommended_qty",
     t("col_days_cover"): "days_of_cover",
     t("col_velocity"): "velocity_weighted",
     "SKU": "seller_sku",
     t("col_stock"): "fulfillable"},
    key="forecast", default_index=0, default_desc=True,
)
df = df.sort_values(sort_col, ascending=sort_asc, na_position="last")

STATUS_ROW_CLASS = {
    "OUT_OF_STOCK": "row-zero",
    "REORDER_NOW": "row-zero",
    "REORDER_SOON": "row-low",
    "LIMITED_HISTORY": "row-low",
}

rows = []
for rec in df.to_dict("records"):
    rec["_row_class"] = STATUS_ROW_CLASS.get(rec.get("status"), "")
    rows.append(rec)


def fmt_days(r):
    v = r.get("days_of_cover")
    return f"{v:.0f}" if pd.notna(v) else "—"


def fmt_trend(r):
    v = r.get("trend_pct")
    if pd.isna(v):
        return "—"
    arrow = "▲" if v >= 0 else "▼"
    return f"{arrow} {abs(v):.0f}%"


def fmt_stockout(r):
    v = r.get("stockout_date")
    return str(v) if v else "—"


columns = [
    ("", lambda r: cell_photo(r.get("image_url"))),
    ("SKU", lambda r: r.get("seller_sku") or ""),
    ("ASIN", lambda r: cell_link(r.get("asin_link"), r.get("asin") or "")),
    (t("col_market"), lambda r: r.get("market_label") or ""),
    (t("col_velocity"), lambda r: f"{r.get('velocity_weighted', 0):.2f}"),
    (t("col_trend"), fmt_trend),
    (t("col_stock"), lambda r: str(int(r.get("fulfillable", 0)))),
    (t("col_inbound"), lambda r: str(int(r.get("inbound", 0)))),
    (t("col_days_cover"), fmt_days),
    (t("col_stockout"), fmt_stockout),
    (t("col_recommended"), lambda r: str(int(r.get("recommended_qty", 0)))),
    (t("col_status"), lambda r: r.get("status") or ""),
]
render_html_table(rows, columns, height=560)
download_csv_button(
    df[["marketplace_id", "seller_sku", "asin", "product_name",
        "velocity_weighted", "trend_pct", "fulfillable", "inbound",
        "days_of_cover", "recommended_qty", "stockout_date", "status"]],
    "forecast", key="forecast",
)

st.caption(t("forecast_legend"))
