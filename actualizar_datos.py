"""
Puente de datos: Prefectura Naval → repositorio de GitHub → tablero en Streamlit Cloud.

Prefectura no acepta conexiones desde los servidores de Streamlit Cloud (fuera de Argentina).
Este script corre en una PC en Argentina, descarga la página de alturas y, si la tabla cambió,
guarda una copia en datos/alturas_pna.html y la sube al repositorio. El tablero publicado
lee esa copia cuando no puede llegar a Prefectura en forma directa.

Uso manual:
    python actualizar_datos.py

Uso automático: Programador de tareas de Windows, cada hora (ver instrucciones en el README).
Requisitos: Git instalado y la carpeta clonada desde GitHub con permiso para hacer push.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

URL_PNA = "https://contenidosweb.prefecturanaval.gob.ar/alturas/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (dashboard-hidrologico-corrientes)",
    "Accept-Language": "es-AR,es;q=0.9",
}
CARPETA = Path(__file__).resolve().parent
DESTINO = CARPETA / "datos" / "alturas_pna.html"
REGISTRO = CARPETA / "datos" / "actualizar_datos.log"


def log(mensaje: str) -> None:
    linea = f"{datetime.now():%d/%m/%Y %H:%M:%S}  {mensaje}"
    print(linea)
    REGISTRO.parent.mkdir(exist_ok=True)
    with REGISTRO.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def tablas(html: str) -> str:
    """Solo las tablas: el resto de la página puede cambiar sin que cambien los datos."""
    return "\n".join(re.findall(r"<table.*?</table>", html, flags=re.I | re.S))


def git(*args: str) -> None:
    resultado = subprocess.run(
        ["git", *args], cwd=CARPETA, capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # sin ventanas al correr en segundo plano
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {resultado.stderr.strip() or resultado.stdout.strip()}")


def main() -> int:
    try:
        resp = requests.get(URL_PNA, headers=HEADERS, timeout=(10, 40))
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        html = resp.text
    except requests.RequestException as e:
        log(f"ERROR al consultar Prefectura: {e}")
        return 1

    if not tablas(html):
        log("ERROR: la respuesta no contiene tablas; se conserva la copia anterior.")
        return 1

    anterior = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
    if tablas(anterior) == tablas(html):
        log("Sin cambios en los datos.")
        return 0

    ahora = datetime.now()
    DESTINO.parent.mkdir(exist_ok=True)
    DESTINO.write_text(f"<!-- capturado: {ahora:%d/%m/%Y %H:%M} -->\n{html}", encoding="utf-8")

    try:
        git("pull", "--rebase", "--autostash")      # por si se editó algo desde la web de GitHub
        git("add", str(DESTINO.relative_to(CARPETA)))
        git("commit", "-m", f"Datos PNA {ahora:%d/%m/%Y %H:%M}")
        git("push")
    except RuntimeError as e:
        log(f"ERROR al publicar en GitHub: {e}")
        return 1

    log("Datos actualizados y publicados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
