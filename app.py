"""Folium map utilities."""
from __future__ import annotations

import folium
from folium.plugins import HeatMap, MarkerCluster
import pandas as pd

LEVEL_COLORS = {
    "Alta": "green",
    "Media": "orange",
    "Baja": "red",
}


def build_opportunity_map(businesses: pd.DataFrame, scored_zones: pd.DataFrame, selected_type: str) -> folium.Map:
    """Create an interactive OpenStreetMap/Folium map."""
    if not scored_zones.empty:
        center = [scored_zones["latitude"].mean(), scored_zones["longitude"].mean()]
    elif not businesses.empty:
        center = [businesses["latitude"].mean(), businesses["longitude"].mean()]
    else:
        center = [23.6345, -102.5528]  # Mexico center-ish

    fmap = folium.Map(location=center, zoom_start=11 if not scored_zones.empty else 5, tiles="OpenStreetMap")

    zone_layer = folium.FeatureGroup(name="Zonas de oportunidad", show=True)
    for _, row in scored_zones.iterrows():
        color = LEVEL_COLORS.get(row["opportunity_level"], "gray")
        popup_html = f"""
        <b>{row['zone_name']}</b><br>
        Ciudad: {row['city']}<br>
        Score: {row['opportunity_score']} / 100<br>
        Nivel: {row['opportunity_level']}<br>
        Población: {int(row['population']):,}<br>
        Competidores cercanos: {int(row['competition_count'])}<br>
        Recomendación: {row['recommendation']}
        """
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=10 + (row["opportunity_score"] / 12),
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.35,
            popup=folium.Popup(popup_html, max_width=360),
            tooltip=f"{row['zone_name']} | Score {row['opportunity_score']}",
        ).add_to(zone_layer)
    zone_layer.add_to(fmap)

    heat_points = scored_zones[["latitude", "longitude", "opportunity_score"]].dropna().values.tolist()
    if heat_points:
        HeatMap(heat_points, name="Heatmap de oportunidad", radius=28, blur=18, min_opacity=0.25).add_to(fmap)

    business_layer = folium.FeatureGroup(name=f"Negocios existentes: {selected_type}", show=True)
    cluster = MarkerCluster().add_to(business_layer)
    for _, row in businesses.iterrows():
        name = row.get("business_name", "Negocio")
        popup_html = f"""
        <b>{name}</b><br>
        Tipo: {row.get('business_type', 'N/D')}<br>
        Ciudad: {row.get('city', 'N/D')}<br>
        Dirección: {row.get('address', 'N/D')}
        """
        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{name} | {row.get('business_type', '')}",
            icon=folium.Icon(color="blue", icon="briefcase", prefix="fa"),
        ).add_to(cluster)
    business_layer.add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap
