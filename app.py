"""Pan Dulce · Planillas de Personal de Temporada.

Correr en la compu:  streamlit run app.py
"""
import streamlit as st

from pandulce import auth, ui

st.set_page_config(page_title="Pan Dulce · Temporada", page_icon="🥐", layout="wide")

if not auth.pedir_login(ui.motor(), ui.secreto("USUARIO", "Carmen"), ui.secreto("CODIGO_ACTIVACION")):
    st.stop()

paginas = [
    st.Page("vistas/subir.py", title="Subir fotos", icon=":material/photo_camera:", default=True),
    st.Page("vistas/revisar.py", title="Revisar", icon=":material/fact_check:"),
    st.Page("vistas/registros.py", title="Registros", icon=":material/table_rows:"),
    st.Page("vistas/resumen.py", title="Horas por persona", icon=":material/schedule:"),
    st.Page("vistas/personas.py", title="Personas", icon=":material/group:"),
    st.Page("vistas/historial.py", title="Cambios", icon=":material/history:"),
]
nav = st.navigation(paginas)

with st.sidebar:
    st.markdown(f"**Pan Dulce** · {ui.usuario()}")
    if st.button("Salir", icon=":material/logout:"):
        auth.salir()
        st.rerun()

nav.run()
