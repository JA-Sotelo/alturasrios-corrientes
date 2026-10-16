@echo off
REM Ejecuta el puente de datos desde la carpeta del proyecto (para el Programador de tareas).
REM Usa el entorno virtual .venv si existe; si no, el Python instalado en el sistema.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" actualizar_datos.py
) else (
    python actualizar_datos.py
)
