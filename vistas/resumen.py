import pandas as pd
import streamlit as st

from pandulce import ui
from pandulce.horas import TIPOS, etiqueta_dia, fmt_horas

st.title("Horas por persona")
st.caption("Suma de (salida − entrada) de cada día, sin descontar almuerzo. "
           "Los días en Los Nogales suman solo si tienen horario anotado.")

df = ui.registros_df()
vista = ui.filtros(df, "res")

if vista.empty:
    st.info("No hay registros en este período.")
    st.stop()

con_h = vista[vista["horas"].notna()]
planta = con_h[con_h["tipo"] == "trabajo"]
ln = con_h[con_h["tipo"] == "LN"]
sin_salida = vista[(vista["tipo"] == "trabajo") & vista["horas"].isna()]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Horas totales", fmt_horas(con_h["horas"].sum()))
c2.metric("De esas, Los Nogales", fmt_horas(ln["horas"].sum()))
c3.metric("Ausencias", int((vista["tipo"] == "ausente").sum()))
c4.metric("Días sin entrada o salida", len(sin_salida))

modo = st.segmented_control("Ver", ["Total por persona", "Por semana (para pagar)"], default="Total por persona")

if modo == "Por semana (para pagar)":
    tab = con_h.pivot_table(index="persona", columns="semana", values="horas", aggfunc="sum", fill_value=0)
    tab.columns = [f"Sem. {c}" for c in tab.columns]
    tab["Total"] = tab.sum(axis=1)
    tab_ln = ln.pivot_table(index="persona", columns="semana", values="horas", aggfunc="sum", fill_value=0)
    tab_ln.columns = [f"LN sem. {c}" for c in tab_ln.columns]
    tab = tab.join(tab_ln, how="left").fillna(0).sort_values("Total", ascending=False)
    tab.loc["TOTAL"] = tab.sum()
    tab.index.name = "Nombre y apellido"
    st.dataframe(tab.round(2), use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(format="%.2f") for c in tab.columns})
    st.caption("Las columnas «LN sem.» muestran cuántas de las horas de esa semana fueron en Los Nogales.")
    exportar = tab.round(2).reset_index()
else:
    g = vista.groupby("persona")
    res = pd.DataFrame({
        "Días trabajados": planta.groupby("persona")["horas"].count(),
        "Horas planta": planta.groupby("persona")["horas"].sum(),
        "Horas LN": ln.groupby("persona")["horas"].sum(),
        "Ausencias": vista[vista["tipo"] == "ausente"].groupby("persona").size(),
        "Días LN": vista[vista["tipo"] == "LN"].groupby("persona").size(),
        "Sin entrada/salida": sin_salida.groupby("persona").size(),
    }, index=g.size().index).fillna(0)
    res["Total horas"] = res["Horas planta"] + res["Horas LN"]
    res = res.sort_values("Total horas", ascending=False)
    res.index.name = "Nombre y apellido"
    st.dataframe(
        res, use_container_width=True,
        column_config={
            "Total horas": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=float(res["Total horas"].max() or 1)),
            "Horas planta": st.column_config.NumberColumn(format="%.2f"),
            "Horas LN": st.column_config.NumberColumn(format="%.2f"),
            **{c: st.column_config.NumberColumn(format="%d") for c in ["Días trabajados", "Ausencias", "Días LN", "Sin entrada/salida"]},
        })
    exportar = res.round(2).reset_index()

    persona = st.selectbox("Ver el detalle de", ["—"] + list(res.index))
    if persona != "—":
        det = vista[vista["persona"] == persona]
        st.dataframe(pd.DataFrame({
            "Día": [f"{etiqueta_dia(f)}/{f.year}" for f in det["fecha"]],
            "Tipo": det["tipo"].map(TIPOS), "Ent": det["ent"], "Sal": det["sal"],
            "Horas": [fmt_horas(h) for h in det["horas"]], "Observaciones": det["obs"],
        }), hide_index=True, use_container_width=True)

st.download_button("Descargar esta tabla (CSV para Excel)",
                   exportar.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                   file_name="horas_temporada.csv", mime="text/csv")
