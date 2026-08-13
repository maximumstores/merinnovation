# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — Залишки FBA / Stock."""

import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth

from db import (ACCENT, AMAZON_DOMAINS, cell_link, cell_photo,
                download_csv_button, inject_css,
                lang_selector, metric_card, mp_label, plotly_layout, q,
                render_html_table, sort_controls, t)

st.set_page_config(layout="wide", page_title="Merinnovation · Stock",
                   page_icon="🐑")

auth.require_auth("1_Stock")
lang_selector()
inject_css()
auth.sidebar_user_block()

st.markdown(f"## {t('stock_title')}")

snap = q("SELECT MAX(snapshot_date) AS d FROM merinnovation.fba_inventory")
if snap.empty or snap["d"].isna().all():
    st.info(t("no_inventory"))
    st.stop()
snapshot_date = snap["d"].iloc[0]

inv = q("""
    SELECT f.marketplace_id, f.seller_sku, f.asin, f.product_name,
           f.fulfillable_quantity,
           COALESCE(f.inbound_working_quantity,0)
             + COALESCE(f.inbound_shipped_quantity,0)
             + COALESCE(f.inbound_receiving_quantity,0) AS inbound_total,
           f.reserved_total, f.unfulfillable_total, f.total_quantity,
           c.image_url
    FROM merinnovation.fba_inventory f
    LEFT JOIN merinnovation.catalog_images c
      ON c.marketplace_id = f.marketplace_id AND c.asin = f.asin
    WHERE f.snapshot_date = %s
""", (snapshot_date,))

df_all = inv.copy()
for col in ["fulfillable_quantity", "inbound_total", "reserved_total",
            "unfulfillable_total", "total_quantity"]:
    df_all[col] = df_all[col].fillna(0).astype(int)

c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card(t("sku_in_stock"),
                f"{(df_all['fulfillable_quantity'] > 0).sum():,}",
                sub=f"{t('total_rows')}: {len(df_all):,}")
with c2:
    metric_card("Fulfillable", f"{df_all['fulfillable_quantity'].sum():,}")
with c3:
    metric_card("Inbound", f"{df_all['inbound_total'].sum():,}",
                sub=t("inbound_sub"))
with c4:
    metric_card("Reserved", f"{df_all['reserved_total'].sum():,}")

st.markdown("")

top15 = (df_all.groupby("seller_sku")["fulfillable_quantity"].sum()
         .sort_values(ascending=False).head(15).sort_values())
if len(top15):
    fig = go.Figure(go.Bar(
        x=top15.values, y=top15.index, orientation="h",
        marker_color=ACCENT, text=top15.values, textposition="outside",
    ))
    fig.update_layout(**{**plotly_layout(title=t("top15_sku")), "height": 420})
    st.plotly_chart(fig, use_container_width=True)

st.markdown(f"**{t('stock_by_sku')}** · {t('snapshot')} {snapshot_date}")

fc1, fc2, _ = st.columns([2, 3, 5])
with fc1:
    mp_options = ["All"] + sorted(df_all["marketplace_id"].dropna().unique().tolist())
    mp_sel = st.selectbox(t("marketplace"), mp_options, format_func=mp_label)
with fc2:
    search = st.text_input(t("search"), "")

df = df_all.copy()
if mp_sel != "All":
    df = df[df["marketplace_id"] == mp_sel]
if search.strip():
    import re
    # дозволяємо вставити одразу декілька ASIN/SKU через кому, пробіл або з нового рядка
    tokens = [tok.lower() for tok in re.split(r"[,\s;]+", search.strip()) if tok]
    mask = pd.Series(False, index=df.index)
    for tok in tokens:
        mask |= (
            df["seller_sku"].str.lower().str.contains(tok, na=False)
            | df["product_name"].str.lower().str.contains(tok, na=False)
            | df["asin"].str.lower().str.contains(tok, na=False)
        )
    df = df[mask]

df["asin_link"] = ("https://" + df["marketplace_id"].map(AMAZON_DOMAINS).fillna("amazon.com")
                   + "/dp/" + df["asin"].fillna(""))
df["market_label"] = df["marketplace_id"].map(mp_label)

sort_col, sort_asc = sort_controls(
    {"SKU": "seller_sku", t("col_name"): "product_name",
     t("col_market"): "market_label", "Fulfillable": "fulfillable_quantity",
     "Inbound": "inbound_total", "Reserved": "reserved_total",
     "Total": "total_quantity"},
    key="stock", default_index=3, default_desc=True,
)
df = df.sort_values(sort_col, ascending=sort_asc)

rows = []
for rec in df.to_dict("records"):
    if rec["fulfillable_quantity"] == 0:
        rec["_row_class"] = "row-zero"
    elif rec["fulfillable_quantity"] < 20:
        rec["_row_class"] = "row-low"
    else:
        rec["_row_class"] = ""
    rows.append(rec)

columns = [
    ("", lambda r: cell_photo(r.get("image_url"))),
    ("SKU", lambda r: r.get("seller_sku") or ""),
    ("ASIN", lambda r: cell_link(r.get("asin_link"), r.get("asin") or "")),
    (t("col_name"), lambda r: (r.get("product_name") or "")[:70]),
    (t("col_market"), lambda r: r.get("market_label") or ""),
    ("Fulfillable", lambda r: str(r.get("fulfillable_quantity", 0))),
    ("Inbound", lambda r: str(r.get("inbound_total", 0))),
    ("Reserved", lambda r: str(r.get("reserved_total", 0))),
    ("Unfulf.", lambda r: str(r.get("unfulfillable_total", 0))),
    ("Total", lambda r: str(r.get("total_quantity", 0))),
]
render_html_table(rows, columns, height=600)
download_csv_button(
    df[["seller_sku", "asin", "product_name", "market_label",
       "fulfillable_quantity", "inbound_total", "reserved_total",
       "unfulfillable_total", "total_quantity"]],
    "stock", key="stock",
)

st.caption(t("legend_stock"))
