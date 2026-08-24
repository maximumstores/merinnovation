# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — Огляд / Overview."""

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:
    PACIFIC = timezone(timedelta(hours=-7))  # fallback, без DST

import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth

from db import (ACCENT, ACCENT2, AMAZON_DOMAINS, cell_link, cell_photo,
                cur_theme, download_csv_button, inject_css, lang_selector,
                metric_card, mp_label, plotly_layout, q, render_html_table,
                sort_controls, t, themed_axis)

st.set_page_config(layout="wide", page_title="Merinnovation", page_icon="🐑")

auth.require_auth("0_Overview")
lang_selector()
inject_css()
auth.sidebar_user_block()

try:
    st.markdown(f"## {t('overview_title')}")

    mps = q("SELECT DISTINCT marketplace_id FROM merinnovation.orders ORDER BY 1")
    mp_options = ["All"] + mps["marketplace_id"].dropna().tolist()

    fc1, fc2, _ = st.columns([2, 2, 6])
    with fc1:
        mp_sel = st.selectbox(t("marketplace"), mp_options, format_func=mp_label, key="mp")
    with fc2:
        period = st.selectbox(t("period"), [7, 14, 30], index=1,
                              format_func=lambda d: f"{d} {t('days')}", key="period")

    is_today_mode = False  # "Сьогодні" прибрано з періоду — плутало більше, ніж давало користі

    now_utc = datetime.now(timezone.utc)
    date_from = (now_utc - timedelta(days=period)).strftime("%Y-%m-%d")
    prev_from = (now_utc - timedelta(days=period * 2)).strftime("%Y-%m-%d")

    mp_where = "" if mp_sel == "All" else "AND marketplace_id = %s"
    mp_params: tuple = () if mp_sel == "All" else (mp_sel,)

    orders_2p = q(f"""
        SELECT amazon_order_id, purchase_date, order_status, marketplace_id,
               order_total_amount, order_total_currency
        FROM merinnovation.orders
        WHERE purchase_date >= %s::date
          AND order_status <> 'Canceled'
          {mp_where}
    """, (prev_from, *mp_params))

    if orders_2p.empty:
        st.info(t("no_orders"))
        st.stop()

    orders_2p["purchase_date"] = pd.to_datetime(orders_2p["purchase_date"], utc=True)
    orders_2p["day"] = orders_2p["purchase_date"].dt.date
    orders_2p["order_total_amount"] = pd.to_numeric(
        orders_2p["order_total_amount"], errors="coerce").fillna(0)

    cutoff = (now_utc - timedelta(days=period)).date()
    orders = orders_2p[orders_2p["day"] >= cutoff].copy()
    orders_prev = orders_2p[orders_2p["day"] < cutoff]

    if orders.empty:
        st.info(t("no_orders"))
        st.stop()

    n_orders = len(orders)
    n_prev = len(orders_prev)

    earliest_date = orders_2p["day"].min()
    enough_history = earliest_date <= (now_utc - timedelta(days=period * 2 - 1)).date()

    rev_by_cur = (orders.groupby("order_total_currency")["order_total_amount"]
                  .sum().sort_values(ascending=False))
    rev_by_cur = rev_by_cur[rev_by_cur.index.notna()]
    if len(rev_by_cur):
        main_cur = rev_by_cur.index[0]
        main_rev = rev_by_cur.iloc[0]
        other = " · ".join(f"{v:,.0f} {c}" for c, v in rev_by_cur.iloc[1:].items())
    else:
        main_cur, main_rev, other = "", 0.0, ""

    prev_rev = orders_prev.loc[
        orders_prev["order_total_currency"] == main_cur, "order_total_amount"].sum()

    main_cur_orders = orders[orders["order_total_currency"] == main_cur]
    avg_check = (main_cur_orders["order_total_amount"].mean()
                 if len(main_cur_orders) else 0)

    # ------------------------------------------------------ точна виручка ----
    # Orders API не завжди дає суму для Pending-замовлень (Amazon просто не
    # віддає OrderTotal, поки замовлення не підтверджене). Sales & Traffic
    # Report дає точну "Ordered Product Sales" — таку саму цифру, як у
    # Amazon Seller Central Sales Dashboard. Якщо дані вже завантажені —
    # використовуємо їх замість оцінки по Orders API.
    st_mp_where = "" if mp_sel == "All" else "AND marketplace_id = %s"
    st_mp_params = () if mp_sel == "All" else (mp_sel,)

    st_daily = q(f"""
        SELECT report_date, ordered_product_sales, ordered_product_sales_currency,
               units_ordered, sessions, page_views
        FROM merinnovation.sales_traffic_daily
        WHERE report_date >= %s AND report_date <= %s
          {st_mp_where}
    """, (date_from, now_utc.strftime("%Y-%m-%d"), *st_mp_params))

    use_accurate_revenue = not st_daily.empty
    sessions_total = 0
    conversion_pct = None

    if use_accurate_revenue:
        st_rev_by_cur = (st_daily.groupby("ordered_product_sales_currency")
                        ["ordered_product_sales"].sum().sort_values(ascending=False))
        st_rev_by_cur = st_rev_by_cur[st_rev_by_cur.index.notna()]
        if len(st_rev_by_cur):
            main_cur = st_rev_by_cur.index[0]
            main_rev = st_rev_by_cur.iloc[0]
            other = " · ".join(f"{v:,.0f} {c}" for c, v in st_rev_by_cur.iloc[1:].items())
        sessions_total = int(st_daily["sessions"].sum())
        units_from_traffic = int(st_daily["units_ordered"].sum())
        if sessions_total > 0:
            conversion_pct = units_from_traffic / sessions_total * 100

    orders_today = int(
        (orders["purchase_date"].dt.tz_convert(PACIFIC).dt.date
         == datetime.now(PACIFIC).date()).sum()
    )
    pending_count = int((orders["order_status"] == "Pending").sum())


    def pct_delta(cur, prev):
        if is_today_mode or not enough_history or not prev or prev < 5:
            return None, True
        change = (cur - prev) / prev * 100
        if abs(change) > 500:
            return None, True
        return f"{abs(change):.0f}%", change >= 0


    d_orders, up_orders = pct_delta(n_orders, n_prev)
    d_rev, up_rev = pct_delta(main_rev, prev_rev)

    period_label = t("today_option") if is_today_mode else f"{period} {t('days')}"

    # "очікує підтвердження" показуємо тільки якщо НЕМАЄ точних даних
    # з Sales & Traffic Report — якщо вони є, довіряємо їм навіть за Pending
    all_pending_period = (pending_count == n_orders and n_orders > 0
                          and not use_accurate_revenue)

    # Коли точних даних Amazon ще немає (звіт з'явиться завтра), рахуємо
    # наближену оцінку по цінах ПОЗИЦІЙ замовлення (item_price) — Amazon
    # зазвичай віддає її навіть для Pending-замовлень, на відміну від
    # сумарного OrderTotal на рівні замовлення, який часто відсутній.
    estimated_rev = None
    estimated_cur = None
    if all_pending_period:
        order_ids_today = tuple(orders["amazon_order_id"].tolist())
        if order_ids_today:
            est = q("""
                SELECT item_price_currency, SUM(item_price_amount * quantity_ordered) AS est_sum
                FROM merinnovation.order_items
                WHERE amazon_order_id IN %s
                GROUP BY item_price_currency
                ORDER BY est_sum DESC
            """, (order_ids_today,))
            est = est[est["item_price_currency"].notna()]
            if not est.empty:
                estimated_cur = est.iloc[0]["item_price_currency"]
                estimated_rev = est.iloc[0]["est_sum"]

    rev_display = (t("pending_note") if all_pending_period
                  else f"{main_rev:,.0f} {main_cur}")

    rev_sub = None
    if all_pending_period:
        if estimated_rev is not None:
            rev_sub = f"{t('estimate_label')}: ~{estimated_rev:,.0f} {estimated_cur}"
        elif is_today_mode:
            rev_sub = t("today_pending_hint")
    elif use_accurate_revenue and conversion_pct is not None:
        rev_sub = f"{t('conversion_label')}: {conversion_pct:.1f}% · {sessions_total:,} {t('sessions_label')}"
        if other:
            rev_sub = f"{other} · {rev_sub}"
    elif other:
        rev_sub = other

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card(f"{t('orders_n')} · {period_label}", f"{n_orders:,}",
                    delta=d_orders, delta_up=up_orders)
    with c2:
        metric_card(f"{t('revenue')} · {period_label}",
                    rev_display,
                    delta=None if all_pending_period else d_rev,
                    delta_up=up_rev,
                    sub=rev_sub)
    with c3:
        metric_card(t("avg_check"), f"{avg_check:,.2f} {main_cur}"
                    if not all_pending_period else "—")
    with c4:
        metric_card(t("orders_today"), f"{orders_today}",
                    sub=f"Pending: {pending_count} · PDT")

    st.markdown("")

    daily = (orders.groupby("day")
             .agg(orders=("amazon_order_id", "count")).reset_index())
    daily_rev = (main_cur_orders.groupby("day")["order_total_amount"]
                 .sum().reset_index(name="revenue"))
    daily = daily.merge(daily_rev, on="day", how="left").fillna(0)

    chart_font_color = cur_theme()["chart_font"]

    fig = go.Figure()
    fig.add_bar(x=daily["day"], y=daily["orders"], name=t("orders_series"),
                marker_color=ACCENT, opacity=0.85)
    fig.add_scatter(x=daily["day"], y=daily["revenue"],
                    name=f"{t('revenue_series')}, {main_cur}",
                    yaxis="y2", mode="lines+markers",
                    line=dict(color=ACCENT2, width=2))
    daily["day_label"] = daily["day"].astype(str)
    fig.data[0].x = daily["day_label"]
    fig.data[1].x = daily["day_label"]

    layout_kwargs = plotly_layout(title=t("chart_daily"))
    layout_kwargs["xaxis"] = themed_axis(type="category", showgrid=False)
    layout_kwargs["yaxis2"] = themed_axis(overlaying="y", side="right",
                                          showgrid=False)
    fig.update_layout(**layout_kwargs)
    st.plotly_chart(fig, use_container_width=True)

    top_sku = q(f"""
        SELECT oi.seller_sku, oi.asin, SUM(oi.quantity_ordered) AS qty
        FROM merinnovation.order_items oi
        JOIN merinnovation.orders o USING (amazon_order_id)
        WHERE o.purchase_date >= %s::date
          AND o.order_status <> 'Canceled'
          {mp_where.replace('marketplace_id', 'o.marketplace_id')}
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10
    """, (date_from, *mp_params))

    if not top_sku.empty:
        top_sku_sorted = top_sku.sort_values("qty")
        f2 = go.Figure(go.Bar(
            x=top_sku_sorted["qty"], y=top_sku_sorted["seller_sku"], orientation="h",
            marker_color=ACCENT, text=top_sku_sorted["qty"], textposition="outside",
        ))
        f2.update_layout(**plotly_layout(title=t("top10_sku")))
        st.plotly_chart(f2, use_container_width=True)

        asins = tuple(top_sku["asin"].dropna().unique())
        if asins:
            photos = q("""
                SELECT DISTINCT ON (asin) asin, marketplace_id, image_url
                FROM merinnovation.catalog_images
                WHERE asin IN %s
            """, (asins,))
        else:
            photos = pd.DataFrame(columns=["asin", "marketplace_id", "image_url"])

        top_tbl = top_sku.merge(photos, on="asin", how="left")
        top_tbl["asin_link"] = (
            "https://" + top_tbl["marketplace_id"].map(AMAZON_DOMAINS).fillna("amazon.com")
            + "/dp/" + top_tbl["asin"].fillna("")
        )

        st.caption(t("sort_hint"))
        sort_col, sort_asc = sort_controls(
            {"SKU": "seller_sku", "ASIN": "asin", t("col_qty"): "qty"},
            key="topsku", default_index=2, default_desc=True,
        )
        top_tbl = top_tbl.sort_values(sort_col, ascending=sort_asc)

        rows = top_tbl.to_dict("records")
        columns = [
            ("", lambda r: cell_photo(r.get("image_url"))),
            ("SKU", lambda r: r.get("seller_sku") or ""),
            ("ASIN", lambda r: cell_link(r.get("asin_link"), r.get("asin") or "")),
            (t("col_qty"), lambda r: str(int(r.get("qty", 0)))),
        ]
        render_html_table(rows, columns, height=280)
        download_csv_button(
            top_tbl[["seller_sku", "asin", "qty"]], "top_sku", key="topsku",
        )

    st.markdown("")
    st.markdown(f"**{t('last20')}**")

    last20 = orders.sort_values("purchase_date", ascending=False).head(20).copy()

    order_ids = tuple(last20["amazon_order_id"].tolist())
    if order_ids:
        items_info = q("""
            SELECT DISTINCT ON (oi.amazon_order_id)
                   oi.amazon_order_id, oi.asin, c.image_url
            FROM merinnovation.order_items oi
            LEFT JOIN merinnovation.orders o USING (amazon_order_id)
            LEFT JOIN merinnovation.catalog_images c
              ON c.asin = oi.asin AND c.marketplace_id = o.marketplace_id
            WHERE oi.amazon_order_id IN %s
            ORDER BY oi.amazon_order_id, oi.order_item_id
        """, (order_ids,))
        last20 = last20.merge(items_info, on="amazon_order_id", how="left")
    else:
        last20["asin"] = None
        last20["image_url"] = None

    last20["asin_link"] = (
        "https://" + last20["marketplace_id"].map(AMAZON_DOMAINS).fillna("amazon.com")
        + "/dp/" + last20["asin"].fillna("")
    )
    last20["market_label"] = last20["marketplace_id"].map(mp_label)
    last20["date_label"] = last20["purchase_date"].dt.strftime("%d.%m %H:%M")
    last20["sum_label"] = last20.apply(
        lambda r: "—" if pd.isna(r["order_total_amount"]) or r["order_total_amount"] == 0
        else f"{r['order_total_amount']:,.2f} {r['order_total_currency'] or ''}",
        axis=1,
    )

    order_search = st.text_input(t("search_orders"), "", key="order_search")
    if order_search.strip():
        import re
        tokens = [tok.lower() for tok in re.split(r"[,\s;]+", order_search.strip()) if tok]
        mask = pd.Series(False, index=last20.index)
        for tok in tokens:
            mask |= (
                last20["amazon_order_id"].str.lower().str.contains(tok, na=False)
                | last20["asin"].str.lower().str.contains(tok, na=False)
            )
        last20 = last20[mask]

    st.caption(t("sort_hint"))
    sort_col20, sort_asc20 = sort_controls(
        {t("col_date"): "purchase_date", t("col_status"): "order_status",
         t("col_market"): "market_label", t("col_sum"): "order_total_amount"},
        key="last20", default_index=0, default_desc=True,
    )
    last20 = last20.sort_values(sort_col20, ascending=sort_asc20)

    rows20 = last20.to_dict("records")
    columns20 = [
        ("", lambda r: cell_photo(r.get("image_url"))),
        (t("col_order"), lambda r: r.get("amazon_order_id") or ""),
        ("ASIN", lambda r: cell_link(r.get("asin_link"), r.get("asin") or "")),
        (t("col_date"), lambda r: r.get("date_label") or ""),
        (t("col_status"), lambda r: r.get("order_status") or ""),
        (t("col_market"), lambda r: r.get("market_label") or ""),
        (t("col_sum"), lambda r: r.get("sum_label") or ""),
    ]
    render_html_table(rows20, columns20, height=380)
    download_csv_button(
        last20[["amazon_order_id", "asin", "date_label", "order_status",
               "market_label", "sum_label"]],
        "last20_orders", key="last20",
    )

    st.caption(t("cache_note"))


except Exception as _page_error:
    # st.stop() всередині try кидає StopException, що успадковується від
    # Exception. Без цієї перевірки нормальний вихід зі сторінки
    # ("немає замовлень") виглядав би як збій.
    if type(_page_error).__name__ in ("StopException", "RerunException"):
        raise
    # Порожня сторінка без пояснення — найгірше, що може побачити
    # користувач: незрозуміло, чи це збій, чи він щось зробив не так.
    st.error("Сторінку не вдалось відобразити")
    st.exception(_page_error)
