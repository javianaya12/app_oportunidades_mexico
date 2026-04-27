# MVP SaaS: Mapa de oportunidades de negocio en México

Aplicación en Python + Streamlit para cargar datos de negocios y zonas de población, visualizar competencia en un mapa OpenStreetMap/Folium y calcular un ranking de oportunidades comerciales.

## Estructura

```text
mvp_oportunidades_mexico/
├── app.py
├── requirements.txt
├── README.md
├── data/
│   ├── negocios_simulados.csv
│   ├── zonas_poblacion_simuladas.csv
│   └── datasets_simulados_mexico.xlsx
├── outputs/
└── src/
    ├── __init__.py
    ├── data_processing.py
    ├── scoring.py
    ├── map_utils.py
    ├── export_utils.py
    └── sample_data.py
```

## Cómo correr

1. Entra a la carpeta del proyecto:

```bash
cd mvp_oportunidades_mexico
```

2. Crea un entorno virtual opcional:

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Mac/Linux:

```bash
source .venv/bin/activate
```

3. Instala dependencias:

```bash
pip install -r requirements.txt
```

4. Genera datos simulados, si todavía no existen:

```bash
python -m src.sample_data
```

5. Ejecuta la app:

```bash
streamlit run app.py
```

## Columnas esperadas

### Dataset de negocios

- business_name
- business_type
- city
- address
- latitude
- longitude

### Dataset de zonas/población

- zone_id
- zone_name
- city
- latitude
- longitude
- population
- income_index opcional

La app también intenta reconocer columnas equivalentes en español, por ejemplo: `latitud`, `longitud`, `ciudad`, `poblacion`, `giro`, `actividad`.

## Fórmula de scoring MVP

El score se calcula de 0 a 100 con esta lógica:

- Mayor población aumenta la oportunidad.
- Menor competencia cercana aumenta la oportunidad.
- Mayor índice de ingreso aumenta ligeramente la oportunidad.

Fórmula usada:

```text
score = 0.60 * poblacion_normalizada + 0.25 * (1 - competencia_normalizada) + 0.15 * ingreso_normalizado
```

Después se clasifica así:

- Alta: score >= 70
- Media: score >= 45 y < 70
- Baja: score < 45

## Nota importante sobre geocodificación

Este MVP no usa APIs de pago. Para producción, lo ideal es cargar datasets que ya traigan latitud y longitud, como muchos archivos geográficos oficiales o datos previamente procesados. Si un archivo trae solo direcciones, se puede agregar geocodificación con Nominatim/OpenStreetMap, pero debe hacerse con cuidado por límites de uso y rendimiento.
