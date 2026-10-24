from datetime import date

import sqlalchemy as sa

from pandulce import db, planilla
from pandulce.lector import armar_lectura

# Lectura cruda como la devolvería la IA para dos filas de la semana 43 (19/10 al 23/10/2026)
CRUDO = {
    "semana": 43, "sector": "", "notas": "",
    "columnas": [{"fecha": f"2026-10-{d}", "feriado": False} for d in (19, 20, 21, 22, 23)],
    "filas": [
        {"impreso": "Álvaro Albornoz", "manuscrito": "Albarracín", "celdas": [
            {"ent": "A", "sal": "A", "duda": False}, {"ent": "09:00", "sal": "18:35", "duda": False},
            {"ent": "09:00", "sal": "17:40", "duda": False}, {"ent": "09:00", "sal": "18:25", "duda": False},
            {"ent": "09:00", "sal": "19:00", "duda": False}]},
        {"impreso": "Mario Oviedo", "manuscrito": "", "celdas": [
            {"ent": "LN", "sal": "LN", "duda": False}, {"ent": "A", "sal": "", "duda": False},
            {"ent": "A", "sal": "A", "duda": False}, {"ent": "7:00", "sal": "", "duda": True},
            {"ent": "07:00", "sal": "18", "duda": True}]},
    ],
}


def motor_prueba():
    return db.crear_motor("sqlite://")


def test_armar_lectura_y_problemas():
    m = motor_prueba()
    lec = armar_lectura(CRUDO, db.listar_personas(m))
    alvaro, mario = lec["filas"]
    assert alvaro["persona_id"] and not alvaro["nombre_ok"]   # escrito a mano: a confirmar
    assert mario["nombre_ok"]                                  # coincide exacto con el padrón
    assert mario["celdas"][1] == {"ent": "A", "sal": "A"}      # "A" en una mitad vale el día
    assert mario["celdas"][4] == {"ent": "07:00?", "sal": "18:00?"}
    p = planilla.problemas(lec)
    assert len(p["nombres"]) == 1 and len(p["dudas"]) == 3 and planilla.bloqueantes(p) == 4
    assert p["faltantes"] == ["Fila 2 · 22/10: falta salida"]


def test_confirmar_carga_registros_y_aprende_alias():
    m = motor_prueba()
    lec = armar_lectura(CRUDO, db.listar_personas(m))
    lec["filas"][0]["nombre_ok"] = True
    planilla.confirmar_dudas(lec)
    assert planilla.bloqueantes(planilla.problemas(lec)) == 0
    with m.begin() as c:
        pid = c.execute(db.planillas.insert().values(semana=43, sector="Planta", estado="pendiente",
                                                     lectura="{}")).inserted_primary_key[0]
    db.guardar_lectura(m, pid, lec)

    cargados, salteados = planilla.confirmar(m, pid, "Carmen", "prueba")
    assert (cargados, salteados) == (10, 0)
    with m.connect() as c:
        regs = c.execute(sa.select(db.registros)).mappings().all()
    tipos = sorted(r["tipo"] for r in regs)
    assert tipos.count("ausente") == 3 and tipos.count("LN") == 1 and tipos.count("trabajo") == 6
    ln = next(r for r in regs if r["tipo"] == "LN")
    assert ln["ent"] == "" and ln["fecha"] == date(2026, 10, 19)

    # cargar dos veces la misma planilla no duplica días
    db.guardar_lectura(m, pid, lec, estado="pendiente")
    assert planilla.confirmar(m, pid, "Carmen", "") == (0, 10)

    alvaro = next(p for p in db.listar_personas(m) if p["apellido"] == "Albarracín")
    assert "Álvaro Albornoz" in alvaro["alias"]


def test_planilla_de_los_nogales_marca_horas_como_ln():
    lec = {"columnas": [{"fecha": "2026-10-19", "feriado": False}, {"fecha": "2026-10-20", "feriado": True}],
           "filas": [{"persona_id": 1, "nombre_ok": True,
                      "celdas": [{"ent": "08:00", "sal": "14:00"}, {"ent": "08:00", "sal": "14:00"}]}]}
    regs = planilla.registros_de_lectura(lec, "Los Nogales (LN)")
    assert len(regs) == 1  # el feriado no se carga
    assert regs[0]["tipo"] == "LN" and regs[0]["ent"] == "08:00"
