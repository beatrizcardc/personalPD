import pytest

from pandulce.horas import emparejar_nombre, fmt_horas, horas, horas_registro, normalizar, tipo_de, valido


@pytest.mark.parametrize("entrada,esperado", [
    ("800", "08:00"), ("1530", "15:30"), ("7.00", "07:00"), ("7:30", "07:30"), ("18", "18:00"),
    ("08:00", "08:00"), ("Δ", "A"), ("a", "A"), ("ln", "LN"), ("", ""), (None, ""),
    ("18:35?", "18:35?"), ("800?", "08:00?"), ("8h30", "08:30"),
])
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


def test_valido():
    assert valido("") and valido("07:00") and valido("A") and valido("LN")
    assert not valido("07:00?") and not valido("25:00") and not valido("xx")


def test_horas_sin_descuento_de_almuerzo():
    assert horas("07:00", "16:00") == 9
    assert horas("09:00", "18:35") == pytest.approx(9 + 35 / 60)
    assert horas("09:00", "") is None
    assert horas("18:00", "09:00") is None


def test_tipos_y_ln():
    assert tipo_de("A", "A") == "ausente"
    assert tipo_de("LN", "LN") == "LN"
    assert tipo_de("07:00", "16:00") == "trabajo"
    assert horas_registro("ausente", "07:00", "16:00") is None
    assert horas_registro("LN", "", "") is None          # LN sin horas: se ignora
    assert horas_registro("LN", "08:00", "14:00") == 6   # LN con horas: suma


PADRON = [
    {"id": 1, "nombre": "Álvaro", "apellido": "Albarracín", "alias": ["Álvaro Albornoz"]},
    {"id": 2, "nombre": "Antonella", "apellido": "De Paoli", "alias": ["Antonella Di Paoli", "Antonella Do Pazo"]},
    {"id": 3, "nombre": "Agustín", "apellido": "Torres", "alias": []},
    {"id": 4, "nombre": "Luciana", "apellido": "Arias", "alias": []},
]


@pytest.mark.parametrize("impreso,manuscrito,esperado", [
    ("Álvaro Albornoz", "Albarracín", 1),      # corrección a mano del apellido
    ("Alvaro Albornoz", "", 1),                # impreso mal, reconocido por alias
    ("Antonella Do Pazo", "De Paoli", 2),
    ("Agustin Torres", "", 3),                 # sin tilde
    ("", "Luciana Arias", 4),                  # fila agregada a mano
    ("", "Luciana Anas", 4),                   # letra difícil
    ("Persona Desconocida", "", None),
])
def test_emparejar_nombre(impreso, manuscrito, esperado):
    assert emparejar_nombre(impreso, manuscrito, PADRON) == esperado


def test_fmt_horas():
    assert fmt_horas(9.25) == "9,25"
    assert fmt_horas(None) == "—" and fmt_horas(float("nan")) == "—"
