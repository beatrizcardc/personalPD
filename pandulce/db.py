"""Base de datos: Postgres (Supabase) en producción, SQLite en la compu para probar.

La URL sale de DATABASE_URL (secrets de Streamlit o variable de entorno).
Las tablas se crean solas la primera vez.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa

meta = sa.MetaData()

personas = sa.Table(
    "personas", meta,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("nombre", sa.String(80), nullable=False),
    sa.Column("apellido", sa.String(80), nullable=False),
    sa.Column("alias", sa.Text, nullable=False, default="[]"),  # lista JSON de otras formas del nombre
    sa.Column("activo", sa.Boolean, nullable=False, default=True),
    sa.Column("desde", sa.Date),
    sa.Column("creado", sa.DateTime, default=datetime.now),
)

planillas = sa.Table(
    "planillas", meta,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("semana", sa.Integer),
    sa.Column("sector", sa.String(60), default="Planta"),
    sa.Column("estado", sa.String(20), nullable=False, default="pendiente"),  # pendiente | confirmada
    sa.Column("archivo", sa.String(200)),
    sa.Column("foto", sa.LargeBinary),  # JPEG comprimido, respaldo de la planilla en papel
    sa.Column("lectura", sa.Text),  # JSON con la grilla leída y corregida
    sa.Column("observaciones", sa.Text, default=""),
    sa.Column("creado", sa.DateTime, default=datetime.now),
    sa.Column("confirmado", sa.DateTime),
)

registros = sa.Table(
    "registros", meta,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("persona_id", sa.Integer, sa.ForeignKey("personas.id"), nullable=False),
    sa.Column("fecha", sa.Date, nullable=False),
    sa.Column("tipo", sa.String(10), nullable=False, default="trabajo"),  # trabajo | ausente | LN
    sa.Column("ent", sa.String(5), default=""),
    sa.Column("sal", sa.String(5), default=""),
    sa.Column("planilla_id", sa.Integer, sa.ForeignKey("planillas.id")),
    sa.Column("origen", sa.String(30), default="Manual"),
    sa.Column("obs", sa.Text, default=""),
    sa.Column("creado", sa.DateTime, default=datetime.now),
    sa.Column("modificado", sa.DateTime, default=datetime.now, onupdate=datetime.now),
)

historial = sa.Table(
    "historial", meta,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("ts", sa.DateTime, nullable=False, default=datetime.now),
    sa.Column("usuario", sa.String(60), nullable=False),
    sa.Column("accion", sa.String(60), nullable=False),
    sa.Column("objeto", sa.String(200), default=""),
    sa.Column("antes", sa.Text, default=""),
    sa.Column("despues", sa.Text, default=""),
    sa.Column("obs", sa.Text, default=""),
)

config = sa.Table(
    "config", meta,
    sa.Column("clave", sa.String(60), primary_key=True),
    sa.Column("valor", sa.Text),
)

# Padrón inicial (planillas de octubre 2026). Se carga solo si la tabla está vacía.
PERSONAS_INICIALES = [
    ("Álvaro", "Albarracín", ["Álvaro Albornoz"], True, date(2026, 10, 1)),
    ("Antonella", "De Paoli", ["Antonella Di Paoli", "Antonella Do Pazo"], True, date(2026, 10, 1)),
    ("Axel", "Ferreira", [], True, date(2026, 10, 1)),
    ("Bárbara", "Duarte", [], True, date(2026, 10, 1)),
    ("Elías", "Ullo", [], True, date(2026, 10, 1)),
    ("Esteban", "González", [], True, date(2026, 10, 1)),
    ("Guadalupe", "Cabral", [], True, date(2026, 10, 1)),
    ("Lucas", "Martínez", [], True, date(2026, 10, 1)),
    ("Magali", "Bustos", [], True, date(2026, 10, 1)),
    ("Mario", "Oviedo", [], True, date(2026, 10, 1)),
    ("Agustín", "Torres", [], True, date(2026, 10, 1)),
    ("Álvaro", "Navarro", [], False, date(2026, 10, 1)),
    ("Luciana", "Arias", [], True, date(2026, 10, 19)),
]


def crear_motor(url: str | None = None) -> sa.Engine:
    url = url or os.environ.get("DATABASE_URL") or "sqlite:///pandulce_local.db"
    if url.startswith("postgres://"):  # Supabase a veces da este prefijo
        url = "postgresql://" + url[len("postgres://"):]
    motor = sa.create_engine(url, pool_pre_ping=True)
    meta.create_all(motor)
    with motor.begin() as c:
        if c.execute(sa.select(sa.func.count()).select_from(personas)).scalar() == 0:
            c.execute(personas.insert(), [
                {"nombre": n, "apellido": a, "alias": json.dumps(al, ensure_ascii=False), "activo": ac, "desde": d}
                for n, a, al, ac, d in PERSONAS_INICIALES
            ])
    return motor


# ---------------- personas ----------------

def _persona(row) -> dict:
    d = dict(row._mapping)
    d["alias"] = json.loads(d.get("alias") or "[]")
    d["completo"] = f"{d['nombre']} {d['apellido']}"
    return d


def listar_personas(motor, solo_activas: bool = False) -> list[dict]:
    q = sa.select(personas).order_by(personas.c.nombre, personas.c.apellido)
    if solo_activas:
        q = q.where(personas.c.activo.is_(True))
    with motor.connect() as c:
        return [_persona(r) for r in c.execute(q)]


def guardar_persona(motor, datos: dict, pid: int | None = None) -> int:
    fila = {**datos, "alias": json.dumps(datos.get("alias", []), ensure_ascii=False)}
    with motor.begin() as c:
        if pid is None:
            return c.execute(personas.insert().values(**fila)).inserted_primary_key[0]
        c.execute(personas.update().where(personas.c.id == pid).values(**fila))
        return pid


def agregar_alias(motor, pid: int, texto: str) -> None:
    """Aprende una forma nueva de escribir el nombre (la próxima planilla la reconoce sola)."""
    texto = (texto or "").strip()
    if not texto:
        return
    with motor.begin() as c:
        row = c.execute(sa.select(personas).where(personas.c.id == pid)).first()
        p = _persona(row)
        if texto.lower() in {p["completo"].lower(), *[a.lower() for a in p["alias"]]}:
            return
        c.execute(personas.update().where(personas.c.id == pid)
                  .values(alias=json.dumps(p["alias"] + [texto], ensure_ascii=False)))


# ---------------- historial ----------------

def anotar(motor_o_conexion, usuario: str, accion: str, objeto: str = "", antes: str = "", despues: str = "", obs: str = "") -> None:
    fila = dict(usuario=usuario, accion=accion, objeto=objeto, antes=antes, despues=despues, obs=obs, ts=datetime.now())
    if isinstance(motor_o_conexion, sa.Engine):
        with motor_o_conexion.begin() as c:
            c.execute(historial.insert().values(**fila))
    else:
        motor_o_conexion.execute(historial.insert().values(**fila))


# ---------------- config ----------------

def leer_config(motor, clave: str) -> str | None:
    with motor.connect() as c:
        return c.execute(sa.select(config.c.valor).where(config.c.clave == clave)).scalar()


def escribir_config(motor, clave: str, valor: str) -> None:
    with motor.begin() as c:
        if c.execute(sa.select(config.c.clave).where(config.c.clave == clave)).first():
            c.execute(config.update().where(config.c.clave == clave).values(valor=valor))
        else:
            c.execute(config.insert().values(clave=clave, valor=valor))


# ---------------- planillas ----------------

def leer_planilla(motor, pid: int) -> dict[str, Any] | None:
    with motor.connect() as c:
        row = c.execute(sa.select(planillas).where(planillas.c.id == pid)).first()
    if not row:
        return None
    d = dict(row._mapping)
    d["lectura"] = json.loads(d["lectura"] or "{}")
    return d


def listar_planillas(motor) -> list[dict]:
    cols = [planillas.c.id, planillas.c.semana, planillas.c.sector, planillas.c.estado,
            planillas.c.archivo, planillas.c.creado, planillas.c.lectura]
    with motor.connect() as c:
        filas = c.execute(sa.select(*cols).order_by(planillas.c.creado.desc())).all()
    out = []
    for r in filas:
        d = dict(r._mapping)
        lec = json.loads(d.pop("lectura") or "{}")
        cols_ = lec.get("columnas") or []
        d["desde"] = cols_[0]["fecha"] if cols_ else None
        d["hasta"] = cols_[-1]["fecha"] if cols_ else None
        out.append(d)
    return out


def guardar_lectura(motor, pid: int, lectura: dict, **extra) -> None:
    with motor.begin() as c:
        c.execute(planillas.update().where(planillas.c.id == pid)
                  .values(lectura=json.dumps(lectura, ensure_ascii=False), **extra))
