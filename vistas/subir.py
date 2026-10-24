from datetime import date, timedelta

import streamlit as st

from pandulce import db, lector, ui

st.title("Subir fotos de planillas")
st.caption("Sacá la foto de frente y con buena luz. Cada foto es una semana. "
           "El sistema la lee y la deja lista para revisar.")

api_key = ui.secreto("ANTHROPIC_API_KEY")
fotos = st.file_uploader("Fotos de las planillas", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)

if fotos and st.button(f"Leer {len(fotos)} foto(s)", type="primary", disabled=not api_key):
    padron = ui.personas()
    for f in fotos:
        with st.status(f"Leyendo {f.name}…", expanded=False) as estado:
            jpeg = lector.preparar_foto(f.getvalue())
            try:
                lec = lector.leer_foto(jpeg, padron, api_key)
            except lector.LecturaError as e:
                estado.update(label=f"{f.name}: {e}", state="error")
                continue
            with ui.motor().begin() as c:
                pid = c.execute(db.planillas.insert().values(
                    semana=lec["semana"], sector=lec["sector"] or "Planta", estado="pendiente",
                    archivo=f.name, foto=jpeg, lectura="{}")).inserted_primary_key[0]
            db.guardar_lectura(ui.motor(), pid, lec)
            db.anotar(ui.motor(), ui.usuario(), "Subió foto", f"Semana {lec['semana']}", despues=f.name)
            estado.update(label=f"{f.name}: semana {lec['semana']} lista para revisar", state="complete")
    st.session_state.revisar_id = None
if not api_key:
    st.warning("Falta ANTHROPIC_API_KEY en los secrets: las fotos no se pueden leer solas. "
               "Mientras tanto podés cargar una planilla a mano (abajo).")

with st.expander("Cargar una planilla a mano (sin foto)"):
    lunes = st.date_input("Lunes de la semana", date.today() - timedelta(days=date.today().weekday()), format="DD/MM/YYYY")
    sector = st.selectbox("Sector", ["Planta", "Los Nogales (LN)"])
    if st.button("Crear planilla vacía"):
        activas = ui.personas(solo_activas=True)
        lec = {"semana": lunes.isocalendar()[1], "sector": sector, "notas": "Cargada a mano",
               "columnas": [{"fecha": (lunes + timedelta(days=i)).isoformat(), "feriado": False} for i in range(5)],
               "filas": [{"impreso": p["completo"], "manuscrito": "", "persona_id": p["id"], "nombre_ok": True,
                          "celdas": [{"ent": "", "sal": ""} for _ in range(5)]} for p in activas]}
        with ui.motor().begin() as c:
            pid = c.execute(db.planillas.insert().values(semana=lec["semana"], sector=sector, estado="pendiente",
                                                         archivo="(a mano)", lectura="{}")).inserted_primary_key[0]
        db.guardar_lectura(ui.motor(), pid, lec)
        st.session_state.revisar_id = pid
        st.switch_page("vistas/revisar.py")

st.subheader("Planillas")
lista = db.listar_planillas(ui.motor())
if not lista:
    st.info("Todavía no hay planillas. Subí la primera foto arriba.")
for p in lista:
    c1, c2, c3 = st.columns([4, 2, 1])
    rango = f"{p['desde'][8:]}/{p['desde'][5:7]} al {p['hasta'][8:]}/{p['hasta'][5:7]}" if p["desde"] else ""
    c1.markdown(f"**Semana {p['semana']}** · {rango} · {p['sector'] or ''}  \n"
                f"<small>{p['archivo'] or ''}</small>", unsafe_allow_html=True)
    c2.markdown(":green-badge[Cargada]" if p["estado"] == "confirmada" else ":orange-badge[Para revisar]")
    if c3.button("Abrir", key=f"abrir_{p['id']}"):
        st.session_state.revisar_id = p["id"]
        st.switch_page("vistas/revisar.py")
