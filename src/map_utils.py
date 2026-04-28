"""Map utilities for the opportunity analysis app.

This version is optimized for larger DENUE datasets and safely escapes text
shown in Folium popups.
"""
from __future__ import annotations

import html
from typing import Any

import folium
import numpy as np
import pandas as pd
from folium.plugins import HeatMap, MarkerCluster


def _safe_text(value: Any, default: str = "") -> str:
    """Return a safe escaped string for HTML popups.

    pd.isna() can return arrays for non-scalar objects, so this function avoids
    boolean ambiguity errors when values are lists, arrays or pandas objects.
    """
    if value is None:
        return default

    if isinstance(value, (list, tuple, set, dict, np.ndarray, pd.Series, pd.DataFrame)):
        value = str(value)

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    return html.escape(str(value))


def _safe_number(value: Any, default: float = 0.0) -> float:
    """Convert values to float without breaking on missing or malformed values."""
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _get_map_center(businesses: pd.DataFrame, zones: pd.DataFrame) -> tuple[float, float]:
    """Find a reasonable center for the map."""
    lat_values = []
    lon_values = []

    for df in [zones, businesses]:
        if df is not None and not df.empty and {"latitude", "longitude"}.issubset(df.columns):
            lat_values.extend(pd.to_numeric(df["latitude"], errors="coerce").dropna().tolist())
            lon_values.extend(pd.to_numeric(df["longitude"], errors="coerce").dropna().tolist())

    if lat_values and lon_values:
        return float(np.mean(lat_values)), float(np.mean(lon_values))

    # Center of Mexico fallback
    return 23.6345, -102.5528


def _zone_color(level: str) -> str:
    level = str(level).strip().lower()
    if level == "alta":
        return "green"
    if level == "media":
        return "orange"
    return "red"


def build_opportunity_map(
    businesses: pd.DataFrame,
    zones: pd.DataFrame,
    selected_type: str = "Todos",
    max_markers: int = 1000,
):
    """Build Folium map with opportunity zones, heatmap and business markers.

    The score calculation can use the full filtered dataset, but this function
    limits displayed business markers to keep the map fast and stable.
    """
    businesses = businesses.copy() if businesses is not None else pd.DataFrame()
    zones = zones.copy() if zones is not None else pd.DataFrame()

    center_lat, center_lon = _get_map_center(businesses, zones)

    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    # Opportunity zones
    if not zones.empty and {"latitude", "longitude"}.issubset(zones.columns):
        zones_group = folium.FeatureGroup(name="Zonas de oportunidad", show=True)

        for _, row in zones.iterrows():
            lat = _safe_number(row.get("latitude"))
            lon = _safe_number(row.get("longitude"))
            if not (14 <= lat <= 33 and -119 <= lon <= -86):
                continue

            zone_name = _safe_text(row.get("zone_name", "Zona"))
            city = _safe_text(row.get("city", ""))
            population = _safe_number(row.get("population"))
            competition = int(_safe_number(row.get("competition_count")))
            nearest = row.get("nearest_competitor_km", None)
            nearest_txt = "Sin dato" if nearest is None or pd.isna(nearest) else f"{_safe_number(nearest):.2f} km"
            score = _safe_number(row.get("opportunity_score"))
            level = _safe_text(row.get("opportunity_level", ""))
            saturation = _safe_number(row.get("saturation_ratio", 0))

            color = _zone_color(level)

            popup_html = f"""
            <div style="font-family: Arial; font-size: 13px;">
                <b>{zone_name}</b><br>
                Ciudad: {city}<br>
                Población: {population:,.0f}<br>
                Competidores cercanos: {competition}<br>
                Saturación: {saturation:.2f} competidores / 10k hab.<br>
                Rival más cercano: {nearest_txt}<br>
                Score: <b>{score:.1f}</b><br>
                Nivel: <b>{level}</b>
            </div>
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=12,
                popup=folium.Popup(popup_html, max_width=320),
                tooltip=f"{zone_name} | Score {score:.1f}",
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.25,
                weight=3,
            ).add_to(zones_group)

        zones_group.add_to(fmap)

        # Heatmap based on zone score
        heat_points = []
        for _, row in zones.iterrows():
            lat = _safe_number(row.get("latitude"))
            lon = _safe_number(row.get("longitude"))
            score = _safe_number(row.get("opportunity_score"))
            if 14 <= lat <= 33 and -119 <= lon <= -86:
                heat_points.append([lat, lon, max(score, 1)])

        if heat_points:
            HeatMap(
                heat_points,
                name="Heatmap de oportunidad",
                min_opacity=0.25,
                radius=30,
                blur=25,
                max_zoom=13,
                show=True,
            ).add_to(fmap)

    # Business markers, limited for performance
    if not businesses.empty and {"latitude", "longitude"}.issubset(businesses.columns):
        total_businesses = len(businesses)

        if total_businesses > max_markers:
            businesses_display = businesses.sample(max_markers, random_state=42)
        else:
            businesses_display = businesses

        cluster_name = (
            f"Negocios existentes: {selected_type}"
            if selected_type and selected_type != "Todos"
            else "Negocios existentes: Todos"
        )

        marker_cluster = MarkerCluster(name=cluster_name, show=True)

        for _, row in businesses_display.iterrows():
            lat = _safe_number(row.get("latitude"))
            lon = _safe_number(row.get("longitude"))
            if not (14 <= lat <= 33 and -119 <= lon <= -86):
                continue

            name = _safe_text(row.get("business_name", row.get("nom_estab", "Negocio")))
            btype = _safe_text(row.get("business_type", row.get("nombre_act", "")))
            city = _safe_text(row.get("city", row.get("municipio", "")))

            popup_html = f"""
            <div style="font-family: Arial; font-size: 13px;">
                <b>{name}</b><br>
                Giro: {btype}<br>
                Ciudad: {city}
            </div>
            """

            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=name,
                icon=folium.Icon(color="blue", icon="briefcase", prefix="fa"),
            ).add_to(marker_cluster)

        marker_cluster.add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap
