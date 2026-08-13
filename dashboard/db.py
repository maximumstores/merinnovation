# -*- coding: utf-8 -*-
"""Общий модуль дашборда: БД, i18n, темы, навигация, UI-хелперы, HTML-таблицы."""

import base64
import os

import pandas as pd
import psycopg2
import streamlit as st
from dotenv import load_dotenv

MARKETPLACE_NAMES = {
    "ATVPDKIKX0DER": "US", "A2EUQ1WTGCTBG2": "CA", "A1AM78C64UM0Y8": "MX",
    "A1F83G8C2ARO7P": "UK", "A1PA6795UKMFR9": "DE", "A13V1IB3VIYZZH": "FR",
    "APJ6JRA9NG5V4": "IT", "A1RKKUPIHCS9HS": "ES", "A1805IZSGTT6HS": "NL",
    "A2NODRKZP88ZB9": "SE", "A1C3SOZRARQ6R3": "PL",
}

AMAZON_DOMAINS = {
    "ATVPDKIKX0DER": "amazon.com", "A2EUQ1WTGCTBG2": "amazon.ca",
    "A1AM78C64UM0Y8": "amazon.com.mx", "A1F83G8C2ARO7P": "amazon.co.uk",
    "A1PA6795UKMFR9": "amazon.de", "A13V1IB3VIYZZH": "amazon.fr",
    "APJ6JRA9NG5V4": "amazon.it", "A1RKKUPIHCS9HS": "amazon.es",
    "A1805IZSGTT6HS": "amazon.nl", "A2NODRKZP88ZB9": "amazon.se",
    "A1C3SOZRARQ6R3": "amazon.pl",
}


def mp_label(mp_id: str) -> str:
    return MARKETPLACE_NAMES.get(mp_id, mp_id)


# ------------------------------------------------------------- themes ----

THEMES = {
    "dark": {
        "bg": "#0e1117", "sidebar": "#161a24", "card": "#1a1f2e",
        "border": "rgba(255,255,255,0.08)", "text": "#f0f2f6",
        "muted": "#8b93a7", "grid": "rgba(255,255,255,0.06)",
        "chart_font": "#c9d1e0", "logo_filter": "none",
        "row_hover": "rgba(16,185,129,0.08)",
    },
    "light": {
        "bg": "#f7f8fa", "sidebar": "#ffffff", "card": "#ffffff",
        "border": "rgba(0,0,0,0.10)", "text": "#1a1f2e",
        "muted": "#5b6472", "grid": "rgba(0,0,0,0.07)",
        "chart_font": "#1a1f2e", "logo_filter": "invert(1)",
        "row_hover": "rgba(16,185,129,0.08)",
    },
}

ACCENT = "#10b981"
ACCENT2 = "#3b82f6"


def cur_theme() -> dict:
    return THEMES[st.session_state.get("theme", "dark")]


def themed_axis(**extra) -> dict:
    """Осі з кольорами поточної теми + твої перевизначення.

    ВАЖЛИВО: якщо просто написати layout["xaxis"] = dict(type="category"),
    воно ЗАТИРАЄ кольори з plotly_layout() — і підписи стають невидимими
    на світлій темі. Цей хелпер зберігає кольори і додає потрібне зверху."""
    th = cur_theme()
    base = {
        "color": th["chart_font"],
        "tickfont": {"color": th["chart_font"]},
        "title": {"font": {"color": th["chart_font"]}},
    }
    # title може прийти рядком — тоді загортаємо, щоб не втратити колір
    if "title" in extra and isinstance(extra["title"], str):
        extra = dict(extra)
        extra["title"] = {"text": extra["title"],
                          "font": {"color": th["chart_font"]}}
    base.update(extra)
    return base


def plotly_layout(title: str | None = None) -> dict:
    """Базовий layout для plotly. Якщо передано title — колір title
    примусово прив'язується до теми (інакше на світлій темі текст
    заголовку лишається білим і зникає)."""
    th = cur_theme()
    layout = dict(
        template="plotly_dark" if st.session_state.get("theme", "dark") == "dark"
                 else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=th["chart_font"], size=12),
        margin=dict(l=10, r=10, t=44, b=36),
        height=340,
        xaxis=dict(showgrid=False, color=th["chart_font"],
                   tickfont=dict(color=th["chart_font"])),
        yaxis=dict(gridcolor=th["grid"], color=th["chart_font"],
                   tickfont=dict(color=th["chart_font"])),
        legend=dict(orientation="h", yanchor="top", y=-0.15, x=0,
                    font=dict(color=th["chart_font"])),
    )
    if title:
        layout["title"] = dict(
            text=title, x=0.01, xanchor="left",
            font=dict(color=th["chart_font"], size=15),
            pad=dict(b=14),
        )
    return layout


# ------------------------------------------------------------- i18n ----

TRANSLATIONS = {
    "uk": {
        "login_subtitle": "Аналітичний кабінет",
        "login_user": "Логін", "login_pass": "Пароль",
        "login_btn": "Увійти", "logout": "Вийти",
        "login_empty": "Введи логін і пароль",
        "login_bad": "Невірний логін або пароль",
        "login_throttled": "Забагато невдалих спроб. Спробуй за 15 хвилин.",
        "login_disabled": "Доступ вимкнено. Зверніться до адміністратора.",
        "role_admin": "Адміністратор", "role_user": "Користувач",
        "admin_only": "Ця сторінка доступна лише адміністратору",
        "pw_required": "Потрібно змінити пароль перед роботою",
        "pw_new": "Новий пароль", "pw_repeat": "Повторіть пароль",
        "pw_save": "Зберегти", "pw_short": "Пароль не коротший за 8 символів",
        "pw_mismatch": "Паролі не збігаються", "pw_changed": "Пароль змінено",
        "nav_overview": "Огляд", "nav_stock": "Залишки",
        "overview_title": "Merinnovation — Огляд",
        "stock_title": "Залишки FBA",
        "marketplace": "Маркетплейс", "period": "Період", "days": "днів",
        "today_option": "Сьогодні",
        "pending_note": "очікує підтвердження",
        "sort_hint": "Сортування застосовується до таблиці нижче",
        "search_orders": "Пошук за ASIN / номером замовлення (можна декілька через кому)",
        "conversion_label": "Конверсія", "sessions_label": "сесій",
        "today_pending_hint": "точні дані Amazon з'являться завтра",
        "estimate_label": "Оцінка за цінами позицій",
        "nav_traffic": "Трафік", "traffic_title": "Продажі та трафік",
        "traffic_chart_title": "Сесії та конверсія по днях",
        "traffic_by_sku": "Трафік за SKU", "no_traffic_data": "Немає даних — запусти 04_sales_traffic_loader.py",
        "sessions_total": "Сесії", "pageviews_label": "переглядів сторінок",
        "units_label": "одиниць", "buybox_label": "Buy Box %",
        "traffic_cache_note": "Дані з sales_traffic · Amazon Sales & Traffic Report",
        "download_csv": "⬇ Скачати CSV",
        "per_1": "1 день", "per_7": "7 днів", "per_14": "14 днів",
        "per_30": "30 днів", "per_60": "60 днів", "per_90": "90 днів",
        "flt_period": "Період", "flt_gran": "Деталізація",
        "flt_threshold": "Поріг покриття", "flt_status": "Статус", "flt_all": "Усі",
        "gran_day": "День", "gran_week": "Тиждень", "gran_month": "Місяць",
        "combo_title": "Замовлення та запити за датами замовлення",
        "combo_processed": "Оброблено (надіслано + вже було)",
        "legend_title": "Легенда статусів і як рахується покриття",
        "legend_body": """
**🟢 OK** (≥{th}%) — запити пішли, робити нічого не треба.

**🟠 В роботі** — нижче цілі, але вікно 5-30 днів ще відкрите. Запити дошлються автоматично, ці дати покриються. Це **не втрата**.

**🔴 Упущено** — вікно закрилось, а покриття лишилось низьким. Ці відгуки втрачені назавжди. Єдиний статус, який є реальною проблемою.

**⏳ Зріє** — замовлення молодше 8 днів, вікно ще не відкрилось. Норма, покриється саме.

---

`Покриття % = (надіслано + вже було) / замовлень × 100`

`Не оброблено = замовлень − (надіслано + вже було)`

Підсумок рахується **лише по дозрілих датах** — інакше нулі свіжих днів занижували б загальний відсоток.
""",
        "sev_critical": "Потребує дії сьогодні",
        "sev_warning": "Варто подивитись",
        "sev_ok": "Під контролем",
        "ai_evidence": "На чому це ґрунтується",
        "leaks_frozen_hint": "Розпродаж або зниження ціни повертає ці гроші в обіг. Поки лежить — не працює і накопичує плату за зберігання.",
        "ai_main_summary": "Головне за сьогодні",
        "ai_actions": "Що робити",
        "ai_supporting_data": "Опорні показники",
        "ai_orders_7d": "Замовлень за 7 днів", "ai_prev": "попередні 7",
        "ai_stockouts": "Стокаути", "ai_stockouts_sub": "продаються, але немає",
        "ai_reorder_now": "Замовити зараз", "ai_units_to_order": "Одиниць до замовлення",
        "ai_orders_chart": "Замовлення по днях, 30 днів",
        "leaks_need_rerun": "Розрахунок втрат застарілої версії — запусти 13_money_leaks.py заново",
        "leaks_lost_title": "Недоотримана виручка",
        "leaks_lost_note": "цих грошей уже не буде · оцінка на 30 днів",
        "leaks_frozen_title": "Заморожено в товарі",
        "leaks_frozen_note": "не втрата — повертається розпродажем",
        "leaks_none": "Втрат не знайдено",
        "leaks_title": "Де втрачаються гроші",
        "leaks_note": "оцінка втрат за 30 днів на поточних даних",
        "leaks_by_type": "Втрати за типом",
        "leaks_of_total": "від суми",
        "leaks_top_positions": "Найбільші втрати за позиціями",
        "leak_stockout_now": "Немає на складі",
        "leak_stockout_soon": "Буде розрив",
        "leak_conversion": "Недобір конверсії",
        "leak_refunds": "Повернення",
        "leak_fees": "Збори Amazon",
        "leak_dead_stock": "Заморожений запас",
        "ads_ai_title": "Що каже аналітик",
        "ads_ai_working": "Аналізую рекламу — за мить оновлю сторінку",
        "ads_ai_refresh": "Аналіз",
        "ads_ai_none": "Висновків ще немає — натисни «Аналіз», раннер підготує їх за пару хвилин",
        "nav_ads": "Реклама", "ads_title": "Реклама",
        "no_ads_data": "Немає таблиць — запусти 05_ads_loader.py",
        "no_ads_rows": "За цей період даних немає",
        "ads_type": "Тип", "ads_spend": "Витрати", "ads_sales": "Продажі",
        "ads_orders": "замовлень", "ads_clicks": "кліків",
        "ads_campaign": "Кампанія",
        "ads_chart_title": "Витрати, продажі та ACOS по днях",
        "ads_by_campaign": "За кампаніями",
        "search_campaign": "Пошук за назвою кампанії",
        "ads_waste_title": "Реклама на товари, яких немає на складі",
        "ads_waste_note": "{n} кампаній рекламують SKU з нульовим залишком і без поставок у дорозі",
        "ads_waste_hint": "Збіг визначається за назвою кампанії — перевір перед вимкненням. Реклама товару, який неможливо купити, витрачає бюджет і псує показники лістингу.",
        "ads_legend": "🔴 витрати без продажів · 🟡 ACOS вище 60%",
        "nav_users": "Користувачі",
        "nav_alerts": "Алерти", "alerts_title": "Алерти системи",
        "no_alerts_data": "Немає даних — запусти 12_watchdog.py",
        "alerts_info_block": "Довідково",
        "alerts_info_note": "Це не проблеми — просто стан системи. Дії не потребують.",
        "alerts_critical": "Потребує дії", "alerts_warning": "Увага",
        "alerts_need_action": "розібратись сьогодні",
        "alerts_last_check": "Остання перевірка",
        "alerts_all_clear": "Відкритих проблем немає — усе працює",
        "alerts_ongoing": "триває", "alerts_hours": "год", "alerts_days": "дн.",
        "alerts_seen": "спрацювало разів:", "alerts_last": "востаннє",
        "alerts_resolved": "Закриті проблеми",
        "alerts_no_resolved": "Поки нічого не закривалось",
        "alerts_lasted": "тривало", "alerts_fixed_at": "зникло",
        "alerts_frequent": "Проблеми, що повторюються",
        "alerts_no_frequent": "Повторюваних проблем немає",
        "alerts_frequent_note": "Те, що виникає знову і знову — симптом системної причини, а не разовий збій.",
        "alerts_cache_note": "Дані з alerts · джерело те саме, що для Telegram",
        "ai_refresh": "Оновити аналіз",
        "ai_refresh_queued": "Заявку прийнято — раннер запустить аналіз протягом хвилини. Онови сторінку через 2-3 хв.",
        "ai_refresh_failed": "Не вдалось поставити заявку",
        "ai_job_pending": "Заявка в черзі — раннер ось-ось візьме її",
        "ai_job_running": "Аналіз виконується — онови сторінку за хвилину",
        "ai_text_lang": "Мова висновків",
        "ai_lang_missing": "Висновків твоєю мовою ще немає",
        "nav_ai": "AI-аналітик", "ai_title": "Висновки ІІ-аналітика",
        "no_ai_data": "Немає даних — запусти 10_ai_analyst.py",
        "ai_showing_date": "За обрану дату даних немає — показано звіт за {d}",
        "ai_report_date": "Дата звіту",
        "ai_by_agent": "За напрямами",
        "ai_model": "Модель",
        "ai_history": "Історія головних сводок",
        "ai_cache_note": "Дані з ai_insights · висновки формуються щодня",
        "age_title": "Ефективність за віком замовлення",
        "age_note": "На якому дні після замовлення запит приймається Amazon. Через місяць даних вистачить, щоб звузити вікно за фактами, а не на око.",
        "age_chart_title": "Статуси запитів за віком замовлення",
        "age_axis": "днів від замовлення",
        "age_low_sample": "Поки лише {n} спостережень — для надійних висновків потрібно 200+. Не звужуй вікно на цих даних.",
        "nav_reviews": "Відгуки", "reviews_title": "Запити на відгуки",
        "no_reviews_data": "Немає даних — запусти 11_review_requests.py",
        "health_ok": "Розсилка працює — останній прогін у межах 25 год",
        "health_warn": "НЕМАЄ РОЗСИЛКИ {h:.0f} год (поріг 25 год)",
        "sent_today": "Надіслано сьогодні", "sent_7d": "за 7 днів",
        "pool_label": "Пул кандидатів", "pool_sub": "чекають відправки",
        "burning_label": "Горить (25-33 дні)", "failed_7d": "Помилок за 7 днів",
        "daily_volume": "Обсяг розсилки по днях",
        "st_sent": "Надіслано", "st_already": "Вже було",
        "st_outside": "Поза вікном", "st_failed": "Помилка",
        "status_hint": "Вже було — запит слали раніше, Amazon відхилив дубль (це норма). Поза вікном — замовлення ще/вже поза межами 5-30 днів після доставки.",
        "pool_title": "Пул за терміновістю",
        "pool_fresh": "Свіжі (8-15 дн.)", "pool_mid": "Середні (15-25 дн.)",
        "pool_burning": "Горять (25-33 дн.)",
        "funnel_title": "Воронка за 30 днів",
        "f_orders": "Shipped замовлень", "f_pool": "Пул кандидатів", "f_sent": "Надіслано",
        "coverage_title": "Покриття за датами замовлень",
        "coverage_note": "Запит можна надіслати лише у вікні 5-30 днів після доставки. Свіжі дати ще зріють — це норма, не втрата.",
        "cov_orders": "Замовлень", "cov_pct": "Покриття",
        "cov_unprocessed": "Не оброблено", "matured_only": "лише дозрілі дати",
        "missed_total": "Упущено", "missed_sub": "вікно закрилось без запиту",
        "st_ok": "OK", "st_progress": "В роботі", "st_missed": "Упущено",
        "st_maturing": "Зріє",
        "coverage_legend": "🟢 покриття в нормі · 🟠 вікно ще відкрите, доганяємо · 🔴 вікно закрилось, відгуки втрачені · ⏳ замовлення надто свіже",
        "by_asin_title": "За товарами",
        "active_asins": "Активних ASIN",
        "heatmap_title": "Теплова карта покриття (день тижня × тиждень)",
        "heatmap_note": "Відсоток покриття по днях. Видно системні провали — наприклад, якщо вихідні стабільно просідають, значить раннер тоді не працює.",
        "dow_names": "Пн,Вт,Ср,Чт,Пт,Сб,Нд",
        "asin_chart_title": "Топ ASIN за надісланими запитами",
        "no_asin_data": "Немає даних по ASIN",
        "reviews_cache_note": "Дані з review_requests · Solicitations API",
        "nav_forecast": "Прогноз", "forecast_title": "Прогноз запасів",
        "no_forecast_data": "Немає даних — запусти 09_forecast.py",
        "status_filter": "Статус",
        "reorder_now_label": "Замовити зараз", "reorder_soon_label": "скоро",
        "out_of_stock_label": "Немає на складі",
        "units_to_order_label": "Одиниць до замовлення",
        "overstock_label": "Затоварення",
        "calculated_at": "Розраховано",
        "cover_distribution": "Розподіл SKU за днями покриття",
        "days_of_cover_axis": "днів покриття",
        "forecast_by_sku": "Прогноз за SKU",
        "col_velocity": "шт/день", "col_trend": "Тренд",
        "col_stock": "Запас", "col_inbound": "В дорозі",
        "col_days_cover": "Днів", "col_stockout": "Закінчиться",
        "col_recommended": "Замовити",
        "forecast_legend": "🔴 замовити терміново / немає на складі · 🟡 замовити скоро",
        "nav_finance": "Фінанси", "finance_title": "Фінанси",
        "no_finance_data": "Немає даних — запусти 06_finance_loader.py",
        "gross_label": "Валова виручка", "promo_label": "Промо",
        "fees_label": "Збори Amazon", "commission_label": "Комісія",
        "refunds_label": "Повернення", "refund_items_label": "позицій",
        "net_label": "Чистими", "finance_chart_title": "Виручка та комісії по днях",
        "finance_by_sku": "Економіка за SKU",
        "finance_cache_note": "Дані з finance_shipment_items · Financial Events API",
        "orders_n": "Замовлення", "revenue": "Виручка",
        "avg_check": "Середній чек", "orders_today": "Замовлень сьогодні",
        "by_utc": "за UTC", "chart_daily": "Замовлення та виручка по днях",
        "orders_series": "Замовлення", "revenue_series": "Виручка",
        "top10_sku": "Топ-10 SKU за кількістю", "last20": "Останні 20 замовлень",
        "col_order": "Замовлення", "col_date": "Дата", "col_status": "Статус",
        "col_market": "Маркет", "col_sum": "Сума",
        "no_orders": "Немає замовлень за обраний період.",
        "search": "Пошук за SKU / ASIN / назвою (можна декілька через кому)", "sku_in_stock": "SKU із залишком > 0",
        "total_rows": "всього рядків", "inbound_sub": "working + shipped + receiving",
        "top15_sku": "Топ-15 SKU за fulfillable", "stock_by_sku": "Залишки за SKU",
        "snapshot": "знімок", "col_name": "Назва", "col_photo": "Фото",
        "col_qty": "Кількість",
        "no_inventory": "Немає даних у fba_inventory — запусти 02_fba_inventory_loader.py",
        "legend_stock": "🔴 fulfillable = 0 · 🟡 fulfillable < 20",
        "cache_note": "Дані з Merinnovation · кеш 10 хв",
        "sort_by": "Сортувати за", "sort_asc": "За зростанням", "sort_desc": "За спаданням",
        "sort_order_label": "Порядок",
    },
    "ru": {
        "login_subtitle": "Аналитический кабинет",
        "login_user": "Логин", "login_pass": "Пароль",
        "login_btn": "Войти", "logout": "Выйти",
        "login_empty": "Введи логин и пароль",
        "login_bad": "Неверный логин или пароль",
        "login_throttled": "Слишком много попыток. Попробуй через 15 минут.",
        "login_disabled": "Доступ отключён. Обратитесь к администратору.",
        "role_admin": "Администратор", "role_user": "Пользователь",
        "admin_only": "Страница доступна только администратору",
        "pw_required": "Нужно сменить пароль перед работой",
        "pw_new": "Новый пароль", "pw_repeat": "Повторите пароль",
        "pw_save": "Сохранить", "pw_short": "Пароль не короче 8 символов",
        "pw_mismatch": "Пароли не совпадают", "pw_changed": "Пароль изменён",
        "nav_overview": "Обзор", "nav_stock": "Остатки",
        "overview_title": "Merinnovation — Обзор",
        "stock_title": "Остатки FBA",
        "marketplace": "Маркетплейс", "period": "Период", "days": "дней",
        "today_option": "Сегодня",
        "pending_note": "ожидает подтверждения",
        "sort_hint": "Сортировка применяется к таблице ниже",
        "search_orders": "Поиск по ASIN / номеру заказа (можно несколько через запятую)",
        "conversion_label": "Конверсия", "sessions_label": "сессий",
        "today_pending_hint": "точные данные Amazon появятся завтра",
        "estimate_label": "Оценка по ценам позиций",
        "nav_traffic": "Трафик", "traffic_title": "Продажи и трафик",
        "traffic_chart_title": "Сессии и конверсия по дням",
        "traffic_by_sku": "Трафик по SKU", "no_traffic_data": "Нет данных — запусти 04_sales_traffic_loader.py",
        "sessions_total": "Сессии", "pageviews_label": "просмотров страниц",
        "units_label": "единиц", "buybox_label": "Buy Box %",
        "traffic_cache_note": "Данные из sales_traffic · Amazon Sales & Traffic Report",
        "download_csv": "⬇ Скачать CSV",
        "per_1": "1 день", "per_7": "7 дней", "per_14": "14 дней",
        "per_30": "30 дней", "per_60": "60 дней", "per_90": "90 дней",
        "flt_period": "Период", "flt_gran": "Детализация",
        "flt_threshold": "Порог покрытия", "flt_status": "Статус", "flt_all": "Все",
        "gran_day": "День", "gran_week": "Неделя", "gran_month": "Месяц",
        "combo_title": "Заказы и запросы по датам заказа",
        "combo_processed": "Обработано (отправлено + уже было)",
        "legend_title": "Легенда статусов и как считается покрытие",
        "legend_body": """
**🟢 OK** (≥{th}%) — запросы ушли, делать ничего не нужно.

**🟠 В работе** — ниже цели, но окно 5-30 дней ещё открыто. Запросы дошлются автоматически, эти даты покроются. Это **не потеря**.

**🔴 Упущено** — окно закрылось, а покрытие осталось низким. Эти отзывы потеряны навсегда. Единственный статус, который реальная проблема.

**⏳ Зреет** — заказ моложе 8 дней, окно ещё не открылось. Норма, покроется само.

---

`Покрытие % = (отправлено + уже было) / заказов × 100`

`Не обработано = заказов − (отправлено + уже было)`

Итог считается **только по дозревшим датам** — иначе нули свежих дней занижали бы общий процент.
""",
        "sev_critical": "Требует действия сегодня",
        "sev_warning": "Стоит посмотреть",
        "sev_ok": "Под контролем",
        "ai_evidence": "На чём это основано",
        "leaks_frozen_hint": "Распродажа или снижение цены возвращает эти деньги в оборот. Пока лежит — не работает и копит плату за хранение.",
        "ai_main_summary": "Главное за сегодня",
        "ai_actions": "Что делать",
        "ai_supporting_data": "Опорные показатели",
        "ai_orders_7d": "Заказов за 7 дней", "ai_prev": "предыдущие 7",
        "ai_stockouts": "Стокауты", "ai_stockouts_sub": "продаются, но нет",
        "ai_reorder_now": "Заказать сейчас", "ai_units_to_order": "Единиц к заказу",
        "ai_orders_chart": "Заказы по дням, 30 дней",
        "leaks_need_rerun": "Расчёт потерь старой версии — запусти 13_money_leaks.py заново",
        "leaks_lost_title": "Недополученная выручка",
        "leaks_lost_note": "этих денег уже не будет · оценка на 30 дней",
        "leaks_frozen_title": "Заморожено в товаре",
        "leaks_frozen_note": "не потеря — возвращается распродажей",
        "leaks_none": "Потерь не найдено",
        "leaks_title": "Где теряются деньги",
        "leaks_note": "оценка потерь за 30 дней на текущих данных",
        "leaks_by_type": "Потери по типу",
        "leaks_of_total": "от суммы",
        "leaks_top_positions": "Крупнейшие потери по позициям",
        "leak_stockout_now": "Нет на складе",
        "leak_stockout_soon": "Будет разрыв",
        "leak_conversion": "Недобор конверсии",
        "leak_refunds": "Возвраты",
        "leak_fees": "Сборы Amazon",
        "leak_dead_stock": "Замороженный запас",
        "nav_ads": "Реклама", "ads_title": "Реклама",
        "ads_ai_title": "Что говорит аналитик",
        "ads_ai_working": "Анализирую рекламу — сейчас обновлю страницу",
        "ads_ai_refresh": "Анализ",
        "ads_ai_none": "Выводов ещё нет — нажми «Анализ», раннер подготовит их за пару минут",
        "no_ads_data": "Нет таблиц — запусти 05_ads_loader.py",
        "no_ads_rows": "За этот период данных нет",
        "ads_type": "Тип", "ads_spend": "Расходы", "ads_sales": "Продажи",
        "ads_orders": "заказов", "ads_clicks": "кликов",
        "ads_campaign": "Кампания",
        "ads_chart_title": "Расходы, продажи и ACOS по дням",
        "ads_by_campaign": "По кампаниям",
        "search_campaign": "Поиск по названию кампании",
        "ads_waste_title": "Реклама на товары, которых нет на складе",
        "ads_waste_note": "{n} кампаний рекламируют SKU с нулевым остатком и без поставок в пути",
        "ads_waste_hint": "Совпадение определяется по названию кампании — проверь перед отключением. Реклама товара, который нельзя купить, тратит бюджет и портит показатели листинга.",
        "ads_legend": "🔴 расходы без продаж · 🟡 ACOS выше 60%",
        "nav_users": "Пользователи",
        "nav_alerts": "Алерты", "alerts_title": "Алерты системы",
        "no_alerts_data": "Нет данных — запусти 12_watchdog.py",
        "alerts_info_block": "Справочно",
        "alerts_info_note": "Это не проблемы — просто состояние системы. Действий не требуют.",
        "alerts_critical": "Требует действия", "alerts_warning": "Внимание",
        "alerts_need_action": "разобраться сегодня",
        "alerts_last_check": "Последняя проверка",
        "alerts_all_clear": "Открытых проблем нет — всё работает",
        "alerts_ongoing": "длится", "alerts_hours": "ч", "alerts_days": "дн.",
        "alerts_seen": "срабатывало раз:", "alerts_last": "последний раз",
        "alerts_resolved": "Закрытые проблемы",
        "alerts_no_resolved": "Пока ничего не закрывалось",
        "alerts_lasted": "длилось", "alerts_fixed_at": "исчезло",
        "alerts_frequent": "Повторяющиеся проблемы",
        "alerts_no_frequent": "Повторяющихся проблем нет",
        "alerts_frequent_note": "То, что возникает снова и снова — симптом системной причины, а не разовый сбой.",
        "alerts_cache_note": "Данные из alerts · источник тот же, что для Telegram",
        "ai_refresh": "Обновить анализ",
        "ai_refresh_queued": "Заявка принята — раннер запустит анализ в течение минуты. Обнови страницу через 2-3 мин.",
        "ai_refresh_failed": "Не удалось поставить заявку",
        "ai_job_pending": "Заявка в очереди — раннер вот-вот её возьмёт",
        "ai_job_running": "Анализ выполняется — обнови страницу через минуту",
        "ai_text_lang": "Язык выводов",
        "ai_lang_missing": "Выводов на твоём языке пока нет",
        "nav_ai": "AI-аналитик", "ai_title": "Выводы ИИ-аналитика",
        "no_ai_data": "Нет данных — запусти 10_ai_analyst.py",
        "ai_showing_date": "За выбранную дату данных нет — показан отчёт за {d}",
        "ai_report_date": "Дата отчёта",
        "ai_by_agent": "По направлениям",
        "ai_model": "Модель",
        "ai_history": "История главных сводок",
        "ai_cache_note": "Данные из ai_insights · выводы формируются ежедневно",
        "age_title": "Эффективность по возрасту заказа",
        "age_note": "На каком дне после заказа запрос принимается Amazon. Через месяц данных хватит, чтобы сузить окно по фактам, а не на глаз.",
        "age_chart_title": "Статусы запросов по возрасту заказа",
        "age_axis": "дней от заказа",
        "age_low_sample": "Пока лишь {n} наблюдений — для надёжных выводов нужно 200+. Не сужай окно на этих данных.",
        "nav_reviews": "Отзывы", "reviews_title": "Запросы на отзывы",
        "no_reviews_data": "Нет данных — запусти 11_review_requests.py",
        "health_ok": "Рассылка работает — последний прогон в пределах 25 ч",
        "health_warn": "НЕТ РАССЫЛКИ {h:.0f} ч (порог 25 ч)",
        "sent_today": "Отправлено сегодня", "sent_7d": "за 7 дней",
        "pool_label": "Пул кандидатов", "pool_sub": "ждут отправки",
        "burning_label": "Горит (25-33 дня)", "failed_7d": "Ошибок за 7 дней",
        "daily_volume": "Объём рассылки по дням",
        "st_sent": "Отправлено", "st_already": "Уже было",
        "st_outside": "Вне окна", "st_failed": "Ошибка",
        "status_hint": "Уже было — запрос слали раньше, Amazon отклонил дубль (это норма). Вне окна — заказ ещё/уже за пределами 5-30 дней после доставки.",
        "pool_title": "Пул по срочности",
        "pool_fresh": "Свежие (8-15 дн.)", "pool_mid": "Средние (15-25 дн.)",
        "pool_burning": "Горят (25-33 дн.)",
        "funnel_title": "Воронка за 30 дней",
        "f_orders": "Shipped заказов", "f_pool": "Пул кандидатов", "f_sent": "Отправлено",
        "coverage_title": "Покрытие по датам заказов",
        "coverage_note": "Запрос можно отправить только в окне 5-30 дней после доставки. Свежие даты ещё зреют — это норма, не потеря.",
        "cov_orders": "Заказов", "cov_pct": "Покрытие",
        "cov_unprocessed": "Не обработано", "matured_only": "только дозревшие даты",
        "missed_total": "Упущено", "missed_sub": "окно закрылось без запроса",
        "st_ok": "OK", "st_progress": "В работе", "st_missed": "Упущено",
        "st_maturing": "Зреет",
        "coverage_legend": "🟢 покрытие в норме · 🟠 окно ещё открыто, догоняем · 🔴 окно закрылось, отзывы потеряны · ⏳ заказ слишком свежий",
        "by_asin_title": "По товарам",
        "active_asins": "Активных ASIN",
        "heatmap_title": "Тепловая карта покрытия (день недели × неделя)",
        "heatmap_note": "Процент покрытия по дням. Видны системные провалы — например, если выходные стабильно проседают, значит раннер тогда не работает.",
        "dow_names": "Пн,Вт,Ср,Чт,Пт,Сб,Вс",
        "asin_chart_title": "Топ ASIN по отправленным запросам",
        "no_asin_data": "Нет данных по ASIN",
        "reviews_cache_note": "Данные из review_requests · Solicitations API",
        "nav_forecast": "Прогноз", "forecast_title": "Прогноз запасов",
        "no_forecast_data": "Нет данных — запусти 09_forecast.py",
        "status_filter": "Статус",
        "reorder_now_label": "Заказать сейчас", "reorder_soon_label": "скоро",
        "out_of_stock_label": "Нет на складе",
        "units_to_order_label": "Единиц к заказу",
        "overstock_label": "Затоваривание",
        "calculated_at": "Рассчитано",
        "cover_distribution": "Распределение SKU по дням покрытия",
        "days_of_cover_axis": "дней покрытия",
        "forecast_by_sku": "Прогноз по SKU",
        "col_velocity": "шт/день", "col_trend": "Тренд",
        "col_stock": "Запас", "col_inbound": "В пути",
        "col_days_cover": "Дней", "col_stockout": "Закончится",
        "col_recommended": "Заказать",
        "forecast_legend": "🔴 заказать срочно / нет на складе · 🟡 заказать скоро",
        "nav_finance": "Финансы", "finance_title": "Финансы",
        "no_finance_data": "Нет данных — запусти 06_finance_loader.py",
        "gross_label": "Валовая выручка", "promo_label": "Промо",
        "fees_label": "Сборы Amazon", "commission_label": "Комиссия",
        "refunds_label": "Возвраты", "refund_items_label": "позиций",
        "net_label": "Чистыми", "finance_chart_title": "Выручка и комиссии по дням",
        "finance_by_sku": "Экономика по SKU",
        "finance_cache_note": "Данные из finance_shipment_items · Financial Events API",
        "orders_n": "Заказы", "revenue": "Выручка",
        "avg_check": "Средний чек", "orders_today": "Заказов сегодня",
        "by_utc": "по UTC", "chart_daily": "Заказы и выручка по дням",
        "orders_series": "Заказы", "revenue_series": "Выручка",
        "top10_sku": "Топ-10 SKU по количеству", "last20": "Последние 20 заказов",
        "col_order": "Заказ", "col_date": "Дата", "col_status": "Статус",
        "col_market": "Маркет", "col_sum": "Сумма",
        "no_orders": "Нет заказов за выбранный период.",
        "search": "Поиск по SKU / ASIN / названию (можно несколько через запятую)", "sku_in_stock": "SKU с остатком > 0",
        "total_rows": "всего строк", "inbound_sub": "working + shipped + receiving",
        "top15_sku": "Топ-15 SKU по fulfillable", "stock_by_sku": "Остатки по SKU",
        "snapshot": "снапшот", "col_name": "Название", "col_photo": "Фото",
        "col_qty": "Кол-во",
        "no_inventory": "Нет данных в fba_inventory — запусти 02_fba_inventory_loader.py",
        "legend_stock": "🔴 fulfillable = 0 · 🟡 fulfillable < 20",
        "cache_note": "Данные из Merinnovation · кэш 10 мин",
        "sort_by": "Сортировать по", "sort_asc": "По возрастанию", "sort_desc": "По убыванию",
        "sort_order_label": "Порядок",
    },
    "en": {
        "login_subtitle": "Analytics dashboard",
        "login_user": "Login", "login_pass": "Password",
        "login_btn": "Sign in", "logout": "Sign out",
        "login_empty": "Enter login and password",
        "login_bad": "Invalid login or password",
        "login_throttled": "Too many attempts. Try again in 15 minutes.",
        "login_disabled": "Access disabled. Contact the administrator.",
        "role_admin": "Administrator", "role_user": "User",
        "admin_only": "This page is for administrators only",
        "pw_required": "You must change your password first",
        "pw_new": "New password", "pw_repeat": "Repeat password",
        "pw_save": "Save", "pw_short": "Password must be 8+ characters",
        "pw_mismatch": "Passwords do not match", "pw_changed": "Password changed",
        "nav_overview": "Overview", "nav_stock": "Stock",
        "overview_title": "Merinnovation — Overview",
        "stock_title": "FBA Stock",
        "marketplace": "Marketplace", "period": "Period", "days": "days",
        "today_option": "Today",
        "pending_note": "pending confirmation",
        "sort_hint": "Sorting applies to the table below",
        "search_orders": "Search ASIN / order number (comma-separated for multiple)",
        "conversion_label": "Conversion", "sessions_label": "sessions",
        "today_pending_hint": "accurate Amazon data available tomorrow",
        "estimate_label": "Estimate from item prices",
        "nav_traffic": "Traffic", "traffic_title": "Sales & Traffic",
        "traffic_chart_title": "Sessions & conversion by day",
        "traffic_by_sku": "Traffic by SKU", "no_traffic_data": "No data — run 04_sales_traffic_loader.py",
        "sessions_total": "Sessions", "pageviews_label": "page views",
        "units_label": "units", "buybox_label": "Buy Box %",
        "traffic_cache_note": "Data from sales_traffic · Amazon Sales \u0026 Traffic Report",
        "download_csv": "⬇ Download CSV",
        "per_1": "1 day", "per_7": "7 days", "per_14": "14 days",
        "per_30": "30 days", "per_60": "60 days", "per_90": "90 days",
        "flt_period": "Period", "flt_gran": "Granularity",
        "flt_threshold": "Coverage target", "flt_status": "Status", "flt_all": "All",
        "gran_day": "Day", "gran_week": "Week", "gran_month": "Month",
        "combo_title": "Orders vs requests by order date",
        "combo_processed": "Processed (sent + already)",
        "legend_title": "Status legend and how coverage is calculated",
        "legend_body": """
**🟢 OK** (≥{th}%) — requests went out, nothing to do.

**🟠 In progress** — below target, but the 5-30 day window is still open. Requests will be sent automatically. This is **not a loss**.

**🔴 Missed** — the window closed with coverage still low. These reviews are lost for good. The only status that is a real problem.

**⏳ Maturing** — order is under 8 days old, the window hasn't opened yet. Normal, will be covered automatically.

---

`Coverage % = (sent + already) / orders × 100`

`Unprocessed = orders − (sent + already)`

The total counts **matured dates only** — otherwise zeros from recent days would drag the overall percentage down.
""",
        "sev_critical": "Needs action today",
        "sev_warning": "Worth a look",
        "sev_ok": "Under control",
        "ai_evidence": "What this is based on",
        "leaks_frozen_hint": "Selling through or discounting returns this money to circulation. While it sits, it earns nothing and accrues storage fees.",
        "ai_main_summary": "Today's headline",
        "ai_actions": "Actions",
        "ai_supporting_data": "Supporting metrics",
        "ai_orders_7d": "Orders last 7 days", "ai_prev": "previous 7",
        "ai_stockouts": "Stockouts", "ai_stockouts_sub": "selling but unavailable",
        "ai_reorder_now": "Reorder now", "ai_units_to_order": "Units to order",
        "ai_orders_chart": "Orders by day, 30 days",
        "leaks_need_rerun": "Leak calculation is from an older version — rerun 13_money_leaks.py",
        "leaks_lost_title": "Lost revenue",
        "leaks_lost_note": "gone for good · 30-day estimate",
        "leaks_frozen_title": "Frozen in stock",
        "leaks_frozen_note": "not a loss — recoverable by selling through",
        "leaks_none": "No losses found",
        "leaks_title": "Where money is leaking",
        "leaks_note": "estimated 30-day loss on current data",
        "leaks_by_type": "Losses by type",
        "leaks_of_total": "of total",
        "leaks_top_positions": "Largest losses by SKU",
        "leak_stockout_now": "Out of stock",
        "leak_stockout_soon": "Gap incoming",
        "leak_conversion": "Conversion shortfall",
        "leak_refunds": "Refunds",
        "leak_fees": "Amazon fees",
        "leak_dead_stock": "Dead stock",
        "nav_ads": "Ads", "ads_title": "Advertising",
        "ads_ai_title": "What the analyst says",
        "ads_ai_working": "Analysing ads — refreshing shortly",
        "ads_ai_refresh": "Analyse",
        "ads_ai_none": "No findings yet — press Analyse, the runner will prepare them in a couple of minutes",
        "no_ads_data": "No tables — run 05_ads_loader.py",
        "no_ads_rows": "No data for this period",
        "ads_type": "Type", "ads_spend": "Spend", "ads_sales": "Sales",
        "ads_orders": "orders", "ads_clicks": "clicks",
        "ads_campaign": "Campaign",
        "ads_chart_title": "Spend, sales and ACOS by day",
        "ads_by_campaign": "By campaign",
        "search_campaign": "Search by campaign name",
        "ads_waste_title": "Ads running on out-of-stock products",
        "ads_waste_note": "{n} campaigns advertise SKUs with zero stock and nothing inbound",
        "ads_waste_hint": "Matched by campaign name — verify before pausing. Advertising something that cannot be bought wastes budget and hurts listing metrics.",
        "ads_legend": "🔴 spend with no sales · 🟡 ACOS above 60%",
        "nav_users": "Users",
        "nav_alerts": "Alerts", "alerts_title": "System alerts",
        "no_alerts_data": "No data — run 12_watchdog.py",
        "alerts_info_block": "For reference",
        "alerts_info_note": "Not problems — just system state. No action needed.",
        "alerts_critical": "Needs action", "alerts_warning": "Warning",
        "alerts_need_action": "handle today",
        "alerts_last_check": "Last check",
        "alerts_all_clear": "No open issues — everything is running",
        "alerts_ongoing": "ongoing", "alerts_hours": "h", "alerts_days": "d",
        "alerts_seen": "seen times:", "alerts_last": "last",
        "alerts_resolved": "Resolved issues",
        "alerts_no_resolved": "Nothing resolved yet",
        "alerts_lasted": "lasted", "alerts_fixed_at": "cleared",
        "alerts_frequent": "Recurring issues",
        "alerts_no_frequent": "No recurring issues",
        "alerts_frequent_note": "What keeps coming back is a symptom of a systemic cause, not a one-off glitch.",
        "alerts_cache_note": "Data from alerts · same source as Telegram",
        "ai_refresh": "Refresh analysis",
        "ai_refresh_queued": "Queued — the runner will start within a minute. Refresh the page in 2-3 min.",
        "ai_refresh_failed": "Could not queue the job",
        "ai_job_pending": "Queued — the runner will pick it up shortly",
        "ai_job_running": "Analysis running — refresh in a minute",
        "ai_text_lang": "Text language",
        "ai_lang_missing": "No findings in your language yet",
        "nav_ai": "AI analyst", "ai_title": "AI analyst findings",
        "no_ai_data": "No data — run 10_ai_analyst.py",
        "ai_showing_date": "No data for the selected date — showing {d}",
        "ai_report_date": "Report date",
        "ai_by_agent": "By area",
        "ai_model": "Model",
        "ai_history": "Past summaries",
        "ai_cache_note": "Data from ai_insights · generated daily",
        "age_title": "Effectiveness by order age",
        "age_note": "Which day after the order Amazon accepts the request. In a month there will be enough data to narrow the window on facts.",
        "age_chart_title": "Request status by order age",
        "age_axis": "days since order",
        "age_low_sample": "Only {n} observations so far — 200+ needed for reliable conclusions. Do not narrow the window on this.",
        "nav_reviews": "Reviews", "reviews_title": "Review Requests",
        "no_reviews_data": "No data — run 11_review_requests.py",
        "health_ok": "Sending healthy — last run within 25h",
        "health_warn": "NO SENDING for {h:.0f}h (threshold 25h)",
        "sent_today": "Sent today", "sent_7d": "last 7 days",
        "pool_label": "Candidate pool", "pool_sub": "awaiting send",
        "burning_label": "Burning (25-33 days)", "failed_7d": "Failed (7 days)",
        "daily_volume": "Daily sending volume",
        "st_sent": "Sent", "st_already": "Already",
        "st_outside": "Outside window", "st_failed": "Failed",
        "status_hint": "Already — request was sent earlier, Amazon declined the duplicate (normal). Outside — order is not within the 5-30 day post-delivery window.",
        "pool_title": "Pool by urgency",
        "pool_fresh": "Fresh (8-15d)", "pool_mid": "Mid (15-25d)",
        "pool_burning": "Burning (25-33d)",
        "funnel_title": "Funnel, last 30 days",
        "f_orders": "Shipped orders", "f_pool": "Candidate pool", "f_sent": "Sent",
        "coverage_title": "Coverage by order date",
        "coverage_note": "Requests are only allowed within 5-30 days after delivery. Recent dates are still maturing — normal, not a loss.",
        "cov_orders": "Orders", "cov_pct": "Coverage",
        "cov_unprocessed": "Unprocessed", "matured_only": "matured dates only",
        "missed_total": "Missed", "missed_sub": "window closed with no request",
        "st_ok": "OK", "st_progress": "In progress", "st_missed": "Missed",
        "st_maturing": "Maturing",
        "coverage_legend": "🟢 on target · 🟠 window still open, catching up · 🔴 window closed, reviews lost · ⏳ order too recent",
        "by_asin_title": "By product",
        "active_asins": "Active ASINs",
        "heatmap_title": "Coverage heatmap (weekday x week)",
        "heatmap_note": "Coverage % by day. Reveals systemic gaps, e.g. weekends consistently dropping means the runner is idle then.",
        "dow_names": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        "asin_chart_title": "Top ASIN by requests sent",
        "no_asin_data": "No ASIN data",
        "reviews_cache_note": "Data from review_requests · Solicitations API",
        "nav_forecast": "Forecast", "forecast_title": "Inventory Forecast",
        "no_forecast_data": "No data — run 09_forecast.py",
        "status_filter": "Status",
        "reorder_now_label": "Reorder now", "reorder_soon_label": "soon",
        "out_of_stock_label": "Out of stock",
        "units_to_order_label": "Units to order",
        "overstock_label": "Overstock",
        "calculated_at": "Calculated",
        "cover_distribution": "SKU distribution by days of cover",
        "days_of_cover_axis": "days of cover",
        "forecast_by_sku": "Forecast by SKU",
        "col_velocity": "units/day", "col_trend": "Trend",
        "col_stock": "Stock", "col_inbound": "In transit",
        "col_days_cover": "Days", "col_stockout": "Stockout",
        "col_recommended": "Order",
        "forecast_legend": "🔴 reorder now / out of stock · 🟡 reorder soon",
        "nav_finance": "Finance", "finance_title": "Finance",
        "no_finance_data": "No data — run 06_finance_loader.py",
        "gross_label": "Gross revenue", "promo_label": "Promo",
        "fees_label": "Amazon fees", "commission_label": "Commission",
        "refunds_label": "Refunds", "refund_items_label": "items",
        "net_label": "Net", "finance_chart_title": "Revenue & fees by day",
        "finance_by_sku": "Economics by SKU",
        "finance_cache_note": "Data from finance_shipment_items · Financial Events API",
        "orders_n": "Orders", "revenue": "Revenue",
        "avg_check": "Avg order value", "orders_today": "Orders today",
        "by_utc": "UTC", "chart_daily": "Orders & revenue by day",
        "orders_series": "Orders", "revenue_series": "Revenue",
        "top10_sku": "Top-10 SKU by quantity", "last20": "Last 20 orders",
        "col_order": "Order", "col_date": "Date", "col_status": "Status",
        "col_market": "Market", "col_sum": "Total",
        "no_orders": "No orders for selected period.",
        "search": "Search SKU / ASIN / name (comma-separated for multiple)", "sku_in_stock": "SKUs in stock > 0",
        "total_rows": "total rows", "inbound_sub": "working + shipped + receiving",
        "top15_sku": "Top-15 SKU by fulfillable", "stock_by_sku": "Stock by SKU",
        "snapshot": "snapshot", "col_name": "Product name", "col_photo": "Photo",
        "col_qty": "Qty",
        "no_inventory": "No data in fba_inventory — run 02_fba_inventory_loader.py",
        "legend_stock": "🔴 fulfillable = 0 · 🟡 fulfillable < 20",
        "cache_note": "Data from Merinnovation · cache 10 min",
        "sort_by": "Sort by", "sort_asc": "Ascending", "sort_desc": "Descending",
        "sort_order_label": "Order",
    },
}

LANGS = ["uk", "ru", "en"]
LANG_LABELS = {"uk": "УКР", "ru": "РУС", "en": "ENG"}


def t(key: str) -> str:
    lang = st.session_state.get("lang", "uk")
    return TRANSLATIONS.get(lang, TRANSLATIONS["uk"]).get(key, key)


# ------------------------------------------------------------- sidebar ----

@st.cache_data(show_spinner=False)
def _logo_b64() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("logo.png", "Logo.png", "logo.PNG",
                 os.path.join("assets", "logo.png")):
        p = os.path.join(here, name)
        if os.path.exists(p):
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode()
    return None


def lang_selector() -> str:
    if "lang" not in st.session_state:
        st.session_state["lang"] = "uk"
    if "theme" not in st.session_state:
        st.session_state["theme"] = "dark"

    with st.sidebar:
        b64 = _logo_b64()
        if b64:
            st.markdown(
                f'<div style="padding: 4px 0 14px 0; text-align: center;">'
                f'<img class="mp-logo" src="data:image/png;base64,{b64}" '
                f'style="max-width: 175px; width: 100%;" /></div>',
                unsafe_allow_html=True,
            )
        st.page_link("app.py", label=t("nav_overview"), icon=":material/bar_chart:")
        st.page_link("pages/1_Stock.py", label=t("nav_stock"), icon=":material/inventory_2:")
        st.page_link("pages/2_Traffic.py", label=t("nav_traffic"), icon=":material/trending_up:")
        st.page_link("pages/3_Finance.py", label=t("nav_finance"), icon=":material/payments:")
        st.page_link("pages/4_Forecast.py", label=t("nav_forecast"), icon=":material/insights:")
        st.page_link("pages/5_Reviews.py", label=t("nav_reviews"), icon=":material/star:")
        st.page_link("pages/6_AI.py", label=t("nav_ai"), icon=":material/auto_awesome:")
        st.page_link("pages/8_Ads.py", label=t("nav_ads"), icon=":material/campaign:")
        # Алерти й Користувачі — лише для адміна: технічні алерти
        # звичайному користувачу нічого не дають, лише відволікають
        try:
            import auth as _auth
            _is_admin = _auth.is_admin()
        except Exception:
            _is_admin = True
        if _is_admin:
            st.page_link("pages/7_Alerts.py", label=t("nav_alerts"), icon=":material/notifications_active:")
            st.page_link("pages/9_Users.py", label=t("nav_users"), icon=":material/group:")
        st.markdown("---")

        cols = st.columns(3)
        for i, code in enumerate(LANGS):
            with cols[i]:
                if st.button(
                    LANG_LABELS[code], key=f"lang_{code}",
                    type="primary" if st.session_state["lang"] == code else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["lang"] = code
                    st.rerun()

        tc1, tc2 = st.columns(2)
        with tc1:
            if st.button("Dark", key="th_dark", use_container_width=True,
                         icon=":material/dark_mode:",
                         type="primary" if st.session_state["theme"] == "dark" else "secondary"):
                st.session_state["theme"] = "dark"
                st.rerun()
        with tc2:
            if st.button("Light", key="th_light", use_container_width=True,
                         icon=":material/light_mode:",
                         type="primary" if st.session_state["theme"] == "light" else "secondary"):
                st.session_state["theme"] = "light"
                st.rerun()

    return st.session_state["lang"]


# ---------------------------------------------------------------- DB ----

def _database_url() -> str:
    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(os.path.dirname(here), ".env"), override=False)
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL не знайдено ні в st.secrets, ні в .env")
    return url


@st.cache_resource
def get_conn():
    conn = psycopg2.connect(_database_url(), connect_timeout=10)
    conn.autocommit = True
    return conn


@st.cache_data(ttl=600, show_spinner=False)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    conn = get_conn()
    try:
        return pd.read_sql(sql, conn, params=params)
    except Exception:
        get_conn.clear()
        conn = get_conn()
        return pd.read_sql(sql, conn, params=params)


# ---------------------------------------------------------------- UI ----

def inject_css():
    th = cur_theme()
    st.markdown(f"""
<style>
[data-testid="stSidebarNav"] {{ display: none !important; }}
[data-testid="stToolbar"] {{ display: none !important; }}
[data-testid="stAppDeployButton"] {{ display: none !important; }}
[data-testid="stActionButtonIcon"] {{ display: none !important; }}
.stAppDeployButton, .stDeployButton {{ display: none !important; }}
[data-testid="stHeaderActionElements"] {{ display: none !important; }}
[data-testid="stDecoration"] {{ display: none !important; }}
[data-testid="stStatusWidget"] {{ display: none !important; }}
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}

.stApp {{ background: {th["bg"]} !important; }}
[data-testid="stSidebar"] {{ background: {th["sidebar"]} !important; }}
.stApp, .stApp p, .stApp span, .stApp label,
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ color: {th["text"]} !important; }}
.stCaption, .stApp small {{ color: {th["muted"]} !important; }}

.mp-logo {{ filter: {th["logo_filter"]}; }}

.block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; }}
header[data-testid="stHeader"] {{ background: transparent; }}

div[data-baseweb="select"] > div,
div[data-baseweb="select"] div,
[data-testid="stSelectbox"] * {{
    background-color: {th["card"]} !important;
    color: {th["text"]} !important;
    border-color: {th["border"]} !important;
}}
ul[role="listbox"], div[data-baseweb="popover"], div[data-baseweb="menu"] {{
    background-color: {th["card"]} !important;
}}
li[role="option"], li[role="option"] * {{
    background-color: {th["card"]} !important;
    color: {th["text"]} !important;
}}
li[role="option"]:hover,
li[role="option"][aria-selected="true"] {{
    background-color: {ACCENT} !important;
    color: #ffffff !important;
}}
li[role="option"]:hover *,
li[role="option"][aria-selected="true"] * {{
    color: #ffffff !important;
}}

[data-testid="stTextInput"] input {{
    background-color: {th["card"]} !important;
    color: {th["text"]} !important;
    border-color: {th["border"]} !important;
}}

button[kind="secondary"], button[kind="secondary"] * {{
    background-color: {th["card"]} !important;
    color: {th["text"]} !important;
    border-color: {th["border"]} !important;
}}
button[kind="secondary"]:hover {{ border-color: {ACCENT} !important; }}

[data-testid="stPageLink"] * {{ color: {th["text"]} !important; }}

.mp-card {{
    background: {th["card"]};
    border: 1px solid {th["border"]};
    border-radius: 12px;
    padding: 16px 18px;
    height: 100%;
}}
.mp-card .t {{ color: {th["muted"]}; font-size: 13px; margin-bottom: 6px; white-space: nowrap; }}
.mp-card .v {{ color: {th["text"]}; font-size: 28px; font-weight: 700; line-height: 1.15; }}
.mp-card .s {{ color: {th["muted"]}; font-size: 12px; margin-top: 4px; }}
.mp-card .d-up   {{ color: #10b981; font-size: 13px; margin-top: 4px; }}
.mp-card .d-down {{ color: #ef4444; font-size: 13px; margin-top: 4px; }}

.mp-table-wrap {{
    overflow-y: auto;
    border: 1px solid {th["border"]};
    border-radius: 10px;
    background: {th["card"]};
}}
.mp-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
.mp-table thead th {{
    position: sticky;
    top: 0;
    background: {th["card"]};
    color: {th["muted"]};
    text-align: left;
    padding: 9px 12px;
    border-bottom: 1px solid {th["border"]};
    font-weight: 600;
    z-index: 1;
    white-space: nowrap;
}}
.mp-table tbody td {{
    padding: 7px 12px;
    border-bottom: 1px solid {th["border"]};
    color: {th["text"]};
    vertical-align: middle;
}}
.mp-table tbody tr:hover {{ background: {th["row_hover"]}; }}
.mp-table tbody tr.row-zero {{ background: rgba(239,68,68,0.14); }}
.mp-table tbody tr.row-low {{ background: rgba(245,158,11,0.12); }}
.mp-table a {{ color: {ACCENT2}; text-decoration: none; font-weight: 500; }}
.mp-table a:hover {{ text-decoration: underline; }}
.mp-table img.mp-thumb {{
    width: 34px; height: 34px; object-fit: cover; border-radius: 6px;
    background: rgba(128,128,128,0.15); display: block;
}}
.mp-thumb-empty {{
    width: 34px; height: 34px; border-radius: 6px;
    background: rgba(128,128,128,0.15); display: block;
}}

h1, h2, h3 {{ letter-spacing: -0.02em; }}
</style>
""", unsafe_allow_html=True)


def metric_card(title: str, value: str, delta: str | None = None,
                delta_up: bool = True, sub: str | None = None):
    d = ""
    if delta:
        cls = "d-up" if delta_up else "d-down"
        arrow = "▲" if delta_up else "▼"
        d = f'<div class="{cls}">{arrow} {delta}</div>'
    s = f'<div class="s">{sub}</div>' if sub else ""
    st.markdown(
        f'<div class="mp-card"><div class="t">{title}</div>'
        f'<div class="v">{value}</div>{d}{s}</div>',
        unsafe_allow_html=True,
    )


# ------------------------------------------------------ HTML-таблиці ----

def cell_photo(url) -> str:
    if url and isinstance(url, str) and url.strip():
        return (f'<img class="mp-thumb" src="{url}" '
                f'onerror="this.outerHTML=\'<div class=mp-thumb-empty></div>\'">')
    return '<div class="mp-thumb-empty"></div>'


def cell_link(url, text) -> str:
    if not url or not text:
        return str(text or "")
    return f'<a href="{url}" target="_blank">{text}</a>'


def download_csv_button(df: pd.DataFrame, filename: str, key: str):
    """Кнопка 'Скачати CSV' під таблицею — заміна нативної кнопки
    st.dataframe, якої немає у кастомних HTML-таблицях."""
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=t("download_csv"), data=csv_bytes, file_name=f"{filename}.csv",
        mime="text/csv", key=f"dl_{key}", use_container_width=False,
    )


def render_html_table(rows, columns, height=420):
    parts = [f'<div class="mp-table-wrap" style="max-height:{height}px;">',
             '<table class="mp-table"><thead><tr>']
    for label, _ in columns:
        parts.append(f"<th>{label}</th>")
    parts.append("</tr></thead><tbody>")
    for row in rows:
        row_cls = row.get("_row_class", "") if isinstance(row, dict) else ""
        parts.append(f'<tr class="{row_cls}">')
        for _, render_fn in columns:
            parts.append(f"<td>{render_fn(row)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def sort_controls(options: dict, key: str, default_index: int = 0,
                  default_desc: bool = True):
    """Компактний рядок керування сортуванням (одна строка, малий шрифт)."""
    labels = list(options.keys())
    th = cur_theme()
    c1, c2 = st.columns([2, 2])
    with c1:
        sel = st.selectbox(t("sort_by"), labels, index=default_index,
                           key=f"sort_col_{key}")
    with c2:
        order = st.selectbox(t("sort_order_label"), [t("sort_desc"), t("sort_asc")],
                             index=0 if default_desc else 1,
                             key=f"sort_ord_{key}")
    ascending = order == t("sort_asc")
    return options[sel], ascending
