"""Lógica de una planilla leída: qué falta revisar y cómo se convierte en registros.

Formato de `lectura` (se guarda como JSON en planillas.lectura):
{
  "semana": 43, "sector": "Planta", "notas": "...",
  "columnas": [{"fecha": "2026-10-19", "feriado": false}, ...],
  "filas": [{"impreso": "Álvaro Albornoz", "manuscrito": "Albarracín",
             "persona_id": 1, "nombre_ok": false,
             "celdas": [{"ent": "A", "sal": "A"}, {"ent": "09:00", "sal": "18:35?"}, ...]}]
}
Una celda que termina en "?" es una lectura dudosa que hay que confirmar.
`persona_id` None con `nombre_ok` True significa "ignorar esta fila".
"""
from __future__ import annotations

from datetime import date, datetime

import sqlalchemy as sa

from . import db
from .horas import DUDA, normalizar, tipo_de, valido


def fecha_col(col: dict) -> date:
    return date.fromisoformat(col["fecha"])


def problemas(lec: dict) -> dict[str, list[str]]:
    """Lo que impide cargar (nombres, dudas, inválidos) y lo que solo se avisa (faltantes)."""
    out = {"nombres": [], "dudas": [], "invalidos": [], "faltantes": []}
    cols = lec.get("columnas", [])
    for i, f in enumerate(lec.get("filas", []), start=1):
        quien = f"Fila {i}"
        if not f.get("nombre_ok"):
            out["nombres"].append(f"{quien}: {f.get('manuscrito') or f.get('impreso') or 'sin nombre'}")
        if f.get("persona_id") is None and f.get("nombre_ok"):
            continue  # fila ignorada
        for j, c in enumerate(f.get("celdas", [])):
            if j >= len(cols) or cols[j].get("feriado"):
                continue
            dia = cols[j]["fecha"][8:10] + "/" + cols[j]["fecha"][5:7]
            for k in ("ent", "sal"):
                v = c.get(k, "")
                if v.endswith(DUDA):
                    out["dudas"].append(f"{quien} · {dia} {k}: {v[:-1]}")
                elif not valido(v):
                    out["invalidos"].append(f"{quien} · {dia} {k}: «{v}»")
            if bool(c.get("ent")) != bool(c.get("sal")):
                out["faltantes"].append(f"{quien} · {dia}: falta {'salida' if c.get('ent') else 'entrada'}")
    return out


def bloqueantes(p: dict[str, list[str]]) -> int:
    return len(p["nombres"]) + len(p["dudas"]) + len(p["invalidos"])


def confirmar_dudas(lec: dict) -> int:
    """Quita la marca "?" de todas las celdas que ya son válidas. Devuelve cuántas confirmó."""
    n = 0
    for f in lec.get("filas", []):
        for c in f.get("celdas", []):
            for k in ("ent", "sal"):
                v = c.get(k, "")
                if v.endswith(DUDA) and valido(v[:-1]):
                    c[k] = v[:-1]
                    n += 1
    return n


def normalizar_lectura(lec: dict) -> None:
    for f in lec.get("filas", []):
        for c in f.get("celdas", []):
            for k in ("ent", "sal"):
                c[k] = normalizar(c.get(k, ""))
            # "A" o "LN" escrito en una sola mitad vale para el día entero
            if c["ent"].rstrip(DUDA) in ("A", "LN") and not c["sal"]:
                c["sal"] = c["ent"]
            elif c["sal"].rstrip(DUDA) in ("A", "LN") and not c["ent"]:
                c["ent"] = c["sal"]


def registros_de_lectura(lec: dict, sector: str) -> list[dict]:
    """Un registro por persona y día con algo anotado. Feriados y filas ignoradas no cargan."""
    out = []
    cols = lec.get("columnas", [])
    es_ln = (sector or "").startswith("Los Nogales")
    for f in lec.get("filas", []):
        if f.get("persona_id") is None:
            continue
        for j, c in enumerate(f.get("celdas", [])):
            if j >= len(cols) or cols[j].get("feriado"):
                continue
            ent, sal = c.get("ent", ""), c.get("sal", "")
            if not ent and not sal:
                continue
            t = tipo_de(ent, sal)
            con_horas = t == "trabajo"
            if con_horas and es_ln:
                t = "LN"  # planilla del sector Los Nogales: sus horas son LN
            out.append({"persona_id": f["persona_id"], "fecha": fecha_col(cols[j]), "tipo": t,
                        "ent": ent if con_horas else "", "sal": sal if con_horas else ""})
    return out


def confirmar(motor, pid: int, usuario: str, obs: str) -> tuple[int, int]:
    """Carga la planilla. Devuelve (registros cargados, días que ya existían y se saltearon)."""
    pl = db.leer_planilla(motor, pid)
    lec, sector = pl["lectura"], pl["sector"] or "Planta"
    nuevos = registros_de_lectura(lec, sector)
    cargados = salteados = 0
    with motor.begin() as c:
        for r in nuevos:
            ya = c.execute(sa.select(db.registros.c.id).where(
                db.registros.c.persona_id == r["persona_id"], db.registros.c.fecha == r["fecha"])).first()
            if ya:
                salteados += 1
                continue
            c.execute(db.registros.insert().values(**r, planilla_id=pid, origen=f"Sem. {pl['semana']}", obs=""))
            cargados += 1
        c.execute(db.planillas.update().where(db.planillas.c.id == pid)
                  .values(estado="confirmada", confirmado=datetime.now(), observaciones=obs))
        cols = lec.get("columnas", [])
        rango = f"{fecha_col(cols[0]):%d/%m} al {fecha_col(cols[-1]):%d/%m/%Y}" if cols else ""
        db.anotar(c, usuario, "Confirmó planilla", f"Semana {pl['semana']} · {rango}",
                  despues=f"{cargados} registros cargados" + (f", {salteados} ya existían" if salteados else ""),
                  obs=obs or "—")
    # aprender cómo aparece escrito cada nombre
    for f in lec.get("filas", []):
        if f.get("persona_id"):
            for texto in (f.get("impreso"), f.get("manuscrito")):
                if texto and len(texto.split()) >= 2:
                    db.agregar_alias(motor, f["persona_id"], texto)
    return cargados, salteados
