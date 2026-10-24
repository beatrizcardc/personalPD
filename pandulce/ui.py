"""Piezas compartidas por las pantallas: conexión, secrets y filtros."""
from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import sqlalchemy as sa
import streamlit as st

from . import db
from .horas import TIPOS, horas_registro, semana_iso


def secreto(clave: str, defecto: str = "") -> str:
    try:
        if clave in st.secrets:
            return str(st.secrets[clave])
    except Exception:  # sin secrets.toml (por ejemplo, en la compu)
        pass
    return os.environ.get(clave, defecto)


@st.cache_resource
def motor() -> sa.Engine:
    return db.crear_motor(secreto("DATABASE_URL") or None)


def usuario() -> str:
    return st.session_state.get("usuario", "")


def personas(solo_activas: bool = False) -> list[dict]:
    return db.listar_personas(motor(), solo_activas)


def registros_df() -> pd.DataFrame:
    """Todos los registros con nombre, horas y semana calculados."""
    q = (sa.select(db.registros, (db.personas.c.nombre + " " + db.personas.c.apellido).label("persona"))
         .join(db.personas, db.personas.c.id == db.registros.c.persona_id))
    with motor().connect() as c:
        df = pd.DataFrame(c.execute(q).mappings().all())
    if df.empty:
        return pd.DataFrame(columns=["id", "persona_id", "persona", "fecha", "tipo", "ent", "sal",
                                     "horas", "semana", "origen", "obs"])
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    df["ent"] = df["ent"].fillna("")
    df["sal"] = df["sal"].fillna("")
    df["horas"] = [horas_registro(t, e, s) for t, e, s in zip(df["tipo"], df["ent"], df["sal"])]
    df["semana"] = [semana_iso(f) for f in df["fecha"]]
    return df.sort_values(["fecha", "persona"])


def filtros(df: pd.DataFrame, clave: str, con_tipo: bool = False) -> pd.DataFrame:
    """Filtros de persona, período (día, semana, mes, rango) y tipo. Devuelve el df filtrado."""
    nombres = sorted(df["persona"].unique()) if not df.empty else []
    c1, c2, c3 = st.columns([2, 2, 3])
    persona = c1.selectbox("Persona", ["Todas"] + nombres, key=f"{clave}_per")
    periodo = c2.selectbox("Período", ["Todo", "Un día", "Una semana", "Un mes", "Entre fechas"], key=f"{clave}_periodo")
    hoy = date.today()
    desde = hasta = None
    with c3:
        if periodo == "Un día":
            desde = hasta = st.date_input("Día", hoy, format="DD/MM/YYYY", key=f"{clave}_dia")
        elif periodo == "Una semana":
            semanas = sorted(df["semana"].unique(), reverse=True) if not df.empty else [semana_iso(hoy)]
            sem = st.selectbox("Semana N°", semanas, key=f"{clave}_sem")
            fechas = df.loc[df["semana"] == sem, "fecha"] if not df.empty else []
            ref = min(fechas) if len(fechas) else hoy
            desde = ref - timedelta(days=ref.weekday())
            hasta = desde + timedelta(days=6)
        elif periodo == "Un mes":
            meses = sorted({(f.year, f.month) for f in df["fecha"]}, reverse=True) if not df.empty else [(hoy.year, hoy.month)]
            a, m = st.selectbox("Mes", meses, format_func=lambda am: f"{am[1]:02d}/{am[0]}", key=f"{clave}_mes")
            desde = date(a, m, 1)
            hasta = (date(a + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)
        elif periodo == "Entre fechas":
            r = st.date_input("Desde / hasta", (hoy - timedelta(days=30), hoy), format="DD/MM/YYYY", key=f"{clave}_rango")
            if isinstance(r, tuple) and len(r) == 2:
                desde, hasta = r
    tipo = None
    if con_tipo:
        tipo = st.radio("Tipo", ["Todos", *TIPOS.values()], horizontal=True, key=f"{clave}_tipo")
    out = df
    if persona != "Todas":
        out = out[out["persona"] == persona]
    if desde:
        out = out[(out["fecha"] >= desde) & (out["fecha"] <= hasta)]
    if tipo and tipo != "Todos":
        out = out[out["tipo"] == {v: k for k, v in TIPOS.items()}[tipo]]
    return out
