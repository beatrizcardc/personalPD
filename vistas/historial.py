import pandas as pd
import sqlalchemy as sa
import streamlit as st

from pandulce import db, ui

st.title("Historial de cambios")
st.caption("Quién cambió qué, cuándo, el valor anterior y el motivo. No se puede borrar ni editar.")

with ui.motor().connect() as c:
    filas = c.execute(sa.select(db.historial).order_by(db.historial.c.ts.desc()).limit(2000)).mappings().all()

if not filas:
    st.info("Todavía no hay cambios.")
    st.stop()

df = pd.DataFrame(filas)
buscar = st.text_input("Buscar (nombre, acción, motivo…)")
if buscar:
    b = buscar.lower()
    df = df[df.apply(lambda r: b in " ".join(str(v) for v in r.values).lower(), axis=1)]

st.dataframe(
    df.rename(columns={"ts": "Cuándo", "usuario": "Quién", "accion": "Acción", "objeto": "Sobre",
                       "antes": "Antes", "despues": "Después", "obs": "Observación"})
      [["Cuándo", "Quién", "Acción", "Sobre", "Antes", "Después", "Observación"]],
    hide_index=True, use_container_width=True,
    column_config={"Cuándo": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")})
