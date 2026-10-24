"""Reglas de horas: normalizar lo escrito a mano, calcular horas, reconocer nombres.

Todo acá es Python puro (sin Streamlit ni base de datos) para poder testearlo.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import date

AUSENTE = "A"
LOS_NOGALES = "LN"
CODIGOS = {AUSENTE, LOS_NOGALES}
DUDA = "?"  # una celda que termina en "?" está para confirmar

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
TIPOS = {"trabajo": "Trabajó", "ausente": "Ausente", "LN": "Los Nogales"}


def normalizar(valor: str | None) -> str:
    """Lleva lo que se lee en la planilla al formato del sistema.

    "800" -> "08:00", "7.30" -> "07:30", "18" -> "18:00", "Δ" -> "A", "ln" -> "LN".
    Conserva la marca de duda ("?") al final si la tenía.
    """
    if valor is None:
        return ""
    v = str(valor).strip()
    duda = v.endswith(DUDA)
    v = v.rstrip(DUDA).strip().upper()
    if v in {"Δ", "∆", "AUS", "AUSENTE"}:
        v = AUSENTE
    v = re.sub(r"[.,hH]", ":", v).replace(" ", "")
    if re.fullmatch(r"\d{3,4}", v):
        v = v.zfill(4)
        v = f"{v[:2]}:{v[2:]}"
    elif re.fullmatch(r"\d{1,2}", v):
        v = f"{int(v):02d}:00"
    elif re.fullmatch(r"\d:\d{2}", v):
        v = "0" + v
    return v + (DUDA if duda and v else "")


def es_hora(v: str | None) -> bool:
    if not v or not re.fullmatch(r"\d{2}:\d{2}", v):
        return False
    h, m = map(int, v.split(":"))
    return h < 24 and m < 60


def valido(v: str | None) -> bool:
    """Vacío, una hora HH:MM o un código (A, LN). Una celda con "?" todavía no es válida."""
    return not v or es_hora(v) or v in CODIGOS


def a_minutos(v: str) -> int:
    h, m = map(int, v.split(":"))
    return h * 60 + m


def horas(ent: str | None, sal: str | None) -> float | None:
    """Salida menos entrada, en horas. Sin descuento de almuerzo."""
    if not (es_hora(ent) and es_hora(sal)):
        return None
    dif = a_minutos(sal) - a_minutos(ent)
    return dif / 60 if dif > 0 else None


def tipo_de(ent: str, sal: str) -> str:
    if AUSENTE in (ent, sal):
        return "ausente"
    if LOS_NOGALES in (ent, sal):
        return "LN"
    return "trabajo"


def horas_registro(tipo: str, ent: str | None, sal: str | None) -> float | None:
    """Ausente nunca suma. LN suma solo si tiene horario anotado."""
    if tipo == "ausente":
        return None
    return horas(ent, sal)


def semana_iso(f: date) -> int:
    return f.isocalendar()[1]


def fmt_horas(h: float | None) -> str:
    if h is None or h != h:  # None o NaN (pandas)
        return "—"
    return f"{h:.2f}".replace(".", ",")


def etiqueta_dia(f: date) -> str:
    return f"{DIAS[f.weekday()]} {f:%d/%m}"


# ---------------- nombres ----------------

def _clave(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def emparejar_nombre(impreso: str, manuscrito: str, personas: list[dict]) -> int | None:
    """Busca a qué persona corresponde una fila. Lo escrito a mano manda sobre lo impreso.

    `personas`: dicts con id, nombre, apellido, alias (lista). El manuscrito puede ser solo
    el apellido ("Albarracín" escrito al lado de "Álvaro Albornoz").
    """
    candidatos: dict[str, int] = {}
    for p in personas:
        candidatos[_clave(f"{p['nombre']} {p['apellido']}")] = p["id"]
        for a in p.get("alias") or []:
            candidatos.setdefault(_clave(a), p["id"])

    nombre_imp = _clave(impreso).split(" ")[0] if impreso else ""
    for texto in [manuscrito, f"{nombre_imp} {_clave(manuscrito)}" if manuscrito else "", impreso]:
        k = _clave(texto)
        if not k:
            continue
        if k in candidatos:
            return candidatos[k]
        parecido = difflib.get_close_matches(k, candidatos.keys(), n=1, cutoff=0.82)
        if parecido:
            return candidatos[parecido[0]]
    # solo apellido a mano: si coincide con un único apellido
    if manuscrito:
        k = _clave(manuscrito)
        ids = {p["id"] for p in personas if _clave(p["apellido"]) == k}
        if len(ids) == 1:
            return ids.pop()
    return None
