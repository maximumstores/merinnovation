# -*- coding: utf-8 -*-
"""Авторизація кабінету: логін, ролі, керування користувачами.

Ролі:
    admin  — бачить усе, керує користувачами
    user   — робочі сторінки, без Алертів і технічного

Паролі зберігаються ХЕШЕМ (bcrypt), не текстом. Навіть маючи доступ до
бази, пароль відновити не можна — це важливо, бо в тій самій базі лежать
дані продажів, і компрометація одного не має відкривати інше.
"""

import os
import secrets
import string
from datetime import datetime, timedelta, timezone

import pandas as pd
import psycopg2
import streamlit as st

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False
    import hashlib

# Сторінки, доступні лише адміну
ADMIN_ONLY_PAGES = {"7_Alerts"}

SESSION_HOURS = 12


# ------------------------------------------------------------- паролі ----

def hash_password(password: str) -> str:
    if HAS_BCRYPT:
        return bcrypt.hashpw(password.encode("utf-8"),
                             bcrypt.gensalt()).decode("utf-8")
    # запасний варіант, якщо bcrypt не встановлено: salted sha256
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"sha256${salt}${h}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("sha256$"):
        _, salt, h = stored.split("$", 2)
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest() == h
    if HAS_BCRYPT:
        try:
            return bcrypt.checkpw(password.encode("utf-8"),
                                  stored.encode("utf-8"))
        except Exception:
            return False
    return False


def generate_password(length: int = 12) -> str:
    """Читабельний пароль без символів, які плутають: 0/O, 1/l/I."""
    alphabet = "".join(c for c in (string.ascii_letters + string.digits)
                       if c not in "0O1lI")
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------- БД ----

def _conn():
    from db import get_conn
    return get_conn()


def init_auth(conn=None):
    """Таблиця користувачів + перший адмін із .env."""
    conn = conn or _conn()
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS merinnovation;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS merinnovation.users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT now(),
                created_by TEXT,
                last_login TIMESTAMPTZ,
                login_count INT DEFAULT 0
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS merinnovation.login_log (
                id BIGSERIAL PRIMARY KEY,
                username TEXT,
                success BOOLEAN,
                at TIMESTAMPTZ DEFAULT now()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_login_log_at
            ON merinnovation.login_log (at DESC);
        """)
        # Журнал дій: видно, хто які сторінки відкривав і що змінював.
        # Це не стеження, а відповідь на питання "хто це зробив" —
        # коли працює кілька людей, без журналу з'ясувати неможливо.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS merinnovation.activity_log (
                id BIGSERIAL PRIMARY KEY,
                username TEXT,
                action TEXT,
                target TEXT,
                at TIMESTAMPTZ DEFAULT now()
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity_at
            ON merinnovation.activity_log (at DESC);
        """)
        # Блокнот адміна: паролі, які ЗАДАВ адмін, щоб не тримати їх
        # у голові й не скидати заново після кожного закритого вікна.
        #
        # ВАЖЛИВО: це не відновлення хешів — так не буває. Сюди пише лише
        # той пароль, який адмін щойно призначив. Щойно людина змінить його
        # сама, запис стає нечинним, і це видно в картці.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS merinnovation.password_notes (
                username TEXT PRIMARY KEY,
                password TEXT,
                set_by TEXT,
                set_at TIMESTAMPTZ DEFAULT now(),
                changed_by_user BOOLEAN DEFAULT FALSE
            );
        """)

        # Першого адміна створює create_admin.py — разовий скрипт,
        # який пише напряму в базу. Тут нічого не бутстрапимо: тримати
        # робочий пароль у конфігу застосунку означає мати другий
        # екземпляр ключа, який ніхто не ротує.
    conn.commit()


def log_action(action: str, target: str = None):
    """Записує дію поточного користувача. Викликається там, де щось
    змінюється або відкривається важлива сторінка."""
    username = st.session_state.get("auth_user")
    if not username:
        return
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO merinnovation.activity_log (username, action, target)
                VALUES (%s, %s, %s)
            """, (username, action, target))
        conn.commit()
    except Exception:
        pass


def get_user(username: str):
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT username, password_hash, full_name, role, is_active,
                   must_change_password
            FROM merinnovation.users WHERE username = %s
        """, (username.strip().lower(),))
        row = cur.fetchone()
    if not row:
        return None
    return {"username": row[0], "password_hash": row[1], "full_name": row[2],
            "role": row[3], "is_active": row[4], "must_change": row[5]}


def log_attempt(username: str, success: bool):
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO merinnovation.login_log (username, success)
                VALUES (%s, %s)
            """, (username, success))
        conn.commit()
    except Exception:
        pass


def mark_login(username: str):
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE merinnovation.users
                SET last_login = now(), login_count = COALESCE(login_count,0)+1
                WHERE username = %s
            """, (username,))
        conn.commit()
    except Exception:
        pass


def too_many_attempts(username: str) -> bool:
    """Захист від перебору: 10 невдалих спроб за 15 хвилин.

    Адміністраторів не блокуємо: власник не має замикати себе зовні
    через кілька помилок у паролі. Для звичайних акаунтів захист
    лишається — саме їх перебирають."""
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT role FROM merinnovation.users WHERE username = %s
            """, (username,))
            row = cur.fetchone()
            if row and row[0] == "admin":
                return False

            cur.execute("""
                SELECT COUNT(*) FROM merinnovation.login_log
                WHERE username = %s AND success = FALSE
                  AND at > now() - INTERVAL '15 minutes'
            """, (username,))
            return cur.fetchone()[0] >= 10
    except Exception:
        return False


# ------------------------------------------------------ користувачі ----

def list_users() -> pd.DataFrame:
    conn = _conn()
    return pd.read_sql("""
        SELECT username, full_name, role, is_active, must_change_password,
               created_at, created_by, last_login, login_count
        FROM merinnovation.users ORDER BY role, username
    """, conn)


def create_user(username, password, full_name, role, created_by,
                must_change: bool = True):
    """must_change=False — людина працює із заданим паролем, і адмін його
    знає. must_change=True — задасть свій при першому вході, і тоді пароль
    відомий тільки їй (відновити з бази неможливо, там лише хеш)."""
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO merinnovation.users
                (username, password_hash, full_name, role, created_by,
                 must_change_password)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (username.strip().lower(), hash_password(password),
              full_name, role, created_by, must_change))
    conn.commit()


def remember_password(username: str, password: str, set_by: str):
    """Зберігає пароль, який задав адмін."""
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO merinnovation.password_notes
                    (username, password, set_by, changed_by_user)
                VALUES (%s, %s, %s, FALSE)
                ON CONFLICT (username) DO UPDATE SET
                    password = EXCLUDED.password,
                    set_by = EXCLUDED.set_by,
                    set_at = now(),
                    changed_by_user = FALSE
            """, (username.strip().lower(), password, set_by))
        conn.commit()
    except Exception:
        pass


def mark_password_changed(username: str):
    """Людина змінила пароль сама — запис у блокноті більше не чинний."""
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE merinnovation.password_notes
                SET changed_by_user = TRUE
                WHERE username = %s
            """, (username.strip().lower(),))
        conn.commit()
    except Exception:
        pass


def get_password_note(username: str):
    """Повертає (пароль, дата, чи змінив користувач сам) або None."""
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT password, set_at, changed_by_user
                FROM merinnovation.password_notes WHERE username = %s
            """, (username.strip().lower(),))
            row = cur.fetchone()
        return row if row else None
    except Exception:
        return None


def set_password(username: str, password: str, force_change: bool = True):
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE merinnovation.users
            SET password_hash = %s, must_change_password = %s
            WHERE username = %s
        """, (hash_password(password), force_change, username.strip().lower()))
    conn.commit()


def change_own_password(username: str, old: str, new: str) -> tuple:
    """Зміна власного пароля — ЗІ СТАРИМ. Без цієї перевірки будь-хто,
    хто отримав доступ до відкритої сесії, міняє пароль і забирає акаунт."""
    user = get_user(username)
    if not user:
        return False, "user_missing"
    if not verify_password(old, user["password_hash"]):
        return False, "old_wrong"
    if len(new) < 8:
        return False, "too_short"
    set_password(username, new, force_change=False)
    return True, "ok"


def set_active(username: str, active: bool):
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE merinnovation.users SET is_active = %s WHERE username = %s
        """, (active, username.strip().lower()))
    conn.commit()


def set_role(username: str, role: str):
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE merinnovation.users SET role = %s WHERE username = %s
        """, (role, username.strip().lower()))
    conn.commit()


def delete_user(username: str):
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM merinnovation.users WHERE username = %s",
                    (username.strip().lower(),))
    conn.commit()


# --------------------------------------------------------------- UI ----

def _session_valid() -> bool:
    if not st.session_state.get("auth_user"):
        return False
    ts = st.session_state.get("auth_at")
    if not ts:
        return False
    return (datetime.now(timezone.utc) - ts) < timedelta(hours=SESSION_HOURS)


def _login_css():
    """На екрані входу Streamlit малює власну навігацію зі СИРИМИ іменами
    файлів (app, Stock, Users...) — наш сайдбар з'являється лише після
    авторизації. Ховаємо цей службовий вигляд, щоб чужа людина не бачила
    структуру застосунку до входу.

    Тут же дублюємо стилі кнопок і полів: inject_css() працює лише після
    авторизації, а до входу без них світла тема дає темні кнопки
    з темним текстом."""
    from db import ACCENT, cur_theme
    th = cur_theme()
    st.markdown(f"""
<style>
[data-testid="stSidebarNav"] {{ display: none !important; }}
[data-testid="stToolbar"] {{ display: none !important; }}
[data-testid="stDecoration"] {{ display: none !important; }}
[data-testid="stStatusWidget"] {{ display: none !important; }}
[data-testid="stAppDeployButton"] {{ display: none !important; }}
.stAppDeployButton, .stDeployButton {{ display: none !important; }}
[data-testid="stHeaderActionElements"] {{ display: none !important; }}
#MainMenu {{ visibility: hidden !important; }}
header[data-testid="stHeader"] {{ background: transparent !important; }}
footer {{ visibility: hidden !important; }}

.stApp {{ background: {th["bg"]} !important; }}
[data-testid="stSidebar"] {{ background: {th["sidebar"]} !important; }}
.stApp, .stApp p, .stApp span, .stApp label {{ color: {th["text"]} !important; }}

/* Поля вводу */
[data-testid="stTextInput"] input {{
    background-color: {th["card"]} !important;
    color: {th["text"]} !important;
    border-color: {th["border"]} !important;
}}

/* Неактивні кнопки: без цього на світлій темі вони темні з темним
   текстом — написи просто не читаються */
button[kind="secondary"], button[kind="secondary"] * {{
    background-color: {th["card"]} !important;
    color: {th["text"]} !important;
    border-color: {th["border"]} !important;
}}
button[kind="secondary"]:hover {{ border-color: {ACCENT} !important; }}

button[kind="secondaryFormSubmit"],
button[kind="secondaryFormSubmit"] * {{
    background-color: {th["card"]} !important;
    color: {th["text"]} !important;
    border-color: {th["border"]} !important;
}}

/* Випадні списки: виділений пункт має бути читабельним */
li[role="option"] {{
    background-color: {th["card"]} !important;
    color: {th["text"]} !important;
}}
li[role="option"] * {{ background-color: transparent !important; }}
li[role="option"]:hover,
li[role="option"][aria-selected="true"],
li[role="option"][aria-selected="true"] > * {{
    background-color: {ACCENT} !important;
    color: #ffffff !important;
}}

/* Кнопка "показати пароль" — той самий фон, що й поле */
[data-testid="stTextInput"] button,
[data-testid="stTextInput"] button * {{
    background-color: {th["card"]} !important;
    color: {th["muted"]} !important;
    border-color: {th["border"]} !important;
}}
[data-testid="stTextInput"] button:hover * {{ color: {th["text"]} !important; }}
[data-testid="stTextInput"] svg {{ fill: {th["muted"]} !important; }}
</style>
""", unsafe_allow_html=True)


def _login_sidebar():
    """Логотип і вибір мови/теми — доступні ще до входу."""
    from db import (LANGS, LANG_LABELS, _logo_b64, ACCENT)

    if "lang" not in st.session_state:
        st.session_state["lang"] = "uk"
    if "theme" not in st.session_state:
        st.session_state["theme"] = "dark"

    with st.sidebar:
        b64 = _logo_b64()
        if b64:
            from db import cur_theme
            th = cur_theme()
            st.markdown(
                f'<div style="padding: 8px 0 20px 0; text-align:center;">'
                f'<img src="data:image/png;base64,{b64}" '
                f'style="max-width:170px;width:100%;'
                f'filter:{th["logo_filter"]};" /></div>',
                unsafe_allow_html=True)

        cols = st.columns(3)
        for i, code in enumerate(LANGS):
            with cols[i]:
                if st.button(LANG_LABELS[code], key=f"login_lang_{code}",
                             type=("primary"
                                   if st.session_state["lang"] == code
                                   else "secondary"),
                             use_container_width=True):
                    st.session_state["lang"] = code
                    st.rerun()

        tc1, tc2 = st.columns(2)
        with tc1:
            if st.button("Dark", key="login_th_dark", use_container_width=True,
                         icon=":material/dark_mode:",
                         type=("primary"
                               if st.session_state["theme"] == "dark"
                               else "secondary")):
                st.session_state["theme"] = "dark"
                st.rerun()
        with tc2:
            if st.button("Light", key="login_th_light", use_container_width=True,
                         icon=":material/light_mode:",
                         type=("primary"
                               if st.session_state["theme"] == "light"
                               else "secondary")):
                st.session_state["theme"] = "light"
                st.rerun()


def _has_any_user() -> bool:
    try:
        conn = _conn()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM merinnovation.users")
            return cur.fetchone()[0] > 0
    except Exception:
        return True


def _no_users_hint():
    """Без цього порожня база дає екран входу, у який неможливо увійти —
    і незрозуміло чому."""
    _login_css()
    st.markdown("### Кабінет ще не налаштовано")
    st.info(
        "У базі немає жодного користувача. Створи адміністратора "
        "на сервері:\n\n"
        "```\npython create_admin.py\n```\n\n"
        "Скрипт покаже логін і пароль. Далі користувачами керуєш "
        "у кабінеті на сторінці «Користувачі»."
    )


def _login_form():
    from db import ACCENT, cur_theme, t
    _login_css()
    _login_sidebar()
    th = cur_theme()

    st.markdown(
        f'<div style="max-width:420px;margin:8vh auto 0 auto;">'
        f'<div style="color:{th["text"]};font-size:30px;font-weight:700;'
        f'letter-spacing:-0.02em;margin-bottom:6px;">Merinnovation</div>'
        f'<div style="color:{th["muted"]};font-size:14px;margin-bottom:24px;">'
        f'{t("login_subtitle")}</div></div>', unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        with st.form("login_form"):
            username = st.text_input(t("login_user"), key="li_user")
            password = st.text_input(t("login_pass"), type="password",
                                     key="li_pass")
            submitted = st.form_submit_button(t("login_btn"), type="primary",
                                              use_container_width=True)

        if submitted:
            u = (username or "").strip().lower()
            if not u or not password:
                st.error(t("login_empty"))
                return

            if too_many_attempts(u):
                st.error(t("login_throttled"))
                return

            user = get_user(u)
            if not user or not verify_password(password, user["password_hash"]):
                log_attempt(u, False)
                # навмисно не уточнюємо, що саме невірне — щоб не давати
                # підказку про існування логіна
                st.error(t("login_bad"))
                return

            if not user["is_active"]:
                log_attempt(u, False)
                st.error(t("login_disabled"))
                return

            log_attempt(u, True)
            mark_login(u)
            st.session_state["auth_user"] = user["username"]
            st.session_state["auth_role"] = user["role"]
            st.session_state["auth_name"] = user["full_name"] or user["username"]
            st.session_state["auth_at"] = datetime.now(timezone.utc)
            st.session_state["auth_must_change"] = user["must_change"]
            st.rerun()


def _change_password_form():
    from db import cur_theme, t
    _login_css()
    _login_sidebar()
    th = cur_theme()
    st.warning(t("pw_required"))

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        with st.form("chpass"):
            p1 = st.text_input(t("pw_new"), type="password")
            p2 = st.text_input(t("pw_repeat"), type="password")
            ok = st.form_submit_button(t("pw_save"), type="primary",
                                       use_container_width=True)
        if ok:
            if len(p1) < 8:
                st.error(t("pw_short"))
            elif p1 != p2:
                st.error(t("pw_mismatch"))
            else:
                set_password(st.session_state["auth_user"], p1,
                             force_change=False)
                mark_password_changed(st.session_state["auth_user"])
                st.session_state["auth_must_change"] = False
                st.success(t("pw_changed"))
                st.rerun()


def require_auth(page: str = None):
    """Ставиться на початку КОЖНОЇ сторінки, одразу після set_page_config.

    Повертає dict користувача або зупиняє рендер сторінки."""
    # Ініціалізація не має мовчки валити сторінку: якщо таблиця вже є,
    # а якийсь ALTER не пройшов, користувач має побачити причину,
    # а не порожній екран.
    try:
        init_auth()
    except Exception as e:
        st.warning(f"Ініціалізація авторизації з помилкою: {e}")

    if not _session_valid():
        if not _has_any_user():
            _no_users_hint()
            st.stop()
        _login_form()
        st.stop()

    if st.session_state.get("auth_must_change"):
        _change_password_form()
        st.stop()

    role = st.session_state.get("auth_role", "user")

    # сторінки тільки для адміна
    from db import t
    if page and page in ADMIN_ONLY_PAGES and role != "admin":
        st.error(t("admin_only"))
        st.stop()

    # фіксуємо відкриття сторінки — але не частіше разу на сесію,
    # інакше кожен rerun Streamlit писав би новий рядок
    if page:
        seen = st.session_state.setdefault("_pages_seen", set())
        if page not in seen:
            seen.add(page)
            try:
                log_action("page_open", page)
            except Exception:
                pass

    return {
        "username": st.session_state["auth_user"],
        "role": role,
        "name": st.session_state.get("auth_name"),
    }


def sidebar_user_block():
    """Блок користувача в сайдбарі: хто увійшов і кнопка виходу."""
    from db import cur_theme, t
    th = cur_theme()
    user = st.session_state.get("auth_name") or st.session_state.get("auth_user")
    role = st.session_state.get("auth_role", "user")
    if not user:
        return

    with st.sidebar:
        st.markdown("---")
        st.markdown(
            f'<div style="color:{th["muted"]};font-size:11px;'
            f'letter-spacing:.1em;text-transform:uppercase;">'
            f'{t("role_admin") if role == "admin" else t("role_user")}</div>'
            f'<div style="color:{th["text"]};font-size:14px;'
            f'font-weight:600;margin-bottom:8px;">{user}</div>',
            unsafe_allow_html=True)
        if st.button(t("logout"), key="logout_btn", use_container_width=True,
                     icon=":material/logout:"):
            for k in ("auth_user", "auth_role", "auth_name", "auth_at",
                      "auth_must_change"):
                st.session_state.pop(k, None)
            st.rerun()


def is_admin() -> bool:
    return st.session_state.get("auth_role") == "admin"
