# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — реклама (SP / SB / SD)."""

import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import (ACCENT, ACCENT2, cur_theme, download_csv_button, inject_css,
                lang_selector, metric_card, plotly_layout, q,
                render_html_table, sort_controls, t, themed_axis)

st.set_page_config(layout="wide", page_title="Merinnovation · Ads", page_icon="🐑")
lang_selector()
inject_css()

th = cur_theme()
RED = "#ef4444"
AMBER = "#f59e0b"

st.markdown(f"## {t('ads_title')}")

# ------------------------------------------------- перевірка таблиць ----
tables = q("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema='merinnovation'
      AND table_name IN ('ads_sp_campaign','ads_sb_campaign','ads_sd_campaign')
""")
if tables.empty:
    st.info(t("no_ads_data"))
    st.stop()
existing = set(tables["table_name"])

# ------------------------------------------------------------ фільтри ----
fc1, fc2, _ = st.columns([2, 2, 6])
with fc1:
    period = st.selectbox(t("period"), [7, 14, 30], index=0,
                          format_func=lambda d: f"{d} {t('days')}", key="ads_period")
with fc2:
    types_avail = [x for x in ["SP", "SB", "SD"]
                   if f"ads_{x.lower()}_campaign" in existing]
    type_sel = st.selectbox(t("ads_type"), [t("flt_all")] + types_avail,
                            key="ads_type")

# ------------------------------------------------------------- дані ----
# Кожен тип реклами має свій набір колонок — зводимо до спільного вигляду
UNION_PARTS = []
if "ads_sp_campaign" in existing:
    UNION_PARTS.append(f"""
        SELECT 'SP' AS ad_type, region, profile_id, "date"::date AS day,
               "campaignName" AS campaign, "campaignStatus" AS status,
               COALESCE(impressions,0)::bigint AS impressions,
               COALESCE(clicks,0)::bigint AS clicks,
               COALESCE(cost,0)::numeric AS cost,
               COALESCE("sales7d",0)::numeric AS sales,
               COALESCE("purchases7d",0)::bigint AS orders
        FROM merinnovation.ads_sp_campaign
        WHERE "date" >= CURRENT_DATE - {period}
    """)
if "ads_sb_campaign" in existing:
    UNION_PARTS.append(f"""
        SELECT 'SB', region, profile_id, "date"::date,
               "campaignName", "campaignStatus",
               COALESCE(impressions,0)::bigint, COALESCE(clicks,0)::bigint,
               COALESCE(cost,0)::numeric, COALESCE(sales,0)::numeric,
               COALESCE(purchases,0)::bigint
        FROM merinnovation.ads_sb_campaign
        WHERE "date" >= CURRENT_DATE - {period}
    """)
if "ads_sd_campaign" in existing:
    UNION_PARTS.append(f"""
        SELECT 'SD', region, profile_id, "date"::date,
               "campaignName", "campaignStatus",
               COALESCE(impressions,0)::bigint, COALESCE(clicks,0)::bigint,
               COALESCE(cost,0)::numeric, COALESCE(sales,0)::numeric,
               COALESCE(purchases,0)::bigint
        FROM merinnovation.ads_sd_campaign
        WHERE "date" >= CURRENT_DATE - {period}
    """)

ads = q(" UNION ALL ".join(UNION_PARTS))

if ads.empty:
    st.info(t("no_ads_rows"))
    st.stop()

for col in ["impressions", "clicks", "orders"]:
    ads[col] = pd.to_numeric(ads[col], errors="coerce").fillna(0).astype(int)
for col in ["cost", "sales"]:
    ads[col] = pd.to_numeric(ads[col], errors="coerce").fillna(0.0)

if type_sel != t("flt_all"):
    ads = ads[ads["ad_type"] == type_sel]

# ------------------------------------------------------------ картки ----
spend = float(ads["cost"].sum())
sales = float(ads["sales"].sum())
clicks = int(ads["clicks"].sum())
impressions = int(ads["impressions"].sum())
orders = int(ads["orders"].sum())

acos = (spend / sales * 100) if sales else None
roas = (sales / spend) if spend else None
cpc = (spend / clicks) if clicks else None
ctr = (clicks / impressions * 100) if impressions else None

c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card(f"{t('ads_spend')} · {period} {t('days')}", f"${spend:,.0f}",
                sub=f"CPC ${cpc:.2f}" if cpc else None)
with c2:
    metric_card(t("ads_sales"), f"${sales:,.0f}",
                sub=f"{orders:,} {t('ads_orders')}")
with c3:
    metric_card("ACOS", f"{acos:.1f}%" if acos is not None else "—",
                sub=f"ROAS {roas:.2f}" if roas else None)
with c4:
    metric_card("CTR", f"{ctr:.2f}%" if ctr is not None else "—",
                sub=f"{clicks:,} {t('ads_clicks')}")

st.markdown("")

# ===================== ГОЛОВНЕ: реклама на товари, яких немає ====
# Це те, заради чого рекламні дані взагалі потрібні поруч із залишками.
oos_check = q("""
    SELECT COUNT(*) AS n FROM information_schema.tables
    WHERE table_schema='merinnovation' AND table_name='forecast_sku'
""")
has_forecast = not oos_check.empty and int(oos_check["n"].iloc[0]) > 0

if has_forecast:
    # кампанії часто містять SKU або ASIN у назві — шукаємо збіг
    oos = q("""
        SELECT seller_sku, asin, velocity_weighted
        FROM merinnovation.forecast_sku
        WHERE fulfillable = 0 AND inbound = 0
    """)

    if not oos.empty:
        camp = (ads.groupby("campaign", as_index=False)
                .agg(cost=("cost", "sum"), sales=("sales", "sum"),
                     clicks=("clicks", "sum")))
        camp = camp[camp["cost"] > 0]

        tokens = {}
        for _, r in oos.iterrows():
            for key in (r["seller_sku"], r["asin"]):
                if key and len(str(key)) >= 6:
                    tokens[str(key).lower()] = r["seller_sku"]

        wasted_rows = []
        for _, r in camp.iterrows():
            name = str(r["campaign"] or "").lower()
            hit = next((sku for tok, sku in tokens.items() if tok in name), None)
            if hit:
                wasted_rows.append({
                    "campaign": r["campaign"], "sku": hit,
                    "cost": float(r["cost"]), "sales": float(r["sales"]),
                    "clicks": int(r["clicks"]),
                })

        wasted_total = sum(w["cost"] for w in wasted_rows)

        if wasted_rows:
            st.markdown(
                f'<div style="background:{th["card"]};border:1px solid {RED}55;'
                f'border-left:4px solid {RED};border-radius:14px;'
                f'padding:20px 24px;margin-bottom:16px;">'
                f'<div style="color:{th["muted"]};font-size:11px;'
                f'letter-spacing:.12em;text-transform:uppercase;'
                f'font-weight:700;margin-bottom:8px;">'
                f'⚠️ {t("ads_waste_title")}</div>'
                f'<div style="color:{RED};font-size:32px;font-weight:800;'
                f'line-height:1.1;font-variant-numeric:tabular-nums;">'
                f'${wasted_total:,.0f}</div>'
                f'<div style="color:{th["muted"]};font-size:13px;'
                f'margin-top:6px;">{t("ads_waste_note").format(n=len(wasted_rows))}'
                f'</div></div>', unsafe_allow_html=True)

            wdf = pd.DataFrame(wasted_rows).sort_values("cost", ascending=False)
            cols_w = [
                (t("ads_campaign"), lambda r: str(r.get("campaign") or "")[:52]),
                ("SKU", lambda r: r.get("sku") or ""),
                (t("ads_spend"), lambda r: f"${r.get('cost', 0):,.2f}"),
                (t("ads_sales"), lambda r: f"${r.get('sales', 0):,.2f}"),
                (t("ads_clicks"), lambda r: str(int(r.get("clicks", 0)))),
            ]
            render_html_table(wdf.to_dict("records"), cols_w, height=260)
            st.caption(t("ads_waste_hint"))
            st.markdown("")

# ------------------------------------------------- графік по днях ----
daily = (ads.groupby("day", as_index=False)
         .agg(cost=("cost", "sum"), sales=("sales", "sum")))
daily = daily.sort_values("day")
daily["label"] = pd.to_datetime(daily["day"]).dt.strftime("%d.%m")
daily["acos"] = daily.apply(
    lambda r: (r["cost"] / r["sales"] * 100) if r["sales"] else None, axis=1)

fig = go.Figure()
fig.add_bar(x=daily["label"], y=daily["cost"], name=t("ads_spend"),
            marker_color=ACCENT2)
fig.add_bar(x=daily["label"], y=daily["sales"], name=t("ads_sales"),
            marker_color=ACCENT)
fig.add_scatter(x=daily["label"], y=daily["acos"], name="ACOS",
                yaxis="y2", mode="lines+markers",
                line=dict(color=AMBER, width=2))
lk = plotly_layout(title=t("ads_chart_title"))
lk["barmode"] = "group"
lk["xaxis"] = themed_axis(type="category", showgrid=False)
lk["yaxis2"] = themed_axis(overlaying="y", side="right", showgrid=False,
                           ticksuffix="%")
fig.update_layout(**lk)
st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------- таблиця кампаній ----
st.markdown(f"**{t('ads_by_campaign')}**")

byc = (ads.groupby(["campaign", "ad_type", "status"], as_index=False)
       .agg(impressions=("impressions", "sum"), clicks=("clicks", "sum"),
            cost=("cost", "sum"), sales=("sales", "sum"),
            orders=("orders", "sum")))
byc["acos"] = byc.apply(
    lambda r: (r["cost"] / r["sales"] * 100) if r["sales"] else None, axis=1)
byc["roas"] = byc.apply(
    lambda r: (r["sales"] / r["cost"]) if r["cost"] else None, axis=1)
byc["cpc"] = byc.apply(
    lambda r: (r["cost"] / r["clicks"]) if r["clicks"] else None, axis=1)

search = st.text_input(t("search_campaign"), "", key="ads_search")
if search.strip():
    import re
    toks = [x.lower() for x in re.split(r"[,\s;]+", search.strip()) if x]
    mask = pd.Series(False, index=byc.index)
    for tok in toks:
        mask |= byc["campaign"].str.lower().str.contains(tok, na=False)
    byc = byc[mask]

st.caption(t("sort_hint"))
sort_col, sort_asc = sort_controls(
    {t("ads_spend"): "cost", t("ads_sales"): "sales", "ACOS": "acos",
     "ROAS": "roas", t("ads_clicks"): "clicks"},
    key="ads", default_index=0, default_desc=True)
byc = byc.sort_values(sort_col, ascending=sort_asc, na_position="last")

# підсвічуємо кампанії, що витрачають без продажів
rows = []
for rec in byc.to_dict("records"):
    if rec.get("cost", 0) > 0 and not rec.get("sales"):
        rec["_row_class"] = "row-zero"
    elif rec.get("acos") is not None and rec["acos"] > 60:
        rec["_row_class"] = "row-low"
    else:
        rec["_row_class"] = ""
    rows.append(rec)


def fmt_acos(r):
    v = r.get("acos")
    return f"{v:.1f}%" if v is not None and pd.notna(v) else "—"


def fmt_roas(r):
    v = r.get("roas")
    return f"{v:.2f}" if v is not None and pd.notna(v) else "—"


cols = [
    (t("ads_campaign"), lambda r: str(r.get("campaign") or "")[:46]),
    (t("ads_type"), lambda r: r.get("ad_type") or ""),
    (t("col_status"), lambda r: str(r.get("status") or "")[:10]),
    (t("ads_spend"), lambda r: f"${r.get('cost', 0):,.2f}"),
    (t("ads_sales"), lambda r: f"${r.get('sales', 0):,.2f}"),
    ("ACOS", fmt_acos),
    ("ROAS", fmt_roas),
    (t("ads_clicks"), lambda r: str(int(r.get("clicks", 0)))),
]
render_html_table(rows, cols, height=520)
download_csv_button(
    byc[["campaign", "ad_type", "status", "impressions", "clicks",
         "cost", "sales", "orders", "acos", "roas"]],
    "ads_campaigns", key="ads")

st.caption(t("ads_legend"))
