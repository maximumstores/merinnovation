# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — монітор запитів на відгуки (Request a Review)."""

import os
import sys
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth

from db import (ACCENT, ACCENT2, AMAZON_DOMAINS, cell_link, cell_photo,
                cur_theme, download_csv_button, inject_css, lang_selector,
                metric_card, mp_label, plotly_layout, q, render_html_table,
                sort_controls, t, themed_axis)

st.set_page_config(layout="wide", page_title="Merinnovation · Reviews",
                   page_icon="🐑")

auth.require_auth("5_Reviews")
lang_selector()
inject_css()
auth.sidebar_user_block()

# Вікно відправки: лоадер бере замовлення 8-33 днів від дати замовлення
AGE_MIN, AGE_MAX = 8, 33

st.markdown(f"## {t('reviews_title')}")

# ------------------------------------------------- перевірка таблиці ----
exists = q("""
    SELECT COUNT(*) AS n
    FROM information_schema.tables
    WHERE table_schema = 'merinnovation' AND table_name = 'review_requests'
""")
if exists.empty or int(exists["n"].iloc[0]) == 0:
    st.info(t("no_reviews_data"))
    st.stop()


# ------------------------------------------------------- хелпери ----
def agg_period(df, date_col, gran, sum_cols):
    """Агрегує по періоду: день / тиждень / місяць."""
    d = df.copy()
    d[date_col] = pd.to_datetime(d[date_col])
    if gran == "week":
        d["period"] = d[date_col].dt.to_period("W")
        d["label"] = d["period"].dt.start_time.dt.strftime("%d.%m.%y")
    elif gran == "month":
        d["period"] = d[date_col].dt.to_period("M")
        d["label"] = d["period"].dt.strftime("%Y-%m")
    else:
        d["period"] = d[date_col].dt.normalize()
        d["label"] = d[date_col].dt.strftime("%d.%m")
    return (d.groupby(["period", "label"], as_index=False)[list(sum_cols)]
            .sum().sort_values("period"))


# ------------------------------------------------------- фільтри ----
fc1, fc2, fc3, _ = st.columns([2, 2, 2, 4])
with fc1:
    period_map = {t("per_1"): 1, t("per_7"): 7, t("per_14"): 14,
                  t("per_30"): 30, t("per_60"): 60, t("per_90"): 90}
    period_label = st.selectbox(t("flt_period"), list(period_map),
                                index=3, key="rv_period")
    period_days = period_map[period_label]
with fc2:
    gran_map = {t("gran_day"): "day", t("gran_week"): "week",
                t("gran_month"): "month"}
    gran_label = st.selectbox(t("flt_gran"), list(gran_map), index=0,
                              key="rv_gran")
    gran = gran_map[gran_label]
with fc3:
    threshold = st.selectbox(t("flt_threshold"), [90, 85, 80, 75, 70],
                             index=2, key="rv_threshold")

# ------------------------------------------------------------ health ----
kpi = q("""
    SELECT
      COUNT(*) FILTER (WHERE status='sent' AND sent_at::date = CURRENT_DATE) AS today,
      COUNT(*) FILTER (WHERE status='sent' AND sent_at >= NOW() - INTERVAL '7 days') AS sent7,
      COUNT(*) FILTER (WHERE status LIKE 'failed%%' AND sent_at >= NOW() - INTERVAL '7 days') AS failed7,
      MAX(sent_at) FILTER (WHERE status='sent') AS last_sent,
      COUNT(*) AS total_rows
    FROM merinnovation.review_requests
""")

if kpi.empty or int(kpi["total_rows"].iloc[0] or 0) == 0:
    st.info(t("no_reviews_data"))
    st.stop()

k = kpi.iloc[0]
last_sent = pd.to_datetime(k["last_sent"]) if pd.notna(k["last_sent"]) else None
hours_since = ((datetime.now(last_sent.tzinfo) - last_sent).total_seconds() / 3600
               if last_sent is not None else None)

if hours_since is not None and hours_since > 25:
    st.error(t("health_warn").format(h=hours_since))
else:
    st.success(t("health_ok"))

# --------------------------------------------------------------- пул ----
pool = q(f"""
    SELECT
      COUNT(*) FILTER (WHERE o.purchase_date >= NOW() - INTERVAL '15 days') AS fresh,
      COUNT(*) FILTER (WHERE o.purchase_date <  NOW() - INTERVAL '15 days'
                         AND o.purchase_date >= NOW() - INTERVAL '25 days') AS mid,
      COUNT(*) FILTER (WHERE o.purchase_date <  NOW() - INTERVAL '25 days') AS burning,
      COUNT(*) AS pool_total
    FROM merinnovation.orders o
    WHERE o.order_status = 'Shipped'
      AND o.purchase_date BETWEEN NOW() - INTERVAL '{AGE_MAX} days'
                              AND NOW() - INTERVAL '{AGE_MIN} days'
      AND NOT EXISTS (
          SELECT 1 FROM merinnovation.review_requests r
          WHERE r.order_id = o.amazon_order_id
            AND r.status IN ('sent','already')
      )
""")
p = pool.iloc[0] if not pool.empty else {}

c1, c2, c3, c4 = st.columns(4)
with c1:
    metric_card(t("sent_today"), f"{int(k['today'] or 0):,}",
                sub=f"{t('sent_7d')}: {int(k['sent7'] or 0):,}")
with c2:
    metric_card(t("pool_label"), f"{int(p.get('pool_total', 0) or 0):,}",
                sub=t("pool_sub"))
with c3:
    metric_card(t("burning_label"), f"{int(p.get('burning', 0) or 0):,}")
with c4:
    metric_card(t("failed_7d"), f"{int(k['failed7'] or 0):,}",
                sub=(last_sent.strftime("%d.%m %H:%M") if last_sent is not None
                     else "—"))

st.markdown("")

# ------------------------------------------------ дані покриття ----
cov = q(f"""
    WITH ord AS (
        SELECT purchase_date::date AS day,
               COUNT(DISTINCT amazon_order_id) AS orders
        FROM merinnovation.orders
        WHERE order_status = 'Shipped'
          AND purchase_date >= NOW() - INTERVAL '{period_days} days'
        GROUP BY 1
    ), req AS (
        SELECT o.purchase_date::date AS day,
               COUNT(DISTINCT r.order_id) FILTER (WHERE r.status='sent') AS sent,
               COUNT(DISTINCT r.order_id) FILTER (WHERE r.status='already') AS already,
               COUNT(DISTINCT r.order_id) FILTER (WHERE r.status LIKE 'failed%%') AS errors
        FROM merinnovation.review_requests r
        JOIN merinnovation.orders o ON o.amazon_order_id = r.order_id
        WHERE o.purchase_date >= NOW() - INTERVAL '{period_days} days'
        GROUP BY 1
    )
    SELECT ord.day, ord.orders,
           COALESCE(req.sent,0) AS sent,
           COALESCE(req.already,0) AS already,
           COALESCE(req.errors,0) AS errors
    FROM ord LEFT JOIN req USING (day)
    ORDER BY ord.day DESC
""")

# --------------------------- Orders vs Requests (комбо з покриттям) ----
if not cov.empty:
    cov["covered"] = cov["sent"] + cov["already"]
    cov["unprocessed"] = (cov["orders"] - cov["covered"]).clip(lower=0)
    cov["coverage"] = (cov["covered"] / cov["orders"].replace(0, pd.NA) * 100).round(1)

    st.markdown(f"**{t('combo_title')}**")
    cc = agg_period(cov, "day", gran, ["orders", "covered"])
    cc["coverage"] = (cc["covered"] / cc["orders"].where(cc["orders"] > 0)
                      * 100).fillna(0).round(1)

    th = cur_theme()
    figc = make_subplots(specs=[[{"secondary_y": True}]])
    figc.add_trace(go.Bar(name=t("cov_orders"), x=cc["label"], y=cc["orders"],
                          marker_color=ACCENT2), secondary_y=False)
    figc.add_trace(go.Bar(name=t("combo_processed"), x=cc["label"], y=cc["covered"],
                          marker_color=ACCENT), secondary_y=False)
    figc.add_trace(go.Scatter(name=t("cov_pct"), x=cc["label"], y=cc["coverage"],
                              mode="lines+markers",
                              line=dict(color="#cc5de8", width=2)),
                   secondary_y=True)
    figc.add_hline(y=threshold, line_dash="dot", line_color="#f59e0b",
                   secondary_y=True, opacity=0.7)

    lk = plotly_layout()
    lk["barmode"] = "group"
    lk["height"] = 380
    lk["xaxis"] = themed_axis(type="category", showgrid=False)
    figc.update_layout(**lk)
    figc.update_yaxes(gridcolor=th["grid"], color=th["chart_font"],
                      tickfont=dict(color=th["chart_font"]), secondary_y=False)
    figc.update_yaxes(range=[0, 105], ticksuffix="%", showgrid=False,
                      color=th["chart_font"],
                      tickfont=dict(color=th["chart_font"]), secondary_y=True)
    st.plotly_chart(figc, use_container_width=True)

# ------------------------------------------------- обсяг по днях ----
daily = q(f"""
    SELECT sent_at::date AS day,
           COUNT(*) FILTER (WHERE status='sent') AS sent,
           COUNT(*) FILTER (WHERE status='already') AS already,
           COUNT(*) FILTER (WHERE status='outside') AS outside,
           COUNT(*) FILTER (WHERE status LIKE 'failed%%') AS failed
    FROM merinnovation.review_requests
    WHERE sent_at >= NOW() - INTERVAL '{period_days} days'
    GROUP BY 1 ORDER BY 1
""")

if not daily.empty:
    dd = agg_period(daily, "day", gran, ["sent", "already", "outside", "failed"])
    fig = go.Figure()
    fig.add_bar(x=dd["label"], y=dd["sent"], name=t("st_sent"), marker_color=ACCENT)
    fig.add_bar(x=dd["label"], y=dd["already"], name=t("st_already"),
                marker_color=ACCENT2)
    fig.add_bar(x=dd["label"], y=dd["outside"], name=t("st_outside"),
                marker_color="#f59e0b")
    fig.add_bar(x=dd["label"], y=dd["failed"], name=t("st_failed"),
                marker_color="#ef4444")
    lk = plotly_layout(title=t("daily_volume"))
    lk["barmode"] = "stack"
    lk["xaxis"] = themed_axis(type="category", showgrid=False)
    fig.update_layout(**lk)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(t("status_hint"))

# ------------------------------------------------ пул за терміновістю ----
gl, gr = st.columns(2)

with gl:
    buckets = pd.DataFrame({
        "b": [t("pool_fresh"), t("pool_mid"), t("pool_burning")],
        "n": [int(p.get("fresh", 0) or 0), int(p.get("mid", 0) or 0),
              int(p.get("burning", 0) or 0)],
    })
    figp = go.Figure(go.Bar(
        x=buckets["n"], y=buckets["b"], orientation="h",
        marker_color=[ACCENT, "#f59e0b", "#ef4444"],
        text=buckets["n"], textposition="outside"))
    lk = plotly_layout(title=t("pool_title"))
    lk["height"] = 280
    lk["yaxis"] = themed_axis(autorange="reversed")
    figp.update_layout(**lk)
    st.plotly_chart(figp, use_container_width=True)

with gr:
    funnel = q(f"""
        SELECT
          (SELECT COUNT(*) FROM merinnovation.orders
            WHERE order_status='Shipped'
              AND purchase_date >= NOW() - INTERVAL '{period_days} days') AS orders_p,
          (SELECT COUNT(*) FROM merinnovation.review_requests
            WHERE status='sent'
              AND sent_at >= NOW() - INTERVAL '{period_days} days') AS sent_p
    """)
    f = funnel.iloc[0] if not funnel.empty else {}
    figf = go.Figure(go.Funnel(
        y=[t("f_orders"), t("f_pool"), t("f_sent")],
        x=[int(f.get("orders_p", 0) or 0), int(p.get("pool_total", 0) or 0),
           int(f.get("sent_p", 0) or 0)],
        textinfo="value+percent initial",
        marker=dict(color=[ACCENT2, "#f59e0b", ACCENT])))
    lk = plotly_layout(title=t("funnel_title"))
    lk["height"] = 280
    figf.update_layout(**lk)
    st.plotly_chart(figf, use_container_width=True)

# ------------------------------------------- покриття по датах ----
if not cov.empty:
    st.markdown(f"**{t('coverage_title')}**")
    st.caption(t("coverage_note"))

    today = pd.Timestamp(datetime.now().date())
    cov["age"] = (today - pd.to_datetime(cov["day"])).dt.days

    def status_of(r):
        if r["age"] < AGE_MIN:
            return "maturing"
        if pd.isna(r["coverage"]):
            return "none"
        if r["coverage"] >= threshold:
            return "ok"
        return "progress" if r["age"] <= AGE_MAX else "missed"

    cov["st"] = cov.apply(status_of, axis=1)

    ST_LABEL = {
        "ok": "🟢 " + t("st_ok"), "progress": "🟠 " + t("st_progress"),
        "missed": "🔴 " + t("st_missed"), "maturing": "⏳ " + t("st_maturing"),
        "none": "⚪ —",
    }
    ST_CLASS = {"missed": "row-zero", "progress": "row-low"}

    matured = cov[cov["st"] != "maturing"]
    t_orders = int(matured["orders"].sum())
    t_cov = round(matured["covered"].sum() / t_orders * 100, 1) if t_orders else 0
    t_missed = int(cov.loc[cov["st"] == "missed", "unprocessed"].sum())

    m1, m2, m3 = st.columns(3)
    with m1:
        metric_card(t("cov_orders"), f"{t_orders:,}", sub=t("matured_only"))
    with m2:
        metric_card(t("cov_pct"), f"{t_cov:.1f}%")
    with m3:
        metric_card(t("missed_total"), f"{t_missed:,}", sub=t("missed_sub"))

    # фільтр за статусом
    st_options = [t("flt_all"), "🟢 " + t("st_ok"), "🟠 " + t("st_progress"),
                  "🔴 " + t("st_missed"), "⏳ " + t("st_maturing")]
    st_sel = st.selectbox(t("flt_status"), st_options, key="rv_status")

    view = cov.copy()
    if st_sel != t("flt_all"):
        key_by_label = {ST_LABEL[k]: k for k in ST_LABEL}
        want = key_by_label.get(st_sel)
        if want:
            view = view[view["st"] == want]

    rows = []
    for rec in view.to_dict("records"):
        rec["_row_class"] = ST_CLASS.get(rec["st"], "")
        rec["day_label"] = pd.to_datetime(rec["day"]).strftime("%d.%m.%Y")
        rec["st_label"] = ST_LABEL.get(rec["st"], "")
        rec["cov_label"] = ("—" if pd.isna(rec["coverage"])
                            else f"{rec['coverage']:.0f}%")
        rows.append(rec)

    columns = [
        (t("col_date"), lambda r: r.get("day_label") or ""),
        (t("cov_orders"), lambda r: str(int(r.get("orders", 0)))),
        (t("st_sent"), lambda r: str(int(r.get("sent", 0)))),
        (t("st_already"), lambda r: str(int(r.get("already", 0)))),
        (t("cov_pct"), lambda r: r.get("cov_label") or ""),
        (t("cov_unprocessed"), lambda r: str(int(r.get("unprocessed", 0)))),
        (t("col_status"), lambda r: r.get("st_label") or ""),
    ]
    render_html_table(rows, columns, height=420)
    download_csv_button(
        view[["day", "orders", "sent", "already", "errors", "coverage",
              "unprocessed", "st"]],
        "review_coverage", key="reviews_cov")

    with st.expander(t("legend_title")):
        st.markdown(t("legend_body").format(th=threshold))

    # ------------------------------------------- heatmap покриття ----
    heat = cov[cov["st"] != "maturing"].copy()
    if len(heat) >= 7:
        st.markdown(f"**{t('heatmap_title')}**")
        st.caption(t("heatmap_note"))

        heat["dt"] = pd.to_datetime(heat["day"])
        heat["dow"] = heat["dt"].dt.dayofweek
        heat["week"] = heat["dt"].dt.to_period("W").dt.start_time.dt.strftime("%d.%m")
        heat["cov_val"] = heat["coverage"].fillna(0)

        piv = heat.pivot_table(index="dow", columns="week",
                               values="cov_val", aggfunc="mean").reindex(range(7))
        dow_names = t("dow_names").split(",")

        figh = go.Figure(go.Heatmap(
            z=piv.values, x=list(piv.columns),
            y=[dow_names[i] for i in piv.index],
            colorscale=[[0, "#ef4444"], [0.8, "#f59e0b"], [1, ACCENT]],
            zmin=0, zmax=100, colorbar=dict(title="%", ticksuffix="%"),
            hovertemplate="%{y} · %{x}<br>%{z:.0f}%<extra></extra>"))
        lk = plotly_layout()
        lk["height"] = 300
        figh.update_layout(**lk)
        st.plotly_chart(figh, use_container_width=True)


# ------------------------------------------ ефективність за віком ----
age_stats = q("""
    SELECT order_age_days,
           COUNT(*) FILTER (WHERE status='sent') AS sent,
           COUNT(*) FILTER (WHERE status='already') AS already,
           COUNT(*) FILTER (WHERE status='outside') AS outside,
           COUNT(*) AS total
    FROM merinnovation.review_requests
    WHERE order_age_days IS NOT NULL
      AND order_age_days BETWEEN 0 AND 60
    GROUP BY 1 ORDER BY 1
""")

if not age_stats.empty and int(age_stats["total"].sum()) >= 20:
    st.markdown("")
    st.markdown(f"**{t('age_title')}**")
    st.caption(t("age_note"))

    age_stats["accepted_pct"] = (age_stats["sent"] / age_stats["total"]
                                 * 100).round(1)

    figa = go.Figure()
    figa.add_bar(x=age_stats["order_age_days"], y=age_stats["sent"],
                 name=t("st_sent"), marker_color=ACCENT)
    figa.add_bar(x=age_stats["order_age_days"], y=age_stats["outside"],
                 name=t("st_outside"), marker_color="#f59e0b")
    figa.add_bar(x=age_stats["order_age_days"], y=age_stats["already"],
                 name=t("st_already"), marker_color=ACCENT2)
    lk = plotly_layout(title=t("age_chart_title"))
    lk["barmode"] = "stack"
    lk["height"] = 300
    lk["xaxis"] = themed_axis(title=t("age_axis"), showgrid=False)
    figa.update_layout(**lk)
    st.plotly_chart(figa, use_container_width=True)

    total_pts = int(age_stats["total"].sum())
    if total_pts < 200:
        st.caption(t("age_low_sample").format(n=total_pts))

# ---------------------------------------------------------- по ASIN ----
st.markdown("")
st.markdown(f"**{t('by_asin_title')}**")

by_asin = q(f"""
    SELECT oi.asin,
           COUNT(DISTINCT r.order_id) FILTER (WHERE r.status='sent') AS sent,
           COUNT(DISTINCT r.order_id) FILTER (WHERE r.status='already') AS already,
           COUNT(DISTINCT r.order_id) FILTER (WHERE r.status='outside') AS outside,
           MAX(o.marketplace_id) AS marketplace_id,
           MAX(c.image_url) AS image_url
    FROM merinnovation.review_requests r
    JOIN merinnovation.orders o ON o.amazon_order_id = r.order_id
    JOIN merinnovation.order_items oi USING (amazon_order_id)
    LEFT JOIN merinnovation.catalog_images c
      ON c.asin = oi.asin AND c.marketplace_id = o.marketplace_id
    WHERE r.sent_at >= NOW() - INTERVAL '{period_days} days'
      AND oi.asin IS NOT NULL
    GROUP BY oi.asin
    ORDER BY sent DESC
""")

if by_asin.empty:
    st.info(t("no_asin_data"))
else:
    by_asin["asin_link"] = (
        "https://" + by_asin["marketplace_id"].map(AMAZON_DOMAINS).fillna("amazon.com")
        + "/dp/" + by_asin["asin"].fillna(""))

    # ---- зведення по блоку ----
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        metric_card(t("st_sent"), f"{int(by_asin['sent'].sum()):,}")
    with s2:
        metric_card(t("st_already"), f"{int(by_asin['already'].sum()):,}")
    with s3:
        metric_card(t("st_outside"), f"{int(by_asin['outside'].sum()):,}")
    with s4:
        metric_card(t("active_asins"), f"{int((by_asin['sent'] > 0).sum()):,}")

    st.markdown("")

    al, ar = st.columns([1, 1])

    # ---- зліва: топ-15 ASIN за надісланими ----
    with al:
        top = by_asin.sort_values("sent", ascending=False).head(15).sort_values("sent")
        figt = go.Figure(go.Bar(
            x=top["sent"], y=top["asin"], orientation="h",
            marker_color=ACCENT, text=top["sent"], textposition="outside"))
        lk = plotly_layout(title=t("asin_chart_title"))
        lk["height"] = max(320, 26 * len(top))
        lk["yaxis"] = themed_axis(type="category")
        figt.update_layout(**lk)
        st.plotly_chart(figt, use_container_width=True)

    # ---- справа: таблиця ----
    with ar:
        st.caption(t("sort_hint"))
        sort_col, sort_asc = sort_controls(
            {t("st_sent"): "sent", t("st_already"): "already", "ASIN": "asin"},
            key="reviews_asin", default_index=0, default_desc=True)
        by_asin = by_asin.sort_values(sort_col, ascending=sort_asc)

        columns_a = [
            ("", lambda r: cell_photo(r.get("image_url"))),
            ("ASIN", lambda r: cell_link(r.get("asin_link"), r.get("asin") or "")),
            (t("st_sent"), lambda r: str(int(r.get("sent", 0)))),
            (t("st_already"), lambda r: str(int(r.get("already", 0)))),
            (t("st_outside"), lambda r: str(int(r.get("outside", 0)))),
        ]
        render_html_table(by_asin.to_dict("records"), columns_a, height=460)
        download_csv_button(
            by_asin[["asin", "sent", "already", "outside"]],
            "review_by_asin", key="reviews_asin_csv")

st.caption(t("reviews_cache_note"))
