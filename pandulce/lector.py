"""Lectura de la foto de una planilla con Claude (visión) -> grilla en JSON.

La clave ANTHROPIC_API_KEY sale de los secrets de Streamlit / variable de entorno.
"""
from __future__ import annotations

import base64
import io
import json
from datetime import date, timedelta

import anthropic
from PIL import Image, ImageOps

from .horas import DUDA, emparejar_nombre
from .planilla import normalizar_lectura

MODELO = "claude-opus-5-5"

INSTRUCCIONES = """Leés fotos de planillas de papel de la fábrica Pan Dulce (Córdoba, Argentina).
La planilla se titula "Registro Manual de Horas — Personal de Temporada". Arriba dice
"Semana del DD/MM/AAAA al DD/MM/AAAA · Semana N° NN del año AAAA · Mes · Sector".
La tabla tiene una fila por persona (N°, Nombre y Apellido) y, por cada día, tres columnas:
Ent (hora de entrada), Sal (hora de salida) y Firma. Ignorá las firmas.

Cómo leer:
- La foto puede estar girada o con sombras. Leé la tabla completa, fila por fila.
- Una columna por cada día que tenga encabezado impreso (a veces son solo 2 días). Devolvé la fecha
  de cada columna en formato AAAA-MM-DD, deducida del encabezado (ej. "Lun 19/10" con año 2026).
- Si una columna entera está tachada o dice FERIADO, marcala feriado=true y dejá sus celdas vacías.
- Horas: copiá lo escrito en formato HH:MM de 24 h. "800" es 08:00, "1530" es 15:30, "7.00" es 07:00.
- Códigos: "A" (o un triángulo Δ) significa ausente -> escribí "A". "LN" significa Los Nogales -> escribí "LN".
- Una raya, una firma sola o una celda vacía -> "".
- Nombres: "impreso" es el nombre impreso en la planilla. "manuscrito" es lo que esté escrito a mano en
  esa celda (una corrección del nombre o del apellido, o una persona agregada a mano en una fila vacía).
  Si una fila impresa está tachada entera, poné manuscrito "TACHADO". Incluí las filas agregadas a mano.
  Omití las filas vacías.
- Marcá duda=true en cada celda que no se lea con seguridad (tachones, números ambiguos, tinta corrida,
  sombra). Es preferible marcar de más que adivinar.
- En "notas" contá en una o dos frases cualquier cosa rara (columna tachada, sector escrito a mano, etc.).
"""

_CELDA = {
    "type": "object",
    "properties": {
        "ent": {"type": "string", "description": "HH:MM, A, LN o vacío"},
        "sal": {"type": "string", "description": "HH:MM, A, LN o vacío"},
        "duda": {"type": "boolean"},
    },
    "required": ["ent", "sal", "duda"],
    "additionalProperties": False,
}

ESQUEMA = {
    "type": "object",
    "properties": {
        "semana": {"type": "integer"},
        "sector": {"type": "string"},
        "columnas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"fecha": {"type": "string"}, "feriado": {"type": "boolean"}},
                "required": ["fecha", "feriado"],
                "additionalProperties": False,
            },
        },
        "filas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "impreso": {"type": "string"},
                    "manuscrito": {"type": "string"},
                    "celdas": {"type": "array", "items": _CELDA},
                },
                "required": ["impreso", "manuscrito", "celdas"],
                "additionalProperties": False,
            },
        },
        "notas": {"type": "string"},
    },
    "required": ["semana", "sector", "columnas", "filas", "notas"],
    "additionalProperties": False,
}


class LecturaError(Exception):
    """La foto no se pudo leer; el mensaje se muestra tal cual a la usuaria."""


def preparar_foto(datos: bytes, lado_max: int = 2000) -> bytes:
    """Endereza según el EXIF del celular, achica y comprime a JPEG (también es el respaldo que se guarda)."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(datos))).convert("RGB")
    img.thumbnail((lado_max, lado_max))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


def girar_foto(jpeg: bytes) -> bytes:
    """Gira 90° a la derecha (las fotos de WhatsApp llegan sin dato de orientación)."""
    img = Image.open(io.BytesIO(jpeg)).rotate(-90, expand=True)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


def leer_foto(jpeg: bytes, personas: list[dict], api_key: str | None = None) -> dict:
    """Devuelve una `lectura` lista para revisar (ver formato en planilla.py)."""
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    nombres = ", ".join(p["completo"] for p in personas if p["activo"])
    try:
        resp = client.beta.messages.create(
            model=MODELO,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": ESQUEMA}},
            system=INSTRUCCIONES,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": base64.standard_b64encode(jpeg).decode()}},
                    {"type": "text", "text": f"Personal de temporada actual (para ayudarte con la letra): {nombres}. "
                                             f"Hoy es {date.today():%d/%m/%Y}. Leé la planilla."},
                ],
            }],
        )
    except anthropic.AuthenticationError as e:
        raise LecturaError("La clave de la IA (ANTHROPIC_API_KEY) no es válida. Revisá los secrets de la app.") from e
    except anthropic.RateLimitError as e:
        raise LecturaError("La IA está ocupada en este momento. Probá de nuevo en un minuto.") from e
    except anthropic.APIStatusError as e:
        raise LecturaError(f"La IA respondió con un error ({e.status_code}). Probá de nuevo.") from e
    except anthropic.APIConnectionError as e:
        raise LecturaError("No hubo conexión con la IA. Revisá internet y probá de nuevo.") from e

    if resp.stop_reason == "refusal":
        raise LecturaError("La IA no pudo procesar esta foto. Cargá la planilla a mano.")
    if resp.stop_reason == "max_tokens":
        raise LecturaError("La planilla es demasiado larga para leerla de una vez. Sacá la foto de media hoja.")
    texto = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        crudo = json.loads(texto)
    except json.JSONDecodeError as e:
        raise LecturaError("La lectura volvió incompleta. Probá de nuevo.") from e
    return armar_lectura(crudo, personas)


def armar_lectura(crudo: dict, personas: list[dict]) -> dict:
    """Pasa la respuesta de la IA al formato de revisión: dudas como "?", nombres emparejados."""
    columnas = crudo.get("columnas") or []
    for c in columnas:  # fecha inválida -> se completa a mano en la revisión
        try:
            date.fromisoformat(c["fecha"])
        except (ValueError, KeyError):
            c["fecha"] = ""
    if columnas and not all(c["fecha"] for c in columnas):
        base = next((date.fromisoformat(c["fecha"]) - timedelta(days=i) for i, c in enumerate(columnas) if c["fecha"]),
                    date.today() - timedelta(days=date.today().weekday()))
        for i, c in enumerate(columnas):
            c["fecha"] = c["fecha"] or (base + timedelta(days=i)).isoformat()

    filas = []
    exactos = {p["completo"].lower(): p["id"] for p in personas}
    for f in crudo.get("filas") or []:
        imp, man = (f.get("impreso") or "").strip(), (f.get("manuscrito") or "").strip()
        celdas = []
        for c in (f.get("celdas") or [])[: len(columnas)]:
            marca = DUDA if c.get("duda") else ""
            celdas.append({"ent": (c.get("ent") or "") + (marca if c.get("ent") else ""),
                           "sal": (c.get("sal") or "") + (marca if c.get("sal") else "")})
        celdas += [{"ent": "", "sal": ""}] * (len(columnas) - len(celdas))
        if man.upper() == "TACHADO":
            filas.append({"impreso": imp, "manuscrito": "(fila tachada)", "persona_id": None,
                          "nombre_ok": False, "celdas": celdas})
            continue
        pid = emparejar_nombre(imp, man, personas)
        # se confirma solo si coincide exacto con el padrón y no hay nada escrito a mano
        ok = bool(pid) and not man and exactos.get(imp.lower()) == pid
        filas.append({"impreso": imp, "manuscrito": man, "persona_id": pid, "nombre_ok": ok, "celdas": celdas})

    lec = {"semana": crudo.get("semana") or (date.fromisoformat(columnas[0]["fecha"]).isocalendar()[1] if columnas else 0),
           "sector": crudo.get("sector") or "", "notas": crudo.get("notas") or "",
           "columnas": columnas, "filas": filas}
    normalizar_lectura(lec)
    return lec
