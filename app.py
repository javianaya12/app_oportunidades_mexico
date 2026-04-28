from __future__ import annotations

from io import BytesIO
from pathlib import Path
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

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
from src.report_utils import generate_opportunity_report

st.set_page_config(page_title="Mapa de Oportunidades México", page_icon="🗺️", layout="wide")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
MAX_MARKERS = 1000


@st.cache_data(show_spinner=False)
def load_sample_data():
    business_path = DATA_DIR / "negocios_simulados.csv"
    zones_path = DATA_DIR / "zonas_poblacion_simuladas.csv"
    if not business_path.exists() or not zones_path.exists():
        create_sample_files(DATA_DIR)
    return pd.read_csv(business_path), pd.read_csv(zones_path)


@st.cache_data(show_spinner="Cargando y limpiando dataset...", max_entries=5)
def load_and_prepare_from_bytes(file_bytes: bytes, file_name: str, dataset_kind: str, enable_geocoding: bool = False) -> pd.DataFrame:
    """Load, normalize and clean uploaded files using Streamlit cache."""
    bio = BytesIO(file_bytes)
    bio.name = file_name
    raw = load_dataset(bio)
    normalized = normalize_columns(raw)

    if enable_geocoding:
        normalized = geocode_missing_coordinates(normalized, max_rows=25)

    cleaned = clean_coordinates(normalized)
    if dataset_kind == "business":
        cleaned = classify_businesses(cleaned)
    return cleaned


def style_level(value: str) -> str:
    if value == "Alta":
        return "background-color: #dcfce7; color: #166534; font-weight: 700"
    if value == "Media":
        return "background-color: #fef9c3; color: #854d0e; font-weight: 700"
    if value == "Baja":
        return "background-color: #fee2e2; color: #991b1b; font-weight: 700"
    return ""


def public_ranking_view(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "zone_name", "city", "population", "competition_count", "saturation_ratio",
        "nearest_competitor_km", "opportunity_score", "opportunity_level", "recommendation",
    ]
    available = [c for c in cols if c in df.columns]
    view = df[available].copy()
    rename = {
        "zone_name": "Zona",
        "city": "Ciudad",
        "population": "Población",
        "competition_count": "Competidores cercanos",
        "saturation_ratio": "Competidores / 10k hab.",
        "nearest_competitor_km": "Rival más cercano (km)",
        "opportunity_score": "Score",
        "opportunity_level": "Nivel",
        "recommendation": "Recomendación",
    }
    view = view.rename(columns=rename)
    if "Competidores / 10k hab." in view.columns:
        view["Competidores / 10k hab."] = pd.to_numeric(view["Competidores / 10k hab."], errors="coerce").round(1)
    return view


st.title("🗺️ SaaS MVP | Mapa de oportunidades de negocio en México")
st.caption("Carga datos de negocios y población, analiza competencia cercana y detecta zonas con alto potencial comercial.")

with st.sidebar:
    with st.expander("1. Datos", expanded=True):
        use_sample = st.toggle("Usar datasets simulados", value=True)

        if st.button("Generar datasets de prueba"):
            create_sample_files(DATA_DIR)
            st.success("Datasets simulados creados en la carpeta data/.")

        business_file = None
        zones_file = None
        if not use_sample:
            business_file = st.file_uploader("Dataset de negocios CSV/Excel", type=["csv", "xlsx", "xls"])
            zones_file = st.file_uploader("Dataset de zonas/población CSV/Excel", type=["csv", "xlsx", "xls"])

    with st.expander("2. Filtros", expanded=True):
        st.caption("Los filtros aparecen después de cargar los datos.")

    with st.expander("3. Configuración avanzada", expanded=False):
        radius_km = st.slider("Radio de competencia cercana (km)", min_value=0.5, max_value=10.0, value=2.0, step=0.5)
        enable_geocoding = st.toggle("Geocodificar direcciones sin lat/lon (demo)", value=False)
        st.caption("Usa geocodificación solo para archivos pequeños. DENUE ya trae coordenadas.")

try:
    if use_sample:
        businesses_raw, zones_raw = load_sample_data()
        businesses = classify_businesses(clean_coordinates(normalize_columns(businesses_raw)))
        zones = clean_coordinates(normalize_columns(zones_raw))
    else:
        if business_file is None or zones_file is None:
            st.info("Carga ambos datasets o activa 'Usar datasets simulados' para ver el MVP funcionando.")
            st.markdown(
                """
                ### Cómo empezar
                1. Sube un archivo de negocios, por ejemplo DENUE de INEGI.  
                2. Sube un archivo de zonas/población.  
                3. Selecciona ciudad, giro y radio para generar el ranking.  

                **Tip:** para datos grandes, primero filtra por ciudad y tipo de negocio.
                """
            )
            st.stop()
        businesses = load_and_prepare_from_bytes(business_file.getvalue(), business_file.name, "business", enable_geocoding)
        zones = load_and_prepare_from_bytes(zones_file.getvalue(), zones_file.name, "zones", False)
except Exception as exc:
    st.error(f"Error cargando o limpiando los archivos: {exc}")
    st.stop()

errors = []
errors.extend(validate_columns(businesses, REQUIRED_BUSINESS_COLUMNS, "Dataset de negocios"))
errors.extend(validate_columns(zones, REQUIRED_ZONE_COLUMNS, "Dataset de población/zonas"))
if errors:
    for error in errors:
        st.error(error)
    st.stop()

if "income_index" not in zones.columns:
    st.warning("El dataset de zonas no tiene `income_index`; se usará un valor neutro para ese factor del score.")

cities = ["Todas"] + sorted(set(businesses["city"].dropna().astype(str)) | set(zones["city"].dropna().astype(str)))
business_types = ["Todos"] + sorted(businesses["business_type"].dropna().astype(str).unique().tolist())

with st.sidebar:
    with st.expander("2. Filtros", expanded=True):
        selected_city = st.selectbox("Ciudad", cities)
        selected_type = st.selectbox("Tipo de negocio", business_types)

filtered_businesses, filtered_zones = apply_filters(businesses, zones, selected_city, selected_type)

try:
    zones_competition = calculate_competition_by_zone(filtered_businesses, filtered_zones, radius_km)
    scored_zones = calculate_opportunity_score(zones_competition)
except Exception as exc:
    st.error(f"Error calculando score de oportunidad: {exc}")
    st.stop()

high_opportunities = int((scored_zones["opportunity_level"] == "Alta").sum()) if not scored_zones.empty else 0
avg_score = float(scored_zones["opportunity_score"].mean()) if not scored_zones.empty else 0
high_pct = (high_opportunities / len(scored_zones) * 100) if len(scored_zones) else 0

metric_1, metric_2, metric_3, metric_4, metric_5 = st.columns(5)
metric_1.metric("Negocios filtrados", f"{len(filtered_businesses):,}")
metric_2.metric("Zonas analizadas", f"{len(scored_zones):,}")
metric_3.metric("Oportunidades altas", f"{high_opportunities:,}", delta=f"{high_pct:.0f}% de zonas")
metric_4.metric("Score promedio", f"{avg_score:.1f}/100")
metric_5.metric("Radio analizado", f"{radius_km:.1f} km")

if len(filtered_businesses) > MAX_MARKERS:
    st.caption(
        f"Para mantener el mapa ágil, se muestran hasta {MAX_MARKERS:,} negocios en el mapa, "
        f"pero el cálculo de competencia usa los {len(filtered_businesses):,} registros filtrados."
    )

left, right = st.columns([1.45, 1])

with left:
    st.subheader("Mapa interactivo")
    fmap = build_opportunity_map(filtered_businesses, scored_zones, selected_type, max_markers=MAX_MARKERS)
    st_folium(fmap, width=None, height=650)

with right:
    st.subheader("Ranking de zonas")
    ranking_view = public_ranking_view(scored_zones)
    if ranking_view.empty:
        st.info("No hay zonas disponibles para los filtros seleccionados.")
    else:
        styled = ranking_view.style.applymap(style_level, subset=["Nivel"]) if "Nivel" in ranking_view.columns else ranking_view
        st.dataframe(styled, use_container_width=True, height=460)

    st.subheader("Exportar")
    report_markdown_preview = generate_opportunity_report(
        scored_zones=scored_zones,
        selected_business_type=selected_type,
        selected_city=selected_city,
        radius_km=radius_km,
        visible_businesses_count=len(filtered_businesses),
    )
    excel_bytes = to_excel_bytes(scored_zones)
    pdf_bytes = to_pdf_bytes(
        scored_zones,
        selected_city=selected_city,
        selected_type=selected_type,
        radius_km=radius_km,
        report_text=report_markdown_preview,
    )
    st.download_button(
        "Descargar Excel",
        data=excel_bytes,
        file_name="ranking_oportunidades_mexico.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=scored_zones.empty,
    )
    st.download_button(
        "Descargar PDF",
        data=pdf_bytes,
        file_name="reporte_oportunidades_mexico.pdf",
        mime="application/pdf",
        disabled=scored_zones.empty,
    )

st.divider()
report_markdown = generate_opportunity_report(
    scored_zones=scored_zones,
    selected_business_type=selected_type,
    selected_city=selected_city,
    radius_km=radius_km,
    visible_businesses_count=len(filtered_businesses),
)
st.markdown(report_markdown)
st.download_button(
    "Descargar reporte de hallazgos TXT",
    data=report_markdown.encode("utf-8"),
    file_name="hallazgos_recomendaciones.txt",
    mime="text/plain",
)

st.divider()
st.subheader("Cómo interpretar el score")
st.write(
    "El score combina demanda potencial, saturación relativa de competencia, distancia al rival más cercano "
    "e índice de ingreso si está disponible. La lógica central es: alta demanda potencial + baja saturación "
    "del mercado = mayor oportunidad."
)

with st.expander("Formato mínimo esperado de los datasets"):
    st.markdown(
        """
        **Dataset de negocios:** `business_name`, `business_type`, `city`, `address`, `latitude`, `longitude`  
        **Dataset de zonas/población:** `zone_id`, `zone_name`, `city`, `latitude`, `longitude`, `population`, `income_index` opcional

        También se aceptan algunos nombres en español/INEGI como `latitud`, `longitud`, `municipio`, `nom_estab`, `nombre_act`, `poblacion`.
        """
    )
