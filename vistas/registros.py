from datetime import date

import sqlalchemy as sa
import streamlit as st

from pandulce import db, ui
from pandulce.horas import TIPOS, es_hora, etiqueta_dia, fmt_horas, horas

st.title("Registros")
st.caption("Un registro es un día de una persona. Crear, editar o eliminar pide una observación que queda en «Cambios».")

m = ui.motor()
df = ui.registros_df()
vista = ui.filtros(df, "reg", con_tipo=True)

tabla = vista.assign(
    Fecha=[f"{etiqueta_dia(f)}/{f.year}" for f in vista["fecha"]],
    Tipo=vista["tipo"].map(TIPOS),
    Horas=[fmt_horas(h) for h in vista["horas"]],
)[["id", "Fecha", "persona", "Tipo", "ent", "sal", "Horas", "origen", "obs"]].rename(
    columns={"persona": "Nombre y apellido", "ent": "Ent", "sal": "Sal", "origen": "Origen", "obs": "Observaciones"})

st.caption(f"{len(tabla)} registros. Tocá una fila para editarla o eliminarla.")
sel = st.dataframe(tabla, hide_index=True, use_container_width=True, on_select="rerun",
                   selection_mode="single-row", column_config={"id": None}, key="tabla_reg")
filas_sel = sel.selection.rows if sel else []
actual = vista.iloc[filas_sel[0]].to_dict() if filas_sel else None

activas = [p["completo"] for p in ui.personas(solo_activas=True)]
por_nombre = {p["completo"]: p["id"] for p in ui.personas()}
tipos_inv = {v: k for k, v in TIPOS.items()}


def describir(r: dict) -> str:
    if r["tipo"] == "ausente":
        return "Ausente"
    pref = "LN " if r["tipo"] == "LN" else ""
    return pref + (f"{r['ent'] or '?'}–{r['sal'] or '?'}" if (r["ent"] or r["sal"]) else "sin horas")


def formulario(modo: str, r: dict | None) -> None:
    r = r or {"persona": activas[0] if activas else "", "fecha": date.today(), "tipo": "trabajo", "ent": "", "sal": ""}
    nombres = activas if r["persona"] in activas else [r["persona"], *activas]
    with st.form(f"form_{modo}", clear_on_submit=modo == "crear"):
        a, b, c = st.columns(3)
        persona = a.selectbox("Nombre y apellido", nombres, index=nombres.index(r["persona"]) if r["persona"] in nombres else 0)
        fecha = b.date_input("Fecha", r["fecha"], format="DD/MM/YYYY")
        tipo = c.selectbox("Tipo", list(TIPOS.values()), index=list(TIPOS).index(r["tipo"]))
        d, e = st.columns(2)
        ent = d.text_input("Entrada (HH:MM)", r["ent"], placeholder="07:00")
        sal = e.text_input("Salida (HH:MM)", r["sal"], placeholder="16:00")
        st.caption("Ausente no suma horas. Los Nogales suma solo si tiene horario.")
        obs = st.text_area("Observación del cambio (obligatorio)",
                           placeholder="Ej.: La foto decía 17:30, corregido según el cuaderno del sector")
        ok = st.form_submit_button("Guardar", type="primary")
    if not ok:
        return
    t = tipos_inv[tipo]
    ent, sal = (ent.strip(), sal.strip()) if t != "ausente" else ("", "")
    errores = []
    if not obs.strip():
        errores.append("Escribí una observación: queda en el historial de cambios.")
    for nombre, v in (("entrada", ent), ("salida", sal)):
        if v and not es_hora(v):
            errores.append(f"La {nombre} tiene que ser HH:MM, por ejemplo 07:30.")
    if ent and sal and es_hora(ent) and es_hora(sal) and horas(ent, sal) is None:
        errores.append("La salida tiene que ser posterior a la entrada.")
    if t == "trabajo" and not (ent or sal):
        errores.append("Completá al menos la entrada o la salida.")
    if errores:
        for x in errores:
            st.error(x)
        return
    nuevo = {"persona_id": por_nombre[persona], "fecha": fecha, "tipo": t, "ent": ent, "sal": sal}
    objeto = f"{persona} · {fecha:%d/%m/%Y}"
    with m.begin() as cx:
        if modo == "crear":
            cx.execute(db.registros.insert().values(**nuevo, origen="Manual", obs=obs.strip()))
            db.anotar(cx, ui.usuario(), "Creó registro", objeto, despues=describir(nuevo), obs=obs.strip())
        else:
            cx.execute(db.registros.update().where(db.registros.c.id == int(r["id"])).values(**nuevo, obs=obs.strip()))
            db.anotar(cx, ui.usuario(), "Editó registro", objeto, antes=describir(r), despues=describir(nuevo), obs=obs.strip())
    st.toast("Guardado")
    st.rerun()


if actual:
    st.subheader(f"{actual['persona']} · {actual['fecha']:%d/%m/%Y}")
    t1, t2 = st.tabs(["Editar", "Eliminar"])
    with t1:
        formulario("editar", actual)
    with t2:
        with st.form("form_eliminar"):
            motivo = st.text_area("Motivo de la eliminación (obligatorio)", placeholder="Ej.: registro duplicado")
            if st.form_submit_button("Eliminar registro", type="primary"):
                if not motivo.strip():
                    st.error("Escribí el motivo: queda en el historial de cambios.")
                else:
                    with m.begin() as cx:
                        cx.execute(sa.delete(db.registros).where(db.registros.c.id == int(actual["id"])))
                        db.anotar(cx, ui.usuario(), "Eliminó registro", f"{actual['persona']} · {actual['fecha']:%d/%m/%Y}",
                                  antes=describir(actual), obs=motivo.strip())
                    st.toast("Registro eliminado")
                    st.rerun()

with st.expander("Nuevo registro", expanded=not actual and df.empty):
    formulario("crear", None)
