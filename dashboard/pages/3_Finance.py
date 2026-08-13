# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — Фінанси (реальні гроші: комісії, збори, повернення)."""

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

st.set_page_config(layout="wide", page_title="Merinnovation · Finance", page_icon="🐑")

auth.require_auth("3_Finance")
lang_selector()
inject_css()
auth.sidebar_user_block()

st.markdown(f"## {t('finance_title')}")

# ------------------------------------------------------------ фільтри ----
period = None
fc1, _ = st.columns([2, 8])
with fc1:
    period = st.selectbox(t("period"), [7, 14, 30], index=1,
                          format_func=lambda d: f"{d} {t('days')}", key="fin_period")

# ------------------------------------------------------------- дані ----
ship = q(f"""
    SELECT amazon_order_id, marketplace_name, posted_date, seller_sku,
           quantity_shipped, principal, shipping_charge, promotion_discount,
           fba_fulfillment_fee, commission, other_fees, currency
    FROM merinnovation.finance_shipment_items
    WHERE posted_date >= (NOW() - INTERVAL '{period} days')
""")

refunds = q(f"""
    SELECT amazon_order_id, posted_date, seller_sku, quantity,
           refund_principal, refund_commission, refund_other, currency
    FROM merinnovation.finance_refunds
    WHERE posted_date >= (NOW() - INTERVAL '{period} days')
""")

if ship.empty and refunds.empty:
    st.info(t("no_finance_data"))
    st.stop()

for col in ["principal", "shipping_charge", "promotion_discount",
            "fba_fulfillment_fee", "commission", "other_fees"]:
    if col in ship.columns:
        ship[col] = pd.to_numeric(ship[col], errors="coerce").fillna(0)
for col in ["refund_principal", "refund_commission", "refund_other"]:
    if col in refunds.columns:
        refunds[col] = pd.to_numeric(refunds[col], errors="coerce").fillna(0)

# головна валюта = та, де найбільший оборот
cur_totals = ship.groupby("currency")["principal"].sum().sort_values(ascending=False)
cur_totals = cur_totals[cur_totals.index.notna()]
main_cur = cur_totals.index[0] if len(cur_totals) else ""

ship_m = ship[ship["currency"] == main_cur]
refunds_m = refunds[refunds["currency"] == main_cur] if not refunds.empty else refunds

gross = ship_m["principal"].sum() + ship_m["shipping_charge"].sum()
promo = ship_m["promotion_discount"].sum()          # зазвичай від'ємні
fees_total = (ship_m["fba_fulfillment_fee"].sum()
             + ship_m["commission"].sum()
             + ship_m["other_fees"].sum())          # зазвичай від'ємні
refund_total = (refunds_m["refund_principal"].sum()
               if not refunds_m.empty else 0)       # зазвичай від'ємні
net = gross + promo + fees_total + refund_total

# ------------------------------------------------------------ картки ----
c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card(f"{t('gross_label')} · {period} {t('days')}",
                f"{gross:,.0f} {main_cur}",
                sub=f"{t('promo_label')}: {promo:,.0f}")
with c2:
    metric_card(t("fees_label"), f"{fees_total:,.0f} {main_cur}",
                sub=f"FBA: {ship_m['fba_fulfillment_fee'].sum():,.0f} · "
                    f"{t('commission_label')}: {ship_m['commission'].sum():,.0f}")
with c3:
    metric_card(t("refunds_label"), f"{refund_total:,.0f} {main_cur}",
                sub=f"{len(refunds_m):,} {t('refund_items_label')}"
                if not refunds_m.empty else None)
with c4:
    metric_card(t("net_label"), f"{net:,.0f} {main_cur}")

st.markdown("")

# ------------------------------------------------------ графік: дні ----
ship_m = ship_m.copy()
ship_m["day"] = pd.to_datetime(ship_m["posted_date"]).dt.date
daily = (ship_m.groupby("day")
        .agg(gross=("principal", "sum"),
             fees=("commission", "sum")).reset_index())
daily["fees_abs"] = daily["fees"].abs()

fig = go.Figure()
fig.add_bar(x=daily["day"].astype(str), y=daily["gross"],
           name=t("gross_label"), marker_color=ACCENT, opacity=0.85)
fig.add_scatter(x=daily["day"].astype(str), y=daily["fees_abs"],
               name=t("commission_label"), mode="lines+markers",
               line=dict(color=ACCENT2, width=2))
layout_kwargs = plotly_layout(title=t("finance_chart_title"))
layout_kwargs["xaxis"] = themed_axis(type="category", showgrid=False)
fig.update_layout(**layout_kwargs)
st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------- таблиця SKU ----
st.markdown(f"**{t('finance_by_sku')}**")

by_sku = (ship_m.groupby("seller_sku")
         .agg(qty=("quantity_shipped", "sum"),
              principal=("principal", "sum"),
              promo=("promotion_discount", "sum"),
              fba_fee=("fba_fulfillment_fee", "sum"),
              commission=("commission", "sum"),
              other=("other_fees", "sum")).reset_index())
by_sku["net"] = (by_sku["principal"] + by_sku["promo"] + by_sku["fba_fee"]
                + by_sku["commission"] + by_sku["other"])

# ASIN + фото: SKU→ASIN мапимо через order_items (там завжди є пара),
# фото — з catalog_images по ASIN
skus = tuple(by_sku["seller_sku"].dropna().unique())
if skus:
    sku_map = q("""
        SELECT DISTINCT ON (oi.seller_sku)
               oi.seller_sku, oi.asin, o.marketplace_id, c.image_url
        FROM merinnovation.order_items oi
        JOIN merinnovation.orders o USING (amazon_order_id)
        LEFT JOIN merinnovation.catalog_images c
          ON c.asin = oi.asin AND c.marketplace_id = o.marketplace_id
        WHERE oi.seller_sku IN %s
        ORDER BY oi.seller_sku, c.image_url NULLS LAST
    """, (skus,))
    by_sku = by_sku.merge(sku_map, on="seller_sku", how="left")
else:
    by_sku["asin"] = None
    by_sku["marketplace_id"] = None
    by_sku["image_url"] = None

by_sku["asin_link"] = (
    "https://" + by_sku["marketplace_id"].map(AMAZON_DOMAINS).fillna("amazon.com")
    + "/dp/" + by_sku["asin"].fillna("")
)

search = st.text_input(t("search"), "", key="fin_search")
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

st.caption(t("sort_hint"))
sort_col, sort_asc = sort_controls(
    {t("net_label"): "net", t("gross_label"): "principal",
     t("fees_label"): "commission", "SKU": "seller_sku", "Qty": "qty"},
    key="finance", default_index=0, default_desc=True,
)
by_sku = by_sku.sort_values(sort_col, ascending=sort_asc)

rows = by_sku.to_dict("records")
columns = [
    ("", lambda r: cell_photo(r.get("image_url"))),
    ("SKU", lambda r: r.get("seller_sku") or ""),
    ("ASIN", lambda r: cell_link(r.get("asin_link"), r.get("asin") or "")),
    ("Qty", lambda r: str(int(r.get("qty", 0)))),
    (t("gross_label"), lambda r: f"{r.get('principal', 0):,.2f}"),
    (t("promo_label"), lambda r: f"{r.get('promo', 0):,.2f}"),
    ("FBA fee", lambda r: f"{r.get('fba_fee', 0):,.2f}"),
    (t("commission_label"), lambda r: f"{r.get('commission', 0):,.2f}"),
    (t("net_label"), lambda r: f"{r.get('net', 0):,.2f}"),
]
render_html_table(rows, columns, height=520)
download_csv_button(
    by_sku[["seller_sku", "asin", "qty", "principal", "promo",
           "fba_fee", "commission", "net"]],
    "finance_by_sku", key="finance",
)

st.caption(f"{t('finance_cache_note')} · {main_cur}")
