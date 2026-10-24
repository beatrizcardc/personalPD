"""Login de una sola usuaria (Carmen).

- La contraseña NO está en el código ni en los secrets: Carmen la crea en el primer ingreso
  y se guarda como hash bcrypt en la tabla config.
- Para crearla (o recuperarla) hace falta el CODIGO_ACTIVACION de los secrets de Streamlit.
  Cada código sirve una sola vez: para un reseteo se pone un código nuevo en los secrets.
"""
from __future__ import annotations

import hashlib
import hmac
import time

import bcrypt
import streamlit as st

from . import db

MAX_INTENTOS = 5
ESPERA_SEG = 60


def _huella(codigo: str) -> str:
    return hashlib.sha256(codigo.strip().encode()).hexdigest()


def _codigo_disponible(motor, codigo_secreto: str) -> bool:
    return bool(codigo_secreto) and db.leer_config(motor, "codigo_usado") != _huella(codigo_secreto)


def _crear_clave(motor, usuario: str, codigo_secreto: str, titulo: str) -> None:
    st.subheader(titulo)
    st.caption("La contraseña se guarda cifrada. Nadie puede leerla, tampoco en el código.")
    with st.form("crear_clave"):
        codigo = st.text_input("Código de activación", type="password")
        c1 = st.text_input("Contraseña nueva (mínimo 8 caracteres)", type="password")
        c2 = st.text_input("Repetir contraseña", type="password")
        if st.form_submit_button("Crear contraseña y entrar", type="primary"):
            if not hmac.compare_digest(_huella(codigo), _huella(codigo_secreto)):
                st.error("El código de activación no es correcto.")
            elif len(c1) < 8:
                st.error("La contraseña tiene que tener al menos 8 caracteres.")
            elif c1 != c2:
                st.error("Las dos contraseñas no coinciden.")
            else:
                db.escribir_config(motor, "clave_hash", bcrypt.hashpw(c1.encode(), bcrypt.gensalt()).decode())
                db.escribir_config(motor, "codigo_usado", _huella(codigo_secreto))
                db.anotar(motor, usuario, "Creó su contraseña", "Ingreso")
                st.session_state.usuario = usuario
                st.rerun()


def pedir_login(motor, usuario: str, codigo_secreto: str) -> bool:
    """Muestra el login si hace falta. Devuelve True cuando la usuaria ya entró."""
    if st.session_state.get("usuario"):
        return True

    st.title("Pan Dulce · Personal de Temporada")
    clave_hash = db.leer_config(motor, "clave_hash")

    if not clave_hash:
        if not codigo_secreto:
            st.error("Falta CODIGO_ACTIVACION en los secrets de la app. Sin él no se puede crear la contraseña.")
            return False
        _crear_clave(motor, usuario, codigo_secreto, f"Hola {usuario}, creá tu contraseña")
        return False

    if st.session_state.get("recuperar"):
        if not _codigo_disponible(motor, codigo_secreto):
            st.warning("Para recuperar la contraseña hace falta un código de activación nuevo en los secrets de la app.")
            if st.button("Volver"):
                st.session_state.recuperar = False
                st.rerun()
            return False
        _crear_clave(motor, usuario, codigo_secreto, "Crear una contraseña nueva")
        return False

    bloqueo = st.session_state.get("bloqueado_hasta", 0)
    with st.form("login"):
        st.text_input("Usuario", value=usuario, disabled=True)
        clave = st.text_input("Contraseña", type="password")
        entrar = st.form_submit_button("Entrar", type="primary")
    if entrar:
        if time.time() < bloqueo:
            st.error(f"Demasiados intentos. Esperá {int(bloqueo - time.time())} segundos.")
        elif bcrypt.checkpw(clave.encode(), clave_hash.encode()):
            st.session_state.usuario = usuario
            st.session_state.intentos = 0
            st.rerun()
        else:
            st.session_state.intentos = st.session_state.get("intentos", 0) + 1
            if st.session_state.intentos >= MAX_INTENTOS:
                st.session_state.bloqueado_hasta = time.time() + ESPERA_SEG
                st.session_state.intentos = 0
            st.error("Contraseña incorrecta.")
    if st.button("Olvidé mi contraseña", type="tertiary"):
        st.session_state.recuperar = True
        st.rerun()
    return False


def salir() -> None:
    for k in ("usuario", "recuperar"):
        st.session_state.pop(k, None)
