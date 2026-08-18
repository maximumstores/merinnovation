"""
18_settings.py — бізнес-налаштування в базі.

НАВІЩО: собівартість, lead time, цільовий ACOS — це параметри бізнесу,
а не коду. Тримати їх у скриптах означає, що для зміни числа потрібен
розробник і перезапуск. Тепер вони в базі й редагуються в кабінеті.

Скрипти читають їх через get_setting(). Якщо значення немає — беруть
дефолт, тому нічого не ламається.

Запуск (створити таблицю і дефолти):
    python 18_settings.py
    python 18_settings.py --show          # показати поточні
    python 18_settings.py --set cogs_ratio=0.42
"""

import os
import sys
from datetime import datetime

import psycopg2
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, ".env"), override=True)

# Дефолти + опис для інтерфейсу.
# (ключ, значення, одиниця, група, підпис, пояснення)
DEFAULTS = [
    ("cogs_ratio", 0.35, "ratio", "Юніт-економіка",
     "Собівартість, частка від ціни",
     "0.35 = собівартість 35% від ціни продажу. Головний параметр "
     "для розрахунку маржі."),
    ("referral_fee_pct", 15.0, "pct", "Юніт-економіка",
     "Реферальна комісія Amazon, %",
     "Для одягу зазвичай 15%. Використовується там, де немає "
     "фактичних даних з фінансових подій."),
    ("deal_discount_pct", 20.0, "pct", "Акції",
     "Знижка для допуску до акції, %",
     "Amazon вимагає знижку від найнижчої ціни за 30 днів. "
     "Типово 20% для Lightning Deal."),
    ("lead_time_days", 45, "days", "Постачання",
     "Строк постачання, днів",
     "Від розміщення замовлення до приймання на складі Amazon. "
     "Від цього числа залежить оцінка розривів у прогнозі."),
    ("target_coverage_days", 60, "days", "Постачання",
     "Цільове покриття, днів",
     "На скільки днів запасу орієнтуємось після приходу поставки."),
    ("safety_stock_days", 14, "days", "Постачання",
     "Страховий запас, днів",
     "Буфер понад строк постачання на випадок стрибка попиту."),
    ("target_acos_pct", 35.0, "pct", "Реклама",
     "Цільовий ACOS, %",
     "Беззбитковий рівень. Для маржі 35-40% це приблизно 35%."),
    ("velocity_drop_pct", 20.0, "pct", "Ціни",
     "Падіння швидкості при підвищенні ціни, %",
     "Оцінка за замовчуванням у калькуляторі медіани. "
     "Точніше дає тест на 7 днів."),
    ("median_window_days", 90, "days", "Ціни",
     "Вікно медіанної ціни, днів",
     "Amazon рахує медіану за 90 днів. Змінювати лише якщо "
     "правила зміняться."),
    ("recalc_buffer_days", 5, "days", "Ціни",
     "Буфер на перерахунок Amazon, днів",
     "Amazon перераховує медіану не миттєво."),
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"), connect_timeout=15)


def init_db(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS merinnovation;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS merinnovation.settings (
                key TEXT PRIMARY KEY,
                value NUMERIC,
                unit TEXT,
                grp TEXT,
                label TEXT,
                help_text TEXT,
                updated_at TIMESTAMPTZ DEFAULT now(),
                updated_by TEXT
            );
        """)
        # дефолти вставляємо лише якщо ключа ще немає — щоб не затирати
        # те, що користувач уже змінив у кабінеті
        for key, val, unit, grp, label, help_text in DEFAULTS:
            cur.execute("""
                INSERT INTO merinnovation.settings
                    (key, value, unit, grp, label, help_text, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, 'default')
                ON CONFLICT (key) DO UPDATE SET
                    unit = EXCLUDED.unit,
                    grp = EXCLUDED.grp,
                    label = EXCLUDED.label,
                    help_text = EXCLUDED.help_text
            """, (key, val, unit, grp, label, help_text))
    conn.commit()


# ==================================================================
#  API для інших скриптів
# ==================================================================

_cache = None


def get_setting(key: str, default=None, conn=None):
    """Читає налаштування з бази. Якщо його немає — повертає default,
    щоб скрипт працював і до першого запуску 18_settings.py."""
    global _cache
    if _cache is None:
        _cache = {}
        own = conn is None
        try:
            conn = conn or get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema='merinnovation' AND table_name='settings'
                """)
                if cur.fetchone()[0]:
                    cur.execute("SELECT key, value FROM merinnovation.settings")
                    _cache = {k: float(v) for k, v in cur.fetchall()
                              if v is not None}
            if own:
                conn.close()
        except Exception:
            _cache = {}
    return _cache.get(key, default)


def set_setting(key: str, value, updated_by: str = "manual", conn=None):
    own = conn is None
    conn = conn or get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE merinnovation.settings
            SET value = %s, updated_at = now(), updated_by = %s
            WHERE key = %s
        """, (value, updated_by, key))
    conn.commit()
    if own:
        conn.close()
    global _cache
    _cache = None


def run():
    conn = get_conn()
    init_db(conn)

    if "--set" in sys.argv:
        i = sys.argv.index("--set")
        if i + 1 < len(sys.argv):
            pair = sys.argv[i + 1]
            if "=" in pair:
                k, v = pair.split("=", 1)
                set_setting(k.strip(), float(v), "cli", conn)
                log(f"{k.strip()} = {v}")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT grp, key, value, unit, label, updated_by
            FROM merinnovation.settings ORDER BY grp, key
        """)
        rows = cur.fetchall()

    print()
    print("=" * 70)
    print("НАЛАШТУВАННЯ")
    print("=" * 70)
    last_grp = None
    for grp, key, val, unit, label, by in rows:
        if grp != last_grp:
            print(f"\n  {grp}")
            last_grp = grp
        suffix = {"pct": "%", "days": " дн", "ratio": ""}.get(unit, "")
        mark = "" if by == "default" else "  ←змінено"
        print(f"    {label:<42} {float(val):>8.2f}{suffix}{mark}")

    conn.close()
    print()
    print("Змінювати зручніше в кабінеті: сторінка «Налаштування».")


if __name__ == "__main__":
    run()
