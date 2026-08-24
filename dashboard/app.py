# -*- coding: utf-8 -*-
"""Merinnovation Dashboard — точка входу.

Уся змістовна частина «Огляду» переїхала в pages/0_Overview.py.

ЧОМУ ТАК. Головний файл Streamlit живе за КОРЕНЕВОЮ адресою застосунку.
Перехід на неї (st.page_link("app.py")) перезавантажує застосунок цілком,
session_state гине разом з авторизацією — і користувач бачить порожній
екран замість сторінки. У звичайних сторінок із pages/ адреси виду
/Overview, /Stock, і такої проблеми немає.

Тому тут лишається тільки авторизація і переадресація.
"""

import streamlit as st

import auth

st.set_page_config(layout="wide", page_title="Merinnovation", page_icon="🐑")

auth.require_auth("app")

# Користувач авторизований — ведемо на змістовну сторінку.
st.switch_page("pages/0_Overview.py")
