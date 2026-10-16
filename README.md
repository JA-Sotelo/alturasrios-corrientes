# Alturas de los ríos Paraná y Uruguay · Corrientes

Tablero interactivo que muestra la situación hidrométrica de 18 puertos de la provincia de Corrientes frente a sus niveles de alerta, evacuación y la creciente de 1992, con datos públicos de la [Prefectura Naval Argentina](https://contenidosweb.prefecturanaval.gob.ar/alturas/).

## Qué muestra

- **Situación general** e indicadores por estado: normal, alerta y evacuación.
- **Mapa** con la ficha de cada puerto: última medición, variación, umbrales y referencia de 1992.
- **Distancia a la referencia**: cuánto le falta a cada puerto para llegar al umbral elegido, o cuánto lo superó.
- **Planilla completa**, filtros por río, estado y estado PNA, y modo claro/oscuro.

Los datos se consultan automáticamente y se actualizan cada hora.

## Ejecutar en tu computadora

```bash
python -m pip install -r requirements.txt
streamlit run dashboard_hidrologico.py
```

## Actualización de datos en la versión publicada

El sitio de Prefectura no acepta conexiones desde los servidores de Streamlit Cloud, que están fuera de Argentina. Por eso el tablero trabaja en dos niveles:

1. **En vivo**: si puede, consulta a Prefectura directamente. Esto funciona al ejecutarlo en una computadora en Argentina.
2. **Copia publicada**: si no puede, lee `datos/alturas_pna.html`, una copia que `actualizar_datos.py` sube al repositorio desde una PC en Argentina.

El tablero indica en el panel lateral de dónde vienen los datos y avisa si la copia tiene más de 6 horas.

### Programar la actualización (Windows)

Copiá `Alturas PNA - Actualizacion.bat` al Escritorio y abrilo con doble clic. Desde su menú podés:

1. **Activar la actualización automática cada hora** (crea una tarea en el Programador de tareas de Windows).
2. **Actualizar ahora**.
3. **Ver las últimas ejecuciones**.
4. **Desactivar la actualización automática**.

La tarea corre en segundo plano, sin abrir ventanas, mientras la PC esté encendida y con la sesión iniciada. El registro de cada ejecución queda en `datos/actualizar_datos.log`.

## Tecnologías

Python · Streamlit · pandas · Folium

## Aviso

Herramienta de carácter informativo y experimental. No es un canal oficial de alertas: ante situaciones de riesgo, seguí las indicaciones de Prefectura Naval Argentina y Defensa Civil. El aviso legal completo está disponible dentro del tablero.

---

Creado por **Javier Sotelo** · Contador Público · Consultor en Business Intelligence
