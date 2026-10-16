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

## Tecnologías

Python · Streamlit · pandas · Folium

## Aviso

Herramienta de carácter informativo y experimental. No es un canal oficial de alertas: ante situaciones de riesgo, seguí las indicaciones de Prefectura Naval Argentina y Defensa Civil. El aviso legal completo está disponible dentro del tablero.

---

Creado por **Javier Sotelo** · Contador Público · Consultor en Business Intelligence
