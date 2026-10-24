import json

import pandas as pd
import sqlalchemy as sa
import streamlit as st

from pandulce import db, lector, planilla, ui
from pandulce.horas import DUDA, CODIGOS, etiqueta_dia, fmt_horas, horas, normalizar, valido

IGNORAR = "— Ignorar esta fila —"
SECTORES = ["Planta", "Los Nogales (LN)"]

st.title("Revisar planilla")

m = ui.motor()
lista = db.listar_planillas(m)
if not lista:
    st.info("No hay planillas. Subí una foto en «Subir fotos».")
    st.stop()

pendientes = [p for p in lista if p["estado"] == "pendiente"]
elegida = st.session_state.get("revisar_id") or (pendientes[0]["id"] if pendientes else lista[0]["id"])
ids = [p["id"] for p in lista]
pid = st.selectbox(
    "Planilla", ids, index=ids.index(elegida) if elegida in ids else 0,
    format_func=lambda i: next(f"Semana {p['semana']} · {p['archivo'] or ''} · "
                               f"{'para revisar' if p['estado'] == 'pendiente' else 'cargada'}" for p in lista if p["id"] == i))
st.session_state.revisar_id = pid

pl = db.leer_planilla(m, pid)
lec = pl["lectura"]
cols = lec.get("columnas", [])
etiquetas = [etiqueta_dia(planilla.fecha_col(c)) for c in cols]
bloqueada = pl["estado"] == "confirmada"
ver_key = f"ver_{pid}"
ver = st.session_state.setdefault(ver_key, 0)

todas = ui.personas()
por_id = {p["id"]: p["completo"] for p in todas}
por_nombre = {p["completo"]: p["id"] for p in todas}


def guardar(nueva: dict, **extra) -> None:
    db.guardar_lectura(m, pid, nueva, **extra)
    st.session_state[ver_key] += 1  # reinicia las grillas con los datos guardados
    st.rerun()


if bloqueada:
    st.success("Esta planilla ya está cargada. Para corregir un día usá «Registros».")

izq, der = st.columns([2, 3], gap="medium")

with izq:
    if pl["foto"]:
        st.image(pl["foto"], caption="Foto original (tocala para agrandar)", use_container_width=True)
        if st.button("Girar foto", icon=":material/rotate_right:"):
            with m.begin() as c:
                c.execute(db.planillas.update().where(db.planillas.c.id == pid).values(foto=lector.girar_foto(pl["foto"])))
            st.rerun()
    else:
        st.caption("Planilla cargada a mano, sin foto.")
    if lec.get("notas"):
        st.info(f"Nota de la lectura: {lec['notas']}")

with der:
    # ---------- datos de la planilla ----------
    c1, c2, c3 = st.columns(3)
    semana = c1.number_input("Semana N°", value=int(lec.get("semana") or 0), step=1, disabled=bloqueada)
    sector_act = pl["sector"] or "Planta"
    opciones_sector = SECTORES if sector_act in SECTORES else SECTORES + [sector_act]
    sector = c2.selectbox("Sector", opciones_sector, index=opciones_sector.index(sector_act), disabled=bloqueada)
    primera = c3.date_input("Primer día de la planilla", planilla.fecha_col(cols[0]) if cols else None,
                            format="DD/MM/YYYY", disabled=bloqueada or not cols)
    feriados = st.multiselect("Feriados (no se cargan)", etiquetas,
                              [e for e, c in zip(etiquetas, cols) if c.get("feriado")], disabled=bloqueada,
                              placeholder="Ninguno")

    if not bloqueada:
        nueva = json.loads(json.dumps(lec))
        if cols and primera != planilla.fecha_col(cols[0]):
            corr = primera - planilla.fecha_col(cols[0])
            for c in nueva["columnas"]:
                c["fecha"] = (planilla.fecha_col(c) + corr).isoformat()
        for e, c in zip(etiquetas, nueva["columnas"]):
            c["feriado"] = e in feriados
        nueva["semana"] = int(semana)
        nueva["sector"] = sector
        if nueva != lec or sector != sector_act:
            guardar(nueva, semana=int(semana), sector=sector)

    # ---------- nombres ----------
    st.subheader("Nombres")
    st.caption("Lo escrito a mano manda sobre lo impreso. Revisá cada nombre y marcá ✓ cuando esté bien.")
    opciones = sorted(p["completo"] for p in todas if p["activo"]) + [IGNORAR]
    df_nom = pd.DataFrame([{
        "N°": i + 1, "Impreso": f.get("impreso", ""), "A mano": f.get("manuscrito", ""),
        "Persona": por_id.get(f.get("persona_id")) or (IGNORAR if f.get("nombre_ok") else None),
        "✓": bool(f.get("nombre_ok")),
    } for i, f in enumerate(lec.get("filas", []))])
    if df_nom.empty:
        st.warning("La lectura no encontró filas.")
    else:
        ed_nom = st.data_editor(
            df_nom, hide_index=True, use_container_width=True, disabled=bloqueada or ["N°", "Impreso", "A mano"],
            column_config={"Persona": st.column_config.SelectboxColumn(options=opciones, width="medium"),
                           "✓": st.column_config.CheckboxColumn("✓ confirmado")},
            key=f"nom_{pid}_{ver}")
        if not bloqueada:
            nueva = json.loads(json.dumps(lec))
            for f, (_, r), (_, r0) in zip(nueva["filas"], ed_nom.iterrows(), df_nom.iterrows()):
                elegido = r["Persona"] if isinstance(r["Persona"], str) else None
                f["persona_id"] = por_nombre.get(elegido) if elegido and elegido != IGNORAR else None
                cambio = elegido != r0["Persona"]
                f["nombre_ok"] = bool(elegido) and (cambio or bool(r["✓"]))
            if nueva != lec:
                guardar(nueva)

    if not bloqueada:
        with st.expander("¿Falta alguien en la lista? Agregar persona"):
            with st.form(f"nueva_persona_{pid}", clear_on_submit=True):
                a, b = st.columns(2)
                nom = a.text_input("Nombre")
                ape = b.text_input("Apellido")
                obs = st.text_input("Observación (obligatorio)", placeholder="Ej.: agregada a mano en la planilla de la semana 43")
                if st.form_submit_button("Agregar"):
                    if not (nom.strip() and ape.strip() and obs.strip()):
                        st.error("Completá nombre, apellido y observación.")
                    elif f"{nom.strip()} {ape.strip()}" in por_nombre:
                        st.error("Esa persona ya existe.")
                    else:
                        db.guardar_persona(m, {"nombre": nom.strip(), "apellido": ape.strip(), "alias": [],
                                               "activo": True, "desde": planilla.fecha_col(cols[0]) if cols else None})
                        db.anotar(m, ui.usuario(), "Agregó persona", f"{nom.strip()} {ape.strip()}", despues="activa", obs=obs)
                        st.rerun()

    # ---------- horas ----------
    st.subheader("Horas")
    st.caption("Formato 24 h (07:00). **A** = ausente · **LN** = Los Nogales. "
               "Un **?** al final marca una lectura dudosa: borralo cuando la confirmes o corregí el valor.")

    def nombre_fila(f):
        return por_id.get(f.get("persona_id")) or f.get("manuscrito") or f.get("impreso") or "?"

    filas_vista, col_dias = [], []
    for e in etiquetas:
        col_dias += [f"{e} Ent", f"{e} Sal"]
    for f in lec.get("filas", []):
        fila = {"Persona": nombre_fila(f)}
        total = 0.0
        for j, e in enumerate(etiquetas):
            c = f["celdas"][j]
            fila[f"{e} Ent"], fila[f"{e} Sal"] = c.get("ent", ""), c.get("sal", "")
            if not cols[j].get("feriado"):
                total += horas(c.get("ent"), c.get("sal")) or 0
        fila["Horas"] = fmt_horas(total or None)
        filas_vista.append(fila)
    df_h = pd.DataFrame(filas_vista)

    if not df_h.empty:
        cerradas = [f"{e} {k}" for e, c in zip(etiquetas, cols) if c.get("feriado") for k in ("Ent", "Sal")]
        ed_h = st.data_editor(
            df_h, hide_index=True, use_container_width=True,
            disabled=True if bloqueada else ["Persona", "Horas", *cerradas],
            column_config={c: st.column_config.TextColumn(c, width="small") for c in col_dias},
            key=f"horas_{pid}_{ver}")
        if not bloqueada:
            nueva = json.loads(json.dumps(lec))
            for f, (_, r) in zip(nueva["filas"], ed_h.iterrows()):
                for j, e in enumerate(etiquetas):
                    for k, sufijo in (("ent", "Ent"), ("sal", "Sal")):
                        v = r[f"{e} {sufijo}"]
                        f["celdas"][j][k] = normalizar("" if pd.isna(v) else str(v))
            planilla.normalizar_lectura(nueva)
            if nueva != lec:
                guardar(nueva)

        # vista de control con colores
        def pintar(v):
            v = str(v)
            if v.endswith(DUDA):
                return "background-color:#f7edcf;color:#8a6d1e"
            if v and not valido(v):
                return "background-color:#fbede2;color:#b4531a;font-weight:700"
            if v in CODIGOS:
                return "color:#b4531a;font-weight:700" if v == "A" else "color:#24466e;font-weight:700"
            return ""
        with st.expander("Vista de control con colores", expanded=not bloqueada):
            st.dataframe(df_h.style.map(pintar, subset=col_dias), hide_index=True, use_container_width=True)
            st.caption("Amarillo: para confirmar · Naranja: no se entiende como hora")

    # ---------- cargar ----------
    if not bloqueada:
        prob = planilla.problemas(lec)
        st.subheader("Cargar")
        if prob["nombres"]:
            st.warning(f"{len(prob['nombres'])} nombre(s) sin confirmar: " + "; ".join(prob["nombres"]))
        if prob["dudas"]:
            st.warning(f"{len(prob['dudas'])} lectura(s) dudosa(s): " + "; ".join(prob["dudas"][:12])
                       + (" …" if len(prob["dudas"]) > 12 else ""))
        if prob["invalidos"]:
            st.error("Valores que no se entienden: " + "; ".join(prob["invalidos"]))
        if prob["faltantes"]:
            st.info("Se puede cargar igual, quedan como «sin salida» o «sin entrada»: " + "; ".join(prob["faltantes"]))

        if prob["dudas"] and st.button(f"Confirmar las {len(prob['dudas'])} lecturas dudosas tal como están"):
            nueva = json.loads(json.dumps(lec))
            planilla.confirmar_dudas(nueva)
            guardar(nueva)

        obs = st.text_area("Observaciones de la planilla", value=pl.get("observaciones") or "",
                           placeholder="Ej.: Mario sin salida el jueves, preguntar al encargado")
        b1, b2 = st.columns([1, 1])
        if b1.button("Cargar planilla", type="primary", disabled=planilla.bloqueantes(prob) > 0,
                     help="Primero confirmá nombres y lecturas dudosas" if planilla.bloqueantes(prob) else None):
            cargados, salteados = planilla.confirmar(m, pid, ui.usuario(), obs.strip())
            st.session_state[ver_key] += 1
            st.toast(f"Semana {lec.get('semana')} cargada: {cargados} registros"
                     + (f" ({salteados} días ya estaban cargados y no se tocaron)" if salteados else ""))
            st.rerun()
        with b2.popover("Descartar planilla"):
            st.write("Se borra la foto y la lectura. Los registros ya cargados no se tocan.")
            if st.button("Sí, descartar", type="primary"):
                with m.begin() as c:
                    c.execute(sa.delete(db.planillas).where(db.planillas.c.id == pid))
                    db.anotar(c, ui.usuario(), "Descartó planilla", f"Semana {lec.get('semana')}", antes=pl["archivo"] or "")
                st.session_state.revisar_id = None
                st.rerun()
