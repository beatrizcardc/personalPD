from datetime import date

import pandas as pd
import streamlit as st

from pandulce import db, ui

st.title("Personas de temporada")
st.caption("Los nombres que el sistema reconoce en las planillas. Excluir a alguien lo saca de las "
           "planillas nuevas pero conserva sus horas pasadas. «También aparece como» sirve para "
           "reconocer nombres mal impresos o escritos de otra forma.")

m = ui.motor()
todas = ui.personas()
df = ui.registros_df()
horas_tot = df.groupby("persona")["horas"].sum() if not df.empty else pd.Series(dtype=float)

tabla = pd.DataFrame([{
    "id": p["id"], "Nombre y apellido": p["completo"], "También aparece como": " · ".join(p["alias"]),
    "Desde": p["desde"], "Estado": "Activa" if p["activo"] else "Excluida",
    "Horas cargadas": round(float(horas_tot.get(p["completo"], 0) or 0), 2),
} for p in sorted(todas, key=lambda p: (not p["activo"], p["completo"]))])

sel = st.dataframe(tabla, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row",
                   column_config={"id": None, "Desde": st.column_config.DateColumn(format="DD/MM/YYYY")}, key="tabla_per")
filas = sel.selection.rows if sel else []
actual = next(p for p in todas if p["id"] == int(tabla.iloc[filas[0]]["id"])) if filas else None


def form_persona(p: dict | None) -> None:
    nueva = p is None
    with st.form("form_persona_" + ("nueva" if nueva else str(p["id"])), clear_on_submit=nueva):
        a, b = st.columns(2)
        nombre = a.text_input("Nombre", "" if nueva else p["nombre"])
        apellido = b.text_input("Apellido", "" if nueva else p["apellido"])
        alias = st.text_input("También aparece como (separado por coma)", "" if nueva else ", ".join(p["alias"]),
                              placeholder="Ej.: Álvaro Albornoz")
        desde = st.date_input("Desde", date.today() if nueva else p["desde"], format="DD/MM/YYYY")
        obs = st.text_area("Observación (obligatorio)",
                           placeholder="Ej.: ingresa a la temporada" if nueva else "Ej.: apellido corregido según DNI")
        ok = st.form_submit_button("Guardar", type="primary")
    if not ok:
        return
    nombre, apellido = nombre.strip(), apellido.strip()
    completo = f"{nombre} {apellido}"
    if not (nombre and apellido):
        st.error("Completá nombre y apellido.")
    elif not obs.strip():
        st.error("Escribí una observación: queda en el historial de cambios.")
    elif any(x["completo"].lower() == completo.lower() and (nueva or x["id"] != p["id"]) for x in todas):
        st.error("Ya existe una persona con ese nombre y apellido.")
    else:
        lista_alias = [x.strip() for x in alias.split(",") if x.strip()]
        if not nueva and p["completo"] != completo and p["completo"] not in lista_alias:
            lista_alias.append(p["completo"])  # el nombre viejo sigue sirviendo para reconocer planillas
        datos = {"nombre": nombre, "apellido": apellido, "alias": lista_alias, "desde": desde}
        if nueva:
            db.guardar_persona(m, {**datos, "activo": True})
            db.anotar(m, ui.usuario(), "Agregó persona", completo, despues="activa", obs=obs.strip())
        else:
            db.guardar_persona(m, datos, p["id"])
            db.anotar(m, ui.usuario(), "Editó persona", completo, antes=p["completo"], despues=completo, obs=obs.strip())
        st.toast("Guardado")
        st.rerun()


if actual:
    st.subheader(actual["completo"])
    t1, t2 = st.tabs(["Editar", "Reactivar" if not actual["activo"] else "Excluir"])
    with t1:
        form_persona(actual)
    with t2:
        with st.form("form_estado"):
            st.write("Vuelve a aparecer en las planillas nuevas." if not actual["activo"]
                     else "Deja de aparecer en las planillas nuevas. Sus horas cargadas se conservan.")
            motivo = st.text_area("Motivo (obligatorio)")
            if st.form_submit_button("Reactivar" if not actual["activo"] else "Excluir", type="primary"):
                if not motivo.strip():
                    st.error("Escribí el motivo: queda en el historial.")
                else:
                    activo = not actual["activo"]
                    db.guardar_persona(m, {"activo": activo, "alias": actual["alias"]}, actual["id"])
                    db.anotar(m, ui.usuario(), "Reactivó persona" if activo else "Excluyó persona", actual["completo"],
                              antes="excluida" if activo else "activa", despues="activa" if activo else "excluida",
                              obs=motivo.strip())
                    st.toast("Listo")
                    st.rerun()

with st.expander("Agregar persona", expanded=False):
    form_persona(None)
