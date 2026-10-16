"""
Dashboard Hidrológico — Provincia de Corrientes
Datos en vivo: Prefectura Naval Argentina (https://contenidosweb.prefecturanaval.gob.ar/alturas/)

Requisitos (requirements.txt):
    streamlit
    pandas
    requests
    lxml
    folium
    streamlit-folium
    matplotlib      # lo usa Styler.background_gradient

Ejecutar:
    streamlit run dashboard_hidrologico.py
"""

from __future__ import annotations

import base64
import io
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import folium
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium

# ============================================================================
# CONFIGURACIÓN
# ============================================================================
URL_PNA = "https://contenidosweb.prefecturanaval.gob.ar/alturas/"
SNAPSHOT = Path(__file__).parent / "datos" / "alturas_pna.html"   # copia que publica actualizar_datos.py
HORAS_COPIA_VIEJA = 13   # Prefectura publica 6, 12 y 18 h: el mayor intervalo es de 12 h
TTL_SEGUNDOS = 60 * 60  # Prefectura actualiza pocas veces al día
HEADERS = {
    "User-Agent": "Mozilla/5.0 (dashboard-hidrologico-corrientes)",
    "Accept-Language": "es-AR,es;q=0.9",
}

# ============================================================================
# AUTORÍA E IDENTIDAD  ← completá tus datos acá
# ============================================================================
AUTOR = "Javier Sotelo"
ROL = "Contador Público · Consultor en Business Intelligence"
REDES = {                       # pegá las URL; las vacías no se muestran
    "LinkedIn": "https://www.linkedin.com/in/javieralejandrosotelo/",
    "Instagram": "https://www.instagram.com/cr.javiersotelo/",
    "Sitio web": "",
}
# Logo: guardá un archivo logo.png (o .svg / .jpg / .webp) junto a este script.
CARPETA = Path(__file__).parent
INICIALES = "".join(p[0] for p in AUTOR.split()[:2]).upper()


def _cargar_logo() -> tuple[Path | None, str | None]:
    tipos = {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp",
             ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    for ext, mime in tipos.items():
        ruta = CARPETA / f"logo{ext}"
        if ruta.exists():
            return ruta, f"data:{mime};base64,{base64.b64encode(ruta.read_bytes()).decode()}"
    return None, None


LOGO_PATH, LOGO_URI = _cargar_logo()

st.set_page_config(
    page_title=f"Alturas de ríos · Corrientes | {AUTOR}",
    page_icon=str(LOGO_PATH) if LOGO_PATH and LOGO_PATH.suffix != ".svg" else "🌊",
    layout="wide",
)

# Estados oficiales PNA (para el panel manual)
ESTADOS_PNA = [
    "CRECE", "BAJA", "ESTAC.", "S/E.",
    "ALERTA CRECE", "ALERTA BAJA", "ALERTA ESTAC.",
    "EVACUACION CRECE", "EVACUACION BAJA", "EVACUACION ESTAC.",
]

# Paleta ÚNICA: misma semántica en mapa, gráfico y tabla
NIVELES = {
    #  nivel         color hex    color folium  ícono folium (sin prefijo)
    "EVACUACIÓN": ("#C62828", "red",    "warning-sign"),
    "ALERTA":     ("#E07B00", "orange", "bell"),
    "NORMAL":     ("#2E7D32", "green",  "ok-sign"),
    "SIN DATO":   ("#8A949C", "gray",   "question-sign"),
}

# ============================================================================
# CATÁLOGO FIJO: lo que Prefectura NO publica (coordenadas y pico histórico)
# Umbrales y altura de respaldo se usan solo si la página no responde
# o si el puerto no aparece en ella.  ⚠ Verificar Nivel_92 con fuente oficial.
# ============================================================================
CATALOGO = pd.DataFrame([
    # Puerto,               Río,       Lat,      Lon,      Nivel_92, Alerta_resp, Evac_resp
    ("ITUZAINGÓ",           "PARANÁ",  -27.5833, -56.6833,  5.10,  3.50,  4.00),
    ("ITÁ IBATÉ",           "PARANÁ",  -27.4333, -57.3167,  7.80,  5.50,  6.20),
    ("ITATÍ",               "PARANÁ",  -27.2693, -58.2435,  9.31,  6.80,  7.50),
    ("PASO DE LA PATRIA",   "PARANÁ",  -27.3167, -58.5667,  8.85,  6.50,  7.00),
    ("CORRIENTES",          "PARANÁ",  -27.4698, -58.8306,  8.60,  6.50,  7.00),
    ("EMPEDRADO",           "PARANÁ",  -27.9535, -58.7952,  7.90,  6.50,  6.70),
    ("BELLA VISTA",         "PARANÁ",  -28.5082, -59.0450,  7.40,  6.00,  6.40),
    ("GOYA",                "PARANÁ",  -29.1417, -59.2625,  7.15,  5.20,  5.70),
    ("ESQUINA",             "PARANÁ",  -30.0167, -59.5333,  6.20,  5.00,  5.40),
    ("GARRUCHOS",           "URUGUAY", -28.1833, -55.6500, 14.50, 10.00, 11.00),
    ("SANTO TOMÉ",          "URUGUAY", -28.5494, -56.0411, 15.10, 11.50, 12.50),
    ("ALVEAR",              "URUGUAY", -29.0962, -56.5492, 13.80,  9.50, 10.50),
    ("LA CRUZ",             "URUGUAY", -29.1750, -56.6333, 14.20, 10.00, 11.00),
    ("YAPEYÚ",              "URUGUAY", -29.4750, -56.8167, 13.50,  8.50,  9.50),
    ("PASO DE LOS LIBRES",  "URUGUAY", -29.7125, -57.0883, 13.20,  7.50,  8.50),
    ("BOMPLAND",            "URUGUAY", -29.9333, -57.4500, 11.80,  8.00,  9.00),
    ("MONTE CASEROS",       "URUGUAY", -30.2520, -57.6360, 10.40,  7.50,  8.50),
    ("MOCORETÁ",            "URUGUAY", -30.6167, -57.9667,  9.50,  6.50,  7.50),
], columns=["Puerto", "Río", "Lat", "Lon", "Nivel_92", "Alerta_resp", "Evac_resp"])


# ============================================================================
# HELPERS
# ============================================================================
def clave(texto) -> str:
    """Normaliza para cruzar nombres: 'Itá Ibaté' -> 'ITA IBATE'."""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", " ", t)).strip().upper()


def a_numero(valor) -> float | None:
    """'5,54' / '5.54 Mts' / '-0,05' / 'S/E' -> float o None."""
    if pd.isna(valor):
        return None
    s = str(valor).strip()
    m = re.search(r"-?\d+(?:[.,]\d+)?", s.replace(" ", ""))
    if not m:
        return None
    return float(m.group().replace(",", "."))


def nivel_desde_estado(estado, actual, alerta, evac) -> str:
    """Fuente de verdad: el estado oficial PNA. Si falta, se calcula por umbrales."""
    e = "" if estado is None or pd.isna(estado) else clave(estado)
    if e.startswith("EVACUACION"):
        return "EVACUACIÓN"
    if e.startswith("ALERTA"):
        return "ALERTA"
    if e and e not in ("S E", "SE", "NAN"):
        return "NORMAL"
    # Sin estado oficial: cálculo propio
    if actual is None or pd.isna(actual):
        return "SIN DATO"
    if evac is not None and not pd.isna(evac) and actual >= evac:
        return "EVACUACIÓN"
    if alerta is not None and not pd.isna(alerta) and actual >= alerta:
        return "ALERTA"
    return "NORMAL"


# Palabras clave para identificar columnas sin depender de su posición
PATRONES_COL = {
    "Puerto":            ("PUERTO",),
    "Rio_pna":           ("RIO",),
    "Actual":            ("ULTIMO REGISTRO", "ULT REGISTRO", "ALTURA"),
    "Variacion":         ("VARIACION",),
    "Periodo":           ("PERIODO",),
    "Fecha Hora":        ("FECHA",),
    "Estado Operativo":  ("ESTADO",),
    "Registro anterior": ("REGISTRO ANTERIOR", "ANTERIOR"),
    "Alerta":            ("ALERTA",),
    "Evacuacion":        ("EVACUACION",),
}


def mapear_columnas(columnas) -> dict:
    """Devuelve {columna_original: nombre_interno}. Prioriza coincidencias largas."""
    asignadas, usadas = {}, set()
    candidatos = sorted(
        ((len(p), interno, p) for interno, pats in PATRONES_COL.items() for p in pats),
        reverse=True,
    )
    for _, interno, patron in candidatos:
        if interno in usadas:
            continue
        for col in columnas:
            if col in asignadas:
                continue
            if patron in clave(col if not isinstance(col, tuple) else " ".join(map(str, col))):
                asignadas[col] = interno
                usadas.add(interno)
                break
    return asignadas


# ============================================================================
# EXTRACCIÓN (cacheada)
# ============================================================================
def obtener_html() -> tuple[str, str, str]:
    """Devuelve (html, hora, origen).

    1) Prefectura en vivo: funciona desde Argentina.
    2) Si falla (p. ej. en Streamlit Cloud, cuyos servidores Prefectura no acepta),
       usa la última copia que actualizar_datos.py publicó en el repositorio.
    """
    try:
        resp = requests.get(URL_PNA, headers=HEADERS, timeout=(6, 20))
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return resp.text, datetime.now().strftime("%d/%m/%Y %H:%M"), "vivo"
    except Exception as error_vivo:  # noqa: BLE001
        if not SNAPSHOT.exists():
            raise error_vivo
        html = SNAPSHOT.read_text(encoding="utf-8")
        m = re.search(r"<!-- capturado: (.+?) -->", html)
        return html, (m.group(1) if m else "fecha desconocida"), "copia"


@st.cache_data(ttl=TTL_SEGUNDOS, show_spinner="Consultando Prefectura Naval…")
def cargar_pna(marca_copia: float = 0.0) -> tuple[pd.DataFrame, str, str]:
    """marca_copia: fecha de modificación de la copia; si cambia, se invalida la caché."""
    html, hora, origen = obtener_html()

    # thousands=None: la coma es decimal en Argentina ("5,54"), no separador de miles
    tablas = pd.read_html(io.StringIO(html), thousands=None)
    tablas = [t for t in tablas if any("PUERTO" in clave(c) for c in t.columns)] or tablas
    if not tablas:
        raise ValueError("La página no contiene tablas.")
    crudo = max(tablas, key=len)

    df = crudo.rename(columns=mapear_columnas(crudo.columns))
    df = df[[c for c in PATRONES_COL if c in df.columns]].copy()
    if "Puerto" not in df.columns:
        raise ValueError(f"No se identificó la columna Puerto. Columnas: {list(crudo.columns)}")

    df = df[df["Puerto"].notna() & (df["Puerto"].map(clave) != "PUERTO")]
    for c in ("Actual", "Variacion", "Alerta", "Evacuacion"):
        if c in df.columns:
            df[c] = df[c].map(a_numero)

    df["clave"] = df["Puerto"].map(clave)
    df = df.drop(columns="Puerto").drop_duplicates("clave")
    return df, hora, origen


def armar_datos() -> tuple[pd.DataFrame, str | None, str | None, str | None]:
    """Cruza catálogo + PNA + correcciones manuales. Devuelve (df, error, hora, origen)."""
    base = CATALOGO.copy()
    base["clave"] = base["Puerto"].map(clave)

    error, hora, origen = None, None, None
    try:
        marca = SNAPSHOT.stat().st_mtime if SNAPSHOT.exists() else 0.0
        pna, hora, origen = cargar_pna(marca)
        df = base.merge(pna, on="clave", how="left")
    except Exception as e:  # noqa: BLE001
        error = str(e)
        df = base.copy()
        for c in ("Actual", "Variacion", "Periodo", "Fecha Hora",
                  "Estado Operativo", "Registro anterior", "Alerta", "Evacuacion"):
            df[c] = None

    # Umbrales: PNA si los publica; si no, los del catálogo
    df["Alerta"] = df["Alerta"].fillna(df["Alerta_resp"]).astype(float)
    df["Evacuacion"] = df["Evacuacion"].fillna(df["Evac_resp"]).astype(float)
    df["Fuente"] = df["Actual"].notna().map({True: "PNA", False: "Sin dato"})

    # Correcciones manuales (sobrescriben)
    for puerto, ov in st.session_state.get("overrides", {}).items():
        m = df["Puerto"] == puerto
        df.loc[m, "Actual"] = ov["Actual"]
        df.loc[m, "Estado Operativo"] = ov["Estado"]
        df.loc[m, "Fecha Hora"] = ov["Hora"]
        df.loc[m, "Fuente"] = "Manual"

    df["Actual"] = pd.to_numeric(df["Actual"], errors="coerce")
    df["Nivel"] = [
        nivel_desde_estado(r["Estado Operativo"], r["Actual"], r["Alerta"], r["Evacuacion"])
        for _, r in df.iterrows()
    ]
    df["Margen_Alerta"] = df["Alerta"] - df["Actual"]
    df["Margen_Evacuacion"] = df["Evacuacion"] - df["Actual"]
    df["Dif_92_Actual"] = df["Nivel_92"] - df["Actual"]
    return df.drop(columns=["clave", "Alerta_resp", "Evac_resp"]), error, hora, origen


def fmt(v, dec=2, signo=False, sufijo="") -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:+.{dec}f}{sufijo}" if signo else f"{v:.{dec}f}{sufijo}"


def txt(v) -> str:
    return "—" if v is None or pd.isna(v) or str(v).strip() == "" else str(v)


# ============================================================================
# HELPERS DE PRESENTACIÓN
# ============================================================================
CLASE_NIVEL = {"EVACUACIÓN": "evac", "ALERTA": "alerta", "NORMAL": "normal", "SIN DATO": "sd"}


def _nombre(p: str) -> str:
    """'PASO DE LA PATRIA' -> 'Paso de la Patria'."""
    menores = {"de", "la", "las", "los", "del", "y"}
    pal = str(p).lower().split()
    return " ".join(w if i and w in menores else w.capitalize() for i, w in enumerate(pal))


def _num(v, dec=2, signo=False) -> str:
    """Formato argentino: 4,44 / +0,26."""
    if v is None or pd.isna(v):
        return "—"
    return (f"{v:+.{dec}f}" if signo else f"{v:.{dec}f}").replace(".", ",")


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def marca_html(clase: str = "hx-logo") -> str:
    """Logo del autor si existe; si no, monograma con sus iniciales."""
    if LOGO_URI:
        return f'<img class="{clase}" src="{LOGO_URI}" alt="Logo de {AUTOR}">'
    return f'<div class="{clase} mono" aria-hidden="true">{INICIALES}</div>'


def seccion(titulo: str, bajada: str = "") -> None:
    st.html(f'<div class="sec"><h2>{titulo}</h2>{f"<p>{bajada}</p>" if bajada else ""}</div>')


def leyenda_niveles() -> str:
    items = "".join(
        f'<span><i style="background:var(--{CLASE_NIVEL[n]})"></i>{n.capitalize()}</span>'
        for n in ("NORMAL", "ALERTA", "EVACUACIÓN", "SIN DATO")
    )
    return f'<div class="lg" role="list">{items}</div>'


# ============================================================================
# ESTILOS GLOBALES
# Tokens de color y tipografía en un solo lugar; breakpoint móvil en 640 px.
# ============================================================================
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap');

:root {{
  --ink:#10212B; --ink-2:#4A5A64; --ink-3:#7A8890;
  --river:#0E5A7A; --river-50:#E8F2F6;
  --line:#DCE3E7; --surface:#F4F7F8; --card:#FFFFFF;
  --evac:{NIVELES["EVACUACIÓN"][0]}; --alerta:{NIVELES["ALERTA"][0]}; --alerta-txt:#B45F06;
  --normal:{NIVELES["NORMAL"][0]}; --sd:{NIVELES["SIN DATO"][0]};
}}

/* Base */
.stApp {{ font-family:'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; color:var(--ink); }}
.stApp h1, .stApp h2, .stApp h3 {{ font-family:'Archivo', 'Inter', sans-serif; letter-spacing:-.01em; color:var(--ink); }}
#MainMenu, footer, [data-testid="stDecoration"] {{ display:none; }}
.block-container {{ padding-top:4rem; padding-bottom:2rem; max-width:1240px; }}
[data-testid="stSidebar"] {{ background:var(--surface); border-right:1px solid var(--line); }}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ font-size:1rem; text-transform:uppercase; letter-spacing:.06em; color:var(--ink-2); }}

/* Cabecera */
.hx {{ border-bottom:1px solid var(--line); padding-bottom:1.25rem; }}
.hx-prov {{ font:800 1.5rem/1.2 'Archivo', sans-serif; text-transform:uppercase; letter-spacing:.14em;
            color:var(--ink); margin:0 0 1.25rem; padding-bottom:.75rem; border-bottom:3px solid var(--river);
            display:inline-block; }}
.hx-top {{ display:flex; gap:1rem; align-items:center; }}
.hx-logo {{ width:56px; height:56px; border-radius:8px; object-fit:contain; flex:none; }}
.mono {{ background:var(--river); color:#fff; display:grid; place-items:center;
         font:800 1.25rem 'Archivo', sans-serif; letter-spacing:.02em; }}
.hx-eyebrow {{ font-size:.75rem; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--river); margin:0 0 .25rem; }}
.hx-title {{ font:800 2rem/1.15 'Archivo', sans-serif; margin:0; padding:0; color:var(--ink); }}
.hx-sub {{ color:var(--ink-2); font-size:1rem; line-height:1.55; margin:.875rem 0 0; max-width:64ch; }}
.hx-meta {{ display:flex; flex-wrap:wrap; gap:.5rem 1.25rem; align-items:center; margin-top:1rem; font-size:.875rem; color:var(--ink-2); }}
.hx-meta b {{ color:var(--ink); }}
.pill {{ display:inline-flex; align-items:center; gap:.5rem; padding:.25rem .75rem; border-radius:999px; font-weight:600; font-size:.8125rem; }}
.pill::before {{ content:""; width:8px; height:8px; border-radius:50%; background:currentColor; }}
.pill.normal {{ color:var(--normal); background:#E8F3E9; }}
.pill.alerta {{ color:#9A4A00; background:#FDF0DC; }}
.pill.evac   {{ color:var(--evac); background:#FBE9E9; }}
.pill.sd     {{ color:var(--ink-2); background:var(--surface); }}

/* Indicadores */
.kp {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:.75rem; margin:1.25rem 0 .25rem; }}
.kp-card {{ background:var(--card); border:1px solid var(--line); border-left:6px solid var(--c, var(--river));
            border-radius:8px; padding:.75rem 1rem; min-width:0; }}
.kp-lbl {{ font-size:.8125rem; color:var(--lc, var(--ink-2)); font-weight:500; }}
.kp-card.estado .kp-lbl {{ font-weight:600; }}
.kp-val {{ font:700 1.75rem/1.2 'Archivo', sans-serif; color:var(--ink); margin-top:.25rem; font-variant-numeric:tabular-nums; }}
.kp-sub {{ font-size:.75rem; color:var(--ink-3); margin-top:.125rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}

/* Secciones */
.sec {{ margin:2.25rem 0 .75rem; }}
.sec h2 {{ font:700 1.375rem/1.25 'Archivo', sans-serif; margin:0; padding:0; }}
.sec p {{ color:var(--ink-2); margin:.25rem 0 0; font-size:.9375rem; line-height:1.5; max-width:72ch; }}

/* Leyenda */
.lg {{ display:flex; flex-wrap:wrap; gap:.5rem 1.25rem; font-size:.8125rem; color:var(--ink-2); margin:.5rem 0 0; }}
.lg span {{ display:inline-flex; align-items:center; gap:.4rem; }}
.lg i {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}

/* Gráfico de variaciones */
.vz {{ font-size:.8125rem; font-variant-numeric:tabular-nums; background:var(--card);
       border:1px solid var(--line); border-radius:8px; padding:.5rem .75rem .75rem; overflow-x:auto; }}
.vz-row {{ display:grid; grid-template-columns:minmax(130px,1.3fr) 64px 64px minmax(220px,3fr) minmax(170px,2fr);
           align-items:center; min-height:26px; min-width:660px; }}
.vz-head {{ font-weight:600; color:var(--ink-2); border-bottom:2px solid var(--ink); padding:.25rem 0; }}
.vz-head .vz-n {{ text-align:right; }}
.vz-grp {{ font-family:'Archivo', sans-serif; font-weight:700; border-bottom:1px solid var(--line); margin-top:.5rem; }}
.vz-note {{ font-family:'Inter', sans-serif; font-weight:600; font-size:.75rem; padding-left:.5rem; }}
.vz-name {{ padding-left:.75rem; }}
.vz-n {{ text-align:right; padding-right:.5rem; color:var(--ink-2); }}
.vz-b {{ font-weight:700; color:var(--ink); }}
.vz-sep {{ border-left:2px solid var(--ink); align-self:stretch; display:flex; align-items:center; padding-left:.375rem; }}
.vz-sep > .vz-track {{ flex:1; }}
.vz-track {{ position:relative; height:20px; }}
.vz-axis {{ position:absolute; top:-3px; bottom:-3px; width:1px; background:var(--ink-3); }}
.vz-bar {{ position:absolute; top:3px; height:14px; border-radius:1px; }}
.vz-stem {{ position:absolute; top:9px; height:2px; }}
.vz-dot {{ position:absolute; top:6px; width:8px; height:8px; border-radius:50%; margin-left:-4px; box-shadow:0 0 0 1.5px var(--ink); }}
.vz-lbl {{ position:absolute; top:1px; white-space:nowrap; font-weight:600; color:var(--ink); }}
.vz-it {{ font-style:italic; }}
.vz-dcol {{ padding:0 .25rem 0 .75rem; }}

/* Aviso legal (barra lateral) */
.legal {{ font-size:.75rem; line-height:1.55; color:var(--ink-2); max-height:52vh; overflow-y:auto; padding-right:.25rem; }}
[data-testid="stSidebar"] .legal p {{ font-size:.75rem !important; line-height:1.55; margin:0 0 .625rem; hyphens:auto; color:var(--ink-2); }}
[data-testid="stSidebar"] .legal .legal-intro {{ color:var(--ink); font-weight:500; }}
.legal h4 {{ font:600 .75rem/1.3 'Inter', sans-serif; color:var(--ink); text-transform:uppercase;
             letter-spacing:.04em; margin:.875rem 0 .25rem; padding:0; }}

/* Script de idioma: invisible */
.element-container:has(iframe[height="0"]) {{ display:none; }}

/* Pie de firma */
.ft {{ margin-top:3rem; border-top:1px solid var(--line); padding-top:1.25rem;
       display:flex; flex-wrap:wrap; gap:1rem 2rem; justify-content:space-between; align-items:center; }}
.ft-who {{ display:flex; gap:.75rem; align-items:center; }}
.ft-who .hx-logo {{ width:44px; height:44px; font-size:1rem; }}
.ft-by {{ font-size:.75rem; color:var(--ink-3); text-transform:uppercase; letter-spacing:.06em; }}
.ft-name {{ font:700 1rem 'Archivo', sans-serif; color:var(--ink); }}
.ft-role {{ font-size:.8125rem; color:var(--ink-2); }}
.ft-links {{ display:flex; flex-wrap:wrap; gap:.5rem 1rem; margin-top:.25rem; }}
.ft-links a {{ color:var(--river); font-weight:600; text-decoration:none; font-size:.8125rem; }}
.ft-links a:hover {{ text-decoration:underline; }}
.ft-note {{ font-size:.75rem; color:var(--ink-3); max-width:48ch; line-height:1.5; }}
.ft-note a {{ color:var(--ink-2); }}

/* Celulares */
@media (max-width: 640px) {{
  .block-container {{ padding:4rem 1rem 2rem; }}
  .hx-title {{ font-size:1.5rem; }}
  .hx-prov {{ font-size:1.125rem; letter-spacing:.1em; margin-bottom:1rem; }}
  .hx-sub {{ font-size:.9375rem; }}
  .hx-logo {{ width:44px; height:44px; }}
  .kp {{ grid-template-columns:repeat(2, minmax(0, 1fr)); gap:.5rem; }}
  .kp-card {{ padding:.625rem .75rem; }}
  .kp-card:last-child:nth-child(odd) {{ grid-column:1 / -1; }}
  .kp-val {{ font-size:1.375rem; }}
  .sec {{ margin-top:1.75rem; }}
  .sec h2 {{ font-size:1.1875rem; }}
  .vz {{ padding:.5rem; font-size:.75rem; }}
  .vz-dcol {{ padding-left:.5rem; }}
  .vz-row {{ grid-template-columns:minmax(92px,1fr) 52px minmax(128px,1.5fr); min-width:0; }}
  .vz-ref, .vz-pct {{ display:none !important; }}
  .ft {{ flex-direction:column; align-items:flex-start; }}
}}
</style>
"""
if "oscuro" not in st.session_state:
    st.session_state.oscuro = st.query_params.get("tema") == "oscuro"   # link compartible: ?tema=oscuro
OSCURO = st.session_state.oscuro


def _alternar_tema() -> None:
    st.session_state.oscuro = not st.session_state.oscuro
    st.query_params["tema"] = "oscuro" if st.session_state.oscuro else "claro"


# Modo oscuro: redefine los tokens y repinta los componentes nativos de Streamlit
CSS_OSCURO = """
<style>
:root {
  --ink:#E6EDF1; --ink-2:#A9B7C0; --ink-3:#7E8D96;
  --river:#5FB3D6; --river-50:#12303D;
  --line:#26343D; --surface:#111B21; --card:#16232B;
  --evac:#EF5350; --alerta:#F59E0B; --alerta-txt:#F59E0B; --normal:#4CAF50; --sd:#8A949C;
}
.stApp, [data-testid="stHeader"] { background:#0C1419; }
.stApp, .stApp p, .stApp label, .stApp li, .stApp span, .stMarkdown,
[data-testid="stWidgetLabel"] p, [data-testid="stCaptionContainer"] { color:var(--ink); }
[data-testid="stCaptionContainer"] p { color:var(--ink-2); }
[data-testid="stSidebar"] { background:var(--surface); }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color:var(--ink-2); }
[data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"],
[data-testid="stNumberInputContainer"], .stNumberInput input,
[data-testid="stExpander"] details, [data-testid="stForm"] {
  background:var(--card) !important; border-color:var(--line) !important; color:var(--ink) !important; }
[data-baseweb="popover"] ul, [data-baseweb="popover"] li { background:var(--card) !important; color:var(--ink) !important; }
[data-baseweb="popover"] li:hover { background:var(--river-50) !important; }
[data-testid="stExpander"] summary:hover p { color:var(--river); }
button[data-testid^="stBaseButton-secondary"] { background:var(--card); color:var(--ink); border-color:var(--line); }
button[data-testid^="stBaseButton-secondary"]:hover { border-color:var(--river); color:var(--river); }
[data-testid="stDataFrame"] { filter:invert(1) hue-rotate(180deg); }
.pill.normal { background:#16301A; } .pill.alerta { color:var(--alerta); background:#3A2A0C; }
.pill.evac { background:#3A1414; }
.vz-dot { box-shadow:0 0 0 1.5px #0C1419; }
[data-testid="stSidebar"] hr, .stApp hr { border-color:var(--line) !important; background:var(--line); }
[data-testid="stRadioOption"]:has(input:not(:checked)) > div > div:first-child,
[data-testid="stRadioOption"]:has(input:not(:checked)) > div > div:first-child > div { background:var(--card) !important; }
[data-testid="stRadioOption"]:has(input:not(:checked)) > div > div:first-child { box-shadow:inset 0 0 0 1px var(--ink-3); }
[data-testid="stSelectbox"] [role="group"] *, [data-testid="stMultiSelect"] [role="group"] * { color:var(--ink); }
[data-testid="stSelectbox"] input, [data-testid="stMultiSelect"] input { color:var(--ink) !important; -webkit-text-fill-color:var(--ink); }
[data-testid="stSelectbox"] svg, [data-testid="stMultiSelect"] svg { color:var(--ink-2); fill:var(--ink-2); }
iframe { color-scheme:normal; }
</style>
"""

st.markdown(CSS + (CSS_OSCURO if OSCURO else ""), unsafe_allow_html=True)

# Idioma: Streamlit declara la página como inglés (<html lang="en">) y los navegadores
# ofrecen "traducirla", alterando textos (p. ej. "Máxima suba" → "Alcalde suba").
# Se declara español y se bloquea la traducción automática.
components.html("""
<script>
  const d = window.parent.document;
  d.documentElement.lang = "es";
  d.documentElement.setAttribute("translate", "no");
  d.documentElement.classList.add("notranslate");
  if (!d.querySelector('meta[name="google"]')) {
    const m = d.createElement("meta");
    m.name = "google"; m.content = "notranslate";
    d.head.appendChild(m);
  }
</script>""", height=0)


# ============================================================================
# SIDEBAR
# ============================================================================
if "overrides" not in st.session_state:
    st.session_state.overrides = {}

st.sidebar.header("Datos")
#if st.sidebar.button("Actualizar datos", icon=":material/refresh:", width="stretch"):
#    cargar_pna.clear()

df, error_pna, hora_consulta, origen_datos = armar_datos()

if error_pna:
    st.sidebar.error(f"No se pudo leer Prefectura:\n\n{error_pna}")
else:
    if origen_datos == "copia":
        st.sidebar.caption(f"Copia de Prefectura del {hora_consulta} · Prefectura publica a las 6, 12 ó 18 hs.")
    else:
        st.sidebar.caption(f"Consultado {hora_consulta} · Prefectura publica a las 6, 12 ó 18 hs.")

faltantes = df.loc[df["Fuente"] == "Sin dato", "Puerto"].tolist()
if faltantes and not error_pna:
    st.sidebar.warning("Sin coincidencia en Prefectura: " + ", ".join(map(_nombre, faltantes)))

with st.sidebar.expander("Corrección manual", icon=":material/edit:", expanded=bool(error_pna)):
    st.caption("Solo para puertos sin dato o con lectura errónea. Se pierde al cerrar la pestaña.")
    with st.form("form_manual"):
        puerto_m = st.selectbox("Puerto", CATALOGO["Puerto"], format_func=_nombre)
        fila = df.loc[df["Puerto"] == puerto_m].iloc[0]
        alt_m = st.number_input("Altura (m)", 0.0, 30.0,
                                float(fila["Actual"]) if pd.notna(fila["Actual"]) else 0.0,
                                0.01, format="%.2f")
        est_m = st.selectbox("Estado PNA", ESTADOS_PNA)
        if st.form_submit_button("Aplicar", type="primary"):
            st.session_state.overrides[puerto_m] = {
                "Actual": alt_m, "Estado": est_m,
                "Hora": datetime.now().strftime("%d/%m/%Y %H:%M") + " (manual)",
            }
            st.rerun()
    if st.session_state.overrides:
        st.write("Corregidos:", ", ".join(map(_nombre, st.session_state.overrides)))
        if st.button("Quitar correcciones"):
            st.session_state.overrides = {}
            st.rerun()

st.sidebar.header("Filtros")

df["Estado PNA"] = df["Estado Operativo"].fillna("Sin dato").astype(str).str.strip()

st.sidebar.caption("Sin selección se muestran todos.")

rios = list(df["Río"].unique())
rio_sel = st.sidebar.multiselect("Río", rios, placeholder="Todos", format_func=_nombre)

niveles = [n for n in NIVELES if n in set(df["Nivel"])]
nivel_sel = st.sidebar.multiselect("Estado", niveles, placeholder="Todos", format_func=str.capitalize)

presentes = set(df["Estado PNA"])
estados_pna = [e for e in ESTADOS_PNA if e in presentes] + sorted(presentes - set(ESTADOS_PNA))
pna_sel = st.sidebar.multiselect("Estado PNA", estados_pna, placeholder="Todos")


def _filtro(col: str, seleccion: list) -> pd.Series:
    """Selección vacía = sin filtrar."""
    return df[col].isin(seleccion) if seleccion else pd.Series(True, index=df.index)


df_filt = df[_filtro("Río", rio_sel) & _filtro("Nivel", nivel_sel) & _filtro("Estado PNA", pna_sel)].copy()

if len(df_filt) < len(df):
    st.sidebar.caption(f"Mostrando {len(df_filt)} de {len(df)} puertos.")

st.sidebar.divider()

# Aviso legal: siempre disponible, plegado para no competir con el panel principal
AVISO_LEGAL = [
    ("", "El presente panel y aplicación web (Dashboard Hidrológico de la Provincia de Corrientes) es una "
         "herramienta de visualización de datos de carácter meramente informativo, experimental y de acceso público."),
    ("1. Origen y naturaleza de los datos",
     "Todos los registros hidrométricos, alturas, estados operativos, marcas de tiempo y umbrales críticos "
     "reflejados en este sistema son extractos o interpretaciones de la información pública brindada oficialmente "
     "por la Prefectura Naval Argentina (PNA) a través de sus canales de difusión oficiales. El desarrollador y "
     "administrador de este sitio no posee estaciones de medición propias, no realiza mediciones físicas en terreno, "
     "ni audita, convalida o garantiza la exactitud, integridad o actualización en tiempo real de los datos "
     "suministrados por fuentes terceras."),
    ("2. Exclusión de responsabilidad",
     "El creador, diseñador y administrador de esta plataforma no asume ningún tipo de responsabilidad legal, civil, "
     "penal o administrativa, directa ni indirecta, por daños, perjuicios, pérdidas económicas, materiales, "
     "logísticas o humanas que pudieran derivarse —de forma total o parcial— del uso, interpretación o aplicación "
     "de la información contenida en este tablero."),
    ("3. Inexistencia de asesoramiento oficial",
     "Esta aplicación no constituye un canal de comunicación oficial, alerta temprana certificado ni un servicio de "
     "pronóstico hidrometeorológico vinculante. Ante situaciones de emergencia hídrica, crecidas, alertas o necesidad "
     "de evacuación, los usuarios, organismos de defensa civil y público en general deben atenerse exclusivamente a "
     "los comunicados oficiales emitidos por los organismos competentes del Estado Nacional, Provincial o Municipal, "
     "y por la propia Prefectura Naval Argentina."),
    ("4. Uso bajo exclusivo riesgo",
     "El acceso a este panel y su utilización implica la aceptación incondicional por parte del usuario de que "
     "cualquier decisión operativa, náutica, comercial, agrícola o de protección civil tomada con base en estos "
     "gráficos, mapas o tablas corre por su única y exclusiva cuenta y riesgo."),
]

with st.sidebar.expander("Aviso legal", icon=":material/gavel:"):
    st.html('<div class="legal">' + "".join(
        f'<h4>{titulo}</h4><p>{texto}</p>' if titulo else f'<p class="legal-intro">{texto}</p>'
        for titulo, texto in AVISO_LEGAL) + "</div>")

st.sidebar.caption(f"Creado por **{AUTOR}**")


# ============================================================================
# CABECERA
# ============================================================================
def situacion_general(d: pd.DataFrame) -> tuple[str, str]:
    n_ev = int((d["Nivel"] == "EVACUACIÓN").sum())
    n_al = int((d["Nivel"] == "ALERTA").sum())
    if n_ev:
        extra = f" y {_plural(n_al, 'en alerta', 'en alerta')}" if n_al else ""
        return "evac", f"{_plural(n_ev, 'puerto', 'puertos')} en evacuación{extra}"
    if n_al:
        return "alerta", f"{_plural(n_al, 'puerto', 'puertos')} en alerta"
    if (d["Nivel"] == "SIN DATO").all():
        return "sd", "Sin datos disponibles"
    return "normal", "Todos los puertos en niveles normales"


def pie_de_firma() -> None:
    links = "".join(f'<a href="{url}" target="_blank" rel="noopener">{red}</a>' for red, url in REDES.items() if url)
    st.html(f"""
    <footer class="ft">
      <div class="ft-who">
        {marca_html()}
        <div>
          <div class="ft-by">Creado por</div>
          <div class="ft-name">{AUTOR}</div>
          <div class="ft-role">{ROL}</div>
          {f'<div class="ft-links">{links}</div>' if links else ''}
        </div>
      </div>
      <p class="ft-note">Datos: <a href="{URL_PNA}" target="_blank" rel="noopener">Prefectura Naval Argentina</a>.
        Tablero informativo; ante situaciones de riesgo seguí las indicaciones de Prefectura y Defensa Civil.</p>
    </footer>""")


with st.container(horizontal=True, horizontal_alignment="right"):
    st.button("Modo claro" if OSCURO else "Modo oscuro",
              icon=":material/light_mode:" if OSCURO else ":material/dark_mode:",
              on_click=_alternar_tema, help="Cambiar entre vista clara y oscura")

clase_sit, texto_sit = situacion_general(df)
actualizado = hora_consulta or datetime.now().strftime("%d/%m/%Y %H:%M")

st.html(f"""
<header class="hx">
  <p class="hx-prov">Provincia de Corrientes</p>
  <div class="hx-top">
    {marca_html()}
    <div>
      <p class="hx-eyebrow">Monitoreo hidrométrico · Corrientes</p>
      <h1 class="hx-title">Alturas de los ríos Paraná y Uruguay</h1>
    </div>
  </div>
  <p class="hx-sub">Situación de {len(df)} puertos de la provincia frente a sus niveles de alerta,
     evacuación y la creciente de 1992, con datos oficiales de Prefectura Naval Argentina.</p>
  <div class="hx-meta">
    <span class="pill {clase_sit}">{texto_sit}</span>
    <span>Actualizado <b>{actualizado}</b></span>
    <span>Creado por <b>{AUTOR}</b></span>
  </div>
</header>""")

if origen_datos == "copia":
    try:
        antiguedad = datetime.now() - datetime.strptime(hora_consulta, "%d/%m/%Y %H:%M")
        if antiguedad.total_seconds() > HORAS_COPIA_VIEJA * 3600:
            st.warning(f"Los datos corresponden a la última lectura disponible ({hora_consulta}). "
                       "Para la situación actual, consultá la fuente oficial.")
    except ValueError:
        pass

if error_pna:
    st.warning("Prefectura no respondió: se muestran solo datos de catálogo y correcciones manuales.")

if df_filt.empty:
    st.info("Ningún puerto cumple la combinación de filtros elegida. Ampliá la selección en el panel lateral.")
    pie_de_firma()
    st.stop()


# ============================================================================
# INDICADORES
# ============================================================================
def tarjeta(etiqueta: str, valor: str, sub: str, color: str = "var(--river)", color_txt: str = "") -> str:
    """color: línea lateral. color_txt: si se indica, la etiqueta toma el color del estado."""
    estilo = f"--c:{color};" + (f"--lc:{color_txt};" if color_txt else "")
    clase = "kp-card estado" if color_txt else "kp-card"
    return (f'<div class="{clase}" style="{estilo}"><div class="kp-lbl">{etiqueta}</div>'
            f'<div class="kp-val">{valor}</div><div class="kp-sub">{sub}</div></div>')


total = len(df_filt)
conteo = {n: int((df_filt["Nivel"] == n).sum()) for n in NIVELES}
subas = df_filt.dropna(subset=["Variacion"]).sort_values("Variacion", ascending=False)
if len(subas) and subas.iloc[0]["Variacion"] > 0:
    top = subas.iloc[0]
    tarjeta_suba = tarjeta("Máxima suba", f"{_num(top['Variacion'], signo=True)} m", _nombre(top["Puerto"]))
else:
    tarjeta_suba = tarjeta("Máxima suba", "—", "sin subas registradas")

st.html('<div class="kp">'
        + tarjeta("Puertos", str(total), "con datos de Prefectura" if not error_pna else "datos de respaldo")
        + tarjeta("Normal", str(conteo["NORMAL"]), f"de {total} puertos", "var(--normal)", "var(--normal)")
        + tarjeta("Alerta", str(conteo["ALERTA"]), f"de {total} puertos", "var(--alerta)", "var(--alerta-txt)")
        + tarjeta("Evacuación", str(conteo["EVACUACIÓN"]), f"de {total} puertos", "var(--evac)", "var(--evac)")
        + tarjeta_suba
        + "</div>")


# ============================================================================
# MAPA
# ============================================================================
seccion("Mapa de puertos", "Tocá un punto para ver la última medición, los umbrales y la referencia de 1992.")

m = folium.Map(location=[-28.9, -57.7], zoom_start=7, tiles="OpenStreetMap", control_scale=True)
if OSCURO:
    # OpenStreetMap no tiene versión oscura: se invierten los mosaicos (sin API key)
    m.get_root().header.add_child(folium.Element(
        "<style>.leaflet-tile-pane{filter:invert(1) hue-rotate(180deg) brightness(.9) contrast(.9);}"
        ".leaflet-container{background:#0C1419;}</style>"))

for _, r in df_filt.iterrows():
    hexcol, folcol, icono = NIVELES[r["Nivel"]]
    var = r["Variacion"]
    flecha = "▲" if pd.notna(var) and var > 0 else ("▼" if pd.notna(var) and var < 0 else "")
    filas_popup = "".join(
        f'<tr><td style="color:#4A5A64;padding:1px 8px 1px 0">{k}</td><td style="text-align:right;font-weight:600">{v}</td></tr>'
        for k, v in [
            ("Estado PNA", txt(r["Estado Operativo"])),
            ("Período", txt(r["Periodo"])),
            ("Alerta", f"{_num(r['Alerta'])} m"),
            ("Evacuación", f"{_num(r['Evacuacion'])} m"),
            ("Pico 1992", f"{_num(r['Nivel_92'])} m"),
            ("Distancia al pico", f"{_num(r['Dif_92_Actual'], signo=True)} m"),
        ]
    )
    popup_html = f"""
    <div translate="no" class="notranslate" style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;width:236px;font-size:12px;color:#10212B;line-height:1.45">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;
                  border-bottom:3px solid {hexcol};padding-bottom:4px;margin-bottom:6px">
        <b style="font-size:14px">{_nombre(r['Puerto'])}</b>
        <span style="color:{hexcol};font-weight:700;font-size:11px;letter-spacing:.04em">{r['Nivel']}</span>
      </div>
      <div style="color:#4A5A64;font-size:11px">Río {_nombre(r['Río'])} · {txt(r['Fecha Hora'])}</div>
      <div style="font-size:22px;font-weight:700;margin:2px 0 6px">{_num(r['Actual'])} m
        <span style="font-size:12px;font-weight:600;color:#4A5A64">{flecha} {_num(var, signo=True)} m</span></div>
      <table style="width:100%;border-collapse:collapse;font-size:12px">{filas_popup}</table>
      <div style="color:#7A8890;font-size:10px;margin-top:6px">Registro anterior: {txt(r['Registro anterior'])} · Fuente: {r['Fuente']}</div>
    </div>"""
    folium.Marker(
        location=[r["Lat"], r["Lon"]],
        popup=folium.Popup(popup_html, max_width=260),
        tooltip=f"{_nombre(r['Puerto'])}: {_num(r['Actual'])} m · {r['Nivel'].capitalize()}",
        icon=folium.Icon(color=folcol, icon=icono),
    ).add_to(m)

# returned_objects=[] evita re-ejecutar el script con cada zoom o arrastre
st_folium(m, use_container_width=True, height=480, returned_objects=[])
st.html(leyenda_niveles())


# ============================================================================
# GRÁFICO DE VARIACIONES (tabla con barras de desvío)
# ============================================================================
ROJO, VERDE = "var(--evac)", "var(--normal)"


def _escala(serie: pd.Series):
    """Dominio con cero incluido y margen para las etiquetas. Devuelve pos(v) en %."""
    s = serie.dropna()
    lo, hi = (min(0.0, s.min()), max(0.0, s.max())) if len(s) else (0.0, 1.0)
    if lo == hi:
        hi = 1.0
    span = hi - lo
    lo -= span * 0.40 if lo < 0 else 0
    hi += span * 0.40 if hi > 0 else 0
    return lambda v: (v - lo) / (hi - lo) * 100


def _celda_barra(v, pos, etiqueta) -> str:
    """Barra que nace en el eje cero: positiva a la derecha, negativa a la izquierda."""
    if v is None or pd.isna(v):
        return '<div class="vz-track"></div>'
    z, x = pos(0), pos(v)
    color = ROJO if v > 0 else VERDE
    izq, ancho = min(z, x), max(abs(x - z), 0.4)
    lbl = (f'<span class="vz-lbl" style="left:calc({x:.2f}% + 5px)">{etiqueta}</span>' if v > 0 else
           f'<span class="vz-lbl" style="right:calc({100 - x:.2f}% + 5px)">{etiqueta}</span>')
    return (f'<div class="vz-track"><div class="vz-axis" style="left:{z:.2f}%"></div>'
            f'<div class="vz-bar" style="left:{izq:.2f}%;width:{ancho:.2f}%;background:{color}"></div>{lbl}</div>')


def _celda_lollipop(v, pos, etiqueta) -> str:
    """Línea fina desde el cero con un punto en el valor."""
    if v is None or pd.isna(v):
        return '<div class="vz-track"></div>'
    z, x = pos(0), pos(v)
    color = ROJO if v > 0 else VERDE
    lbl = (f'<span class="vz-lbl vz-it" style="left:calc({x:.2f}% + 8px)">{etiqueta}</span>' if v > 0 else
           f'<span class="vz-lbl vz-it" style="right:calc({100 - x:.2f}% + 8px)">{etiqueta}</span>')
    return (f'<div class="vz-track"><div class="vz-axis" style="left:{z:.2f}%"></div>'
            f'<div class="vz-stem" style="left:{min(z, x):.2f}%;width:{abs(x - z):.2f}%;background:{color}"></div>'
            f'<div class="vz-dot" style="left:{x:.2f}%;background:{color}"></div>{lbl}</div>')


def grafico_variaciones(df: pd.DataFrame, col_ref: str, nombre_ref: str, por_variacion: bool) -> str:
    d = df[["Puerto", "Río", "Actual", col_ref]].rename(columns={col_ref: "Ref"}).copy()
    d["Delta"] = d["Actual"] - d["Ref"]
    d["Pct"] = d["Delta"] / d["Ref"] * 100
    pos_d, pos_p = _escala(d["Delta"]), _escala(d["Pct"])

    filas = []
    for rio, g in d.groupby("Río", sort=False):
        if por_variacion:
            g = g.sort_values("Delta", ascending=False, na_position="last")
        sobre = int((g["Delta"] > 0).sum())
        resumen = (f'<span style="color:{ROJO}">{sobre} de {len(g)} por encima</span>' if sobre
                   else f'<span style="color:{VERDE}">todos por debajo</span>')
        filas.append(f'<div class="vz-row vz-grp"><div>Río {_nombre(rio)}</div><div class="vz-ref"></div><div></div>'
                     f'<div class="vz-note">{resumen}</div><div class="vz-sep vz-pct"></div></div>')
        for _, r in g.iterrows():
            filas.append(
                f'<div class="vz-row"><div class="vz-name">{_nombre(r["Puerto"])}</div>'
                f'<div class="vz-n vz-ref">{_num(r["Ref"])}</div><div class="vz-n vz-b">{_num(r["Actual"])}</div>'
                f'<div class="vz-dcol">{_celda_barra(r["Delta"], pos_d, _num(r["Delta"], signo=True))}</div>'
                f'<div class="vz-sep vz-pct">{_celda_lollipop(r["Pct"], pos_p, _num(r["Pct"], 1, signo=True))}</div></div>'
            )

    cab = (f'<div class="vz-row vz-head"><div>Puerto</div><div class="vz-n vz-ref">{nombre_ref}</div>'
           f'<div class="vz-n">Actual</div><div style="padding-left:.75rem">Δ Actual − {nombre_ref} (m)</div>'
           f'<div class="vz-sep vz-pct" style="border-left-color:transparent">Δ %</div></div>')
    return f'<div class="vz" role="table" aria-label="Nivel actual frente a {nombre_ref}">{cab}{"".join(filas)}</div>'


seccion("Distancia a la referencia",
        "Cuánto le falta a cada puerto para llegar al umbral elegido (verde) o cuánto lo superó (rojo).")

c_ref, c_ord = st.columns(2)
modo = c_ref.selectbox(
    "Comparar contra",
    ["Nivel de alerta", "Nivel de evacuación", "Creciente de 1992 (máximo histórico)"],
)
col_ref, nombre_ref = {
    "Nivel de alerta": ("Alerta", "Alerta"),
    "Nivel de evacuación": ("Evacuacion", "Evacuación"),
    "Creciente de 1992 (máximo histórico)": ("Nivel_92", "Pico '92"),
}[modo]
orden = c_ord.radio("Ordenar", ["Geográfico (aguas abajo)", "Variación más alta primero"], horizontal=True)

st.html(grafico_variaciones(df_filt, col_ref, nombre_ref, orden.startswith("Variación")))
st.html(f'<div class="lg"><span><i style="background:{ROJO};border-radius:2px"></i>Por encima de la referencia</span>'
        f'<span><i style="background:{VERDE};border-radius:2px"></i>Por debajo</span>'
        f'<span>Δ % = (Actual − Referencia) ÷ Referencia</span></div>')


# ============================================================================
# PLANILLA
# ============================================================================
seccion("Todos los datos", "La planilla completa, para consultar o copiar.")

tabla = df_filt[[
    "Puerto", "Río", "Nivel", "Actual", "Variacion", "Periodo", "Fecha Hora", "Estado Operativo",
    "Alerta", "Evacuacion", "Margen_Alerta", "Margen_Evacuacion", "Nivel_92", "Dif_92_Actual", "Fuente",
]].rename(columns={
    "Nivel": "Estado", "Actual": "Últ. registro (m)", "Variacion": "Variación (m)",
    "Periodo": "Período", "Estado Operativo": "Estado PNA",
    "Alerta": "Alerta (m)", "Evacuacion": "Evacuación (m)",
    "Margen_Alerta": "Margen a alerta (m)", "Margen_Evacuacion": "Margen a evacuación (m)",
    "Nivel_92": "Pico 1992 (m)", "Dif_92_Actual": "Dist. al pico '92 (m)",
})
tabla["Puerto"] = tabla["Puerto"].map(_nombre)
tabla["Río"] = tabla["Río"].map(_nombre)

num_cols = ["Últ. registro (m)", "Alerta (m)", "Evacuación (m)", "Margen a alerta (m)",
            "Margen a evacuación (m)", "Pico 1992 (m)", "Dist. al pico '92 (m)"]

with st.expander(f"Ver planilla ({len(tabla)} puertos)", icon=":material/table:"):
    estilo = (
        tabla.style
        .format("{:.2f}", subset=num_cols, na_rep="—", decimal=",")
        .format("{:+.2f}", subset=["Variación (m)"], na_rep="—", decimal=",")
        .map(lambda v: f"color: {NIVELES.get(v, ('#10212B',))[0]}; font-weight: 600", subset=["Estado"])
    )
    if not OSCURO:  # en oscuro la tabla se invierte por CSS y los degradados perderían sentido
        estilo = (estilo
                  .background_gradient(subset=["Margen a alerta (m)", "Margen a evacuación (m)"], cmap="YlOrRd_r")
                  .background_gradient(subset=["Dist. al pico '92 (m)"], cmap="Blues"))
    st.dataframe(estilo, width="stretch", hide_index=True)

pie_de_firma()
