# personalPD · Planillas de Personal de Temporada (Pan Dulce)

App en Streamlit para digitalizar las planillas en papel del personal de temporada:

1. **Subir fotos**: Carmen sube la foto de la planilla y la IA (Claude) lee nombres, horas y códigos.
2. **Revisar**: foto al lado de la grilla. Lo escrito a mano manda sobre lo impreso; lo dudoso queda marcado con `?` para confirmar o corregir.
3. **Registros**: un día por persona. Crear, editar y eliminar, siempre con observación obligatoria.
4. **Horas por persona**: total y por semana (para pagar), con filtros por persona, día, semana, mes o rango. Descarga CSV para Excel.
5. **Personas**: alta, edición, exclusión y reactivación del padrón.
6. **Cambios**: historial de todo lo que se hizo, con el valor anterior, el nuevo y el motivo.

## Reglas

| Regla | Cómo funciona |
|---|---|
| Horas del día | salida − entrada, **sin descontar almuerzo** |
| `A` (o triángulo Δ) | Ausente: no suma |
| `LN` | Los Nogales: suma solo si tiene horario anotado; si solo dice "LN", se ignora. Se ve aparte en la vista por semana |
| Planilla del sector "Los Nogales (LN)" | todas sus horas cuentan como LN |
| Feriado | la columna no se carga |
| Día sin salida | se puede cargar igual y queda marcado como «sin salida» |
| Nombres | cada persona tiene alias ("Álvaro Albornoz" = Álvaro Albarracín). Al cargar una planilla, el sistema aprende las formas nuevas |
| Misma planilla cargada dos veces | los días que ya existen no se duplican |

## Publicarla (Streamlit Community Cloud + Supabase)

### 1. Base de datos (Supabase, gratis)
1. Entrar a [supabase.com](https://supabase.com) → **New project** (región São Paulo). Anotar la contraseña de la base.
2. **Connect** (arriba) → **Session pooler** → copiar la URI. Tiene esta forma:
   `postgresql://postgres.xxxx:CONTRASEÑA@aws-0-sa-east-1.pooler.supabase.com:5432/postgres`
   Hay que usar el *pooler*: la conexión directa no funciona desde Streamlit Cloud.
3. Las tablas se crean solas la primera vez que abre la app.

### 2. Clave de la IA
En [console.anthropic.com](https://console.anthropic.com) → **API Keys** → crear una clave. Cada foto cuesta unos centavos de dólar.

### 3. La app (Streamlit Community Cloud, gratis)
1. Entrar a [share.streamlit.io](https://share.streamlit.io) con la cuenta de GitHub.
2. **Create app** → repo `beatrizcardc/personalPD`, rama `main`, archivo `app.py`.
3. **Advanced settings → Secrets**: pegar el contenido de `.streamlit/secrets.toml.example` con los valores reales:
   `DATABASE_URL`, `ANTHROPIC_API_KEY`, `USUARIO = "Carmen"` y un `CODIGO_ACTIVACION` largo inventado.
4. **Deploy**. Cada push a `main` actualiza la app sola.
5. Opcional, recomendado: en **Share** dejar la app visible solo para el email de Carmen.

### 4. Primer ingreso de Carmen
Pasale el link y el `CODIGO_ACTIVACION` por un canal aparte. Ella ingresa el código y crea su contraseña. La contraseña se guarda cifrada (bcrypt) en la base: no está en el código ni en los secrets, y el código ya no sirve para entrar.

**Si olvida la contraseña:** cambiar `CODIGO_ACTIVACION` en los secrets por uno nuevo; ella toca «Olvidé mi contraseña» y crea otra.

## Correr en la compu

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # completar valores
streamlit run app.py
pytest
```
Sin `DATABASE_URL` usa un archivo SQLite local (`pandulce_local.db`).

## Estructura

```
app.py                  login + menú
pandulce/horas.py       normalizar horas, calcular, reconocer nombres (sin dependencias)
pandulce/planilla.py    qué falta revisar y cómo una planilla se vuelve registros
pandulce/lector.py      lectura de la foto con Claude (claude-opus-5-5, salida JSON con esquema)
pandulce/db.py          tablas y padrón inicial
pandulce/auth.py        primer ingreso, login, recuperación
pandulce/ui.py          conexión, secrets y filtros compartidos
vistas/                 una pantalla por archivo
tests/                  pytest
```
