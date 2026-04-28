"""Folium map utilities optimized for real DENUE data."""
from __future__ import annotations

import html
import folium
from folium.plugins import HeatMap, MarkerCluster
import pandas as pd

LEVEL_COLORS = {
    "Alta": "green",
    "Media": "orange",
    "Baja": "red",
}


def _safe_text(value) -> str:
    if pd.isna(value):
        return "N/D"
    return html.escape(str(value))


def build_opportunity_map(
    businesses: pd.DataFrame,
    scored_zones: pd.DataFrame,
    selected_type: str,
    max_markers: int = 1000,
) -> folium.Map:
    """Create an interactive OpenStreetMap/Folium map with a safe marker limit."""
    if not scored_zones.empty:
        center = [scored_zones["latitude"].mean(), scored_zones["longitude"].mean()]
        zoom = 11
    elif businesses is not None and not businesses.empty:
        center = [businesses["latitude"].mean(), businesses["longitude"].mean()]
        zoom = 10
    else:
        center = [23.6345, -102.5528]
        zoom = 5

    fmap = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap")

    zone_layer = folium.FeatureGroup(name="Zonas de oportunidad", show=True)
    for _, row in scored_zones.iterrows():
        color = LEVEL_COLORS.get(row.get("opportunity_level", "Baja"), "gray")
        saturation = row.get("saturation_ratio", None)
        saturation_text = "N/D" if pd.isna(saturation) else f"{float(saturation):.1f} por 10k hab."
        popup_html = f"""
        <b>{_safe_text(row.get('zone_name'))}</b><br>
        Ciudad: {_safe_text(row.get('city'))}<br>
        Score: {_safe_text(row.get('opportunity_score'))} / 100<br>
        Nivel: {_safe_text(row.get('opportunity_level'))}<br>
        Población: {int(float(row.get('population', 0) or 0)):,}<br>
        Competidores cercanos: {int(float(row.get('competition_count', 0) or 0))}<br>
        Saturación: {html.escape(saturation_text)}<br>
        Rival más cercano: {_safe_text(row.get('nearest_competitor_km'))} km<br>
        Recomendación: {_safe_text(row.get('recommendation'))}
        """
        score = float(row.get("opportunity_score", 0) or 0)
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=9 + (score / 13),
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.35,
            popup=folium.Popup(popup_html, max_width=390),
            tooltip=f"{_safe_text(row.get('zone_name'))} | Score {score:.1f}",
        ).add_to(zone_layer)
    zone_layer.add_to(fmap)

    heat_points = scored_zones[["latitude", "longitude", "opportunity_score"]].dropna().values.tolist()
    if heat_points:
        HeatMap(heat_points, name="Heatmap de oportunidad", radius=28, blur=18, min_opacity=0.25).add_to(fmap)

    business_layer_name = f"Negocios existentes: {selected_type}"
    businesses_to_plot = businesses if businesses is not None else pd.DataFrame()
    if len(businesses_to_plot) > max_markers:
        businesses_to_plot = businesses_to_plot.sample(max_markers, random_state=42)
        business_layer_name += f" (muestra {max_markers:,})"

    business_layer = folium.FeatureGroup(name=business_layer_name, show=True)
    cluster = MarkerCluster().add_to(business_layer)
    for _, row in businesses_to_plot.iterrows():
        name = row.get("business_name", "Negocio")
        popup_html = f"""
        <b>{_safe_text(name)}</b><br>
        Tipo: {_safe_text(row.get('business_type', 'N/D'))}<br>
        Ciudad: {_safe_text(row.get('city', 'N/D'))}<br>
        Dirección: {_safe_text(row.get('address', 'N/D'))}
        """
        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{_safe_text(name)} | {_safe_text(row.get('business_type', ''))}",
            icon=folium.Icon(color="blue", icon="briefcase", prefix="fa"),
        ).add_to(cluster)
    business_layer.add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap
