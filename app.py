from __future__ import annotations

from pathlib import Path
import streamlit as st
from streamlit_folium import st_folium
import pandas as pd

from src.data_processing import (
    REQUIRED_BUSINESS_COLUMNS,
    REQUIRED_ZONE_COLUMNS,
    apply_filters,
    classify_businesses,
    clean_coordinates,
    geocode_missing_coordinates,
    load_dataset,
    normalize_columns,
    validate_columns,
)
from src.export_utils import to_excel_bytes, to_pdf_bytes
from src.map_utils import build_opportunity_map
from src.sample_data import create_sample_files
from src.scoring import calculate_competition_by_zone, calculate_opportunity_score

st.set_page_config(page_title="Mapa de Oportunidades México", page_icon="🗺️", layout="wide")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

st.title("🗺️ SaaS MVP | Mapa de oportunidades de negocio en México")
st.caption("Carga datos de negocios y población, analiza competencia cercana y detecta zonas con alto potencial comercial.")

with st.sidebar:
    st.header("1. Datos")
    use_sample = st.toggle("Usar datasets simulados", value=True)

    if st.button("Generar datasets de prueba"):
        create_sample_files(DATA_DIR)
        st.success("Datasets simulados creados en la carpeta data/.")

    business_file = None
    zones_file = None
    if not use_sample:
        business_file = st.file_uploader("Dataset de negocios CSV/Excel", type=["csv", "xlsx", "xls"])
        zones_file = st.file_uploader("Dataset de zonas/población CSV/Excel", type=["csv", "xlsx", "xls"])

    st.header("2. Filtros")
    radius_km = st.slider("Radio de competencia cercana (km)", min_value=0.5, max_value=10.0, value=2.0, step=0.5)
    enable_geocoding = st.toggle("Geocodificar direcciones sin lat/lon (demo)", value=False)

@st.cache_data(show_spinner=False)
def load_sample_data():
    business_path = DATA_DIR / "negocios_simulados.csv"
    zones_path = DATA_DIR / "zonas_poblacion_simuladas.csv"
    if not business_path.exists() or not zones_path.exists():
        create_sample_files(DATA_DIR)
    return pd.read_csv(business_path), pd.read_csv(zones_path)

try:
    if use_sample:
        businesses_raw, zones_raw = load_sample_data()
    else:
        if business_file is None or zones_file is None:
            st.info("Carga ambos datasets o activa 'Usar datasets simulados' para ver el MVP funcionando.")
            st.stop()
        businesses_raw = load_dataset(business_file)
        zones_raw = load_dataset(zones_file)

    businesses_pre = normalize_columns(businesses_raw)
    zones_pre = normalize_columns(zones_raw)

    if enable_geocoding and not use_sample:
        businesses_pre = geocode_missing_coordinates(businesses_pre, max_rows=25)
        zones_pre = geocode_missing_coordinates(zones_pre, max_rows=25)

    businesses = classify_businesses(clean_coordinates(businesses_pre))
    zones = clean_coordinates(zones_pre)

    errors = []
    errors.extend(validate_columns(businesses, REQUIRED_BUSINESS_COLUMNS, "Dataset de negocios"))
    errors.extend(validate_columns(zones, REQUIRED_ZONE_COLUMNS, "Dataset de población/zonas"))
    if errors:
        for error in errors:
            st.error(error)
        st.stop()

except Exception as exc:
    st.error(f"No se pudieron cargar/procesar los datos: {exc}")
    st.stop()

cities = ["Todas"] + sorted(set(businesses["city"].dropna().astype(str)) | set(zones["city"].dropna().astype(str)))
business_types = ["Todos"] + sorted(businesses["business_type"].dropna().astype(str).unique().tolist())

with st.sidebar:
    selected_city = st.selectbox("Ciudad", cities)
    selected_type = st.selectbox("Tipo de negocio", business_types)

filtered_businesses, filtered_zones = apply_filters(businesses, zones, selected_city, selected_type)
zones_competition = calculate_competition_by_zone(filtered_businesses, filtered_zones, radius_km)
scored_zones = calculate_opportunity_score(zones_competition)

high_opportunities = int((scored_zones["opportunity_level"] == "Alta").sum()) if not scored_zones.empty else 0

metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("Negocios visibles", f"{len(filtered_businesses):,}")
metric_2.metric("Zonas analizadas", f"{len(scored_zones):,}")
metric_3.metric("Oportunidades altas", f"{high_opportunities:,}")
metric_4.metric("Radio analizado", f"{radius_km:.1f} km")

left, right = st.columns([1.45, 1])

with left:
    st.subheader("Mapa interactivo")
    fmap = build_opportunity_map(filtered_businesses, scored_zones, selected_type)
    st_folium(fmap, width=None, height=650)

with right:
    st.subheader("Ranking de zonas")
    display_cols = [
        "zone_name", "city", "population", "competition_count", "nearest_competitor_km",
        "opportunity_score", "opportunity_level", "recommendation",
    ]
    display_cols = [c for c in display_cols if c in scored_zones.columns]
    st.dataframe(scored_zones[display_cols], use_container_width=True, height=460)

    st.subheader("Exportar")
    excel_bytes = to_excel_bytes(scored_zones)
    pdf_bytes = to_pdf_bytes(scored_zones)
    st.download_button(
        "Descargar Excel",
        data=excel_bytes,
        file_name="ranking_oportunidades_mexico.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        "Descargar PDF",
        data=pdf_bytes,
        file_name="reporte_oportunidades_mexico.pdf",
        mime="application/pdf",
    )

st.divider()
st.subheader("Cómo interpretar el score")
st.write(
    "El score combina población, baja competencia cercana e índice de ingreso simulado. "
    "Para un MVP comercial, esto permite detectar zonas donde podría existir demanda suficiente "
    "y poca oferta del tipo de negocio seleccionado."
)

with st.expander("Formato mínimo esperado de los datasets"):
    st.markdown(
        """
        **Dataset de negocios:** `business_name`, `business_type`, `city`, `address`, `latitude`, `longitude`  
        **Dataset de zonas/población:** `zone_id`, `zone_name`, `city`, `latitude`, `longitude`, `population`, `income_index` opcional

        También se aceptan algunos nombres en español como `latitud`, `longitud`, `ciudad`, `poblacion`, `giro`, `actividad`.
        """
    )
