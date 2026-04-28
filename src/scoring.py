"""Opportunity scoring logic optimized for larger DENUE datasets."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from .data_processing import haversine_distance_km

EARTH_RADIUS_KM = 6371.0


def minmax(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce").fillna(0)
    min_v, max_v = series.min(), series.max()
    if len(series) == 0:
        return pd.Series(dtype=float)
    if max_v == min_v:
        return pd.Series(np.ones(len(series)) * 0.5, index=series.index)
    return (series - min_v) / (max_v - min_v)


def _latlon_to_unit_sphere(coords: np.ndarray) -> np.ndarray:
    """Convert lat/lon degrees to 3D unit-sphere coordinates for spatial indexing."""
    lat = np.radians(coords[:, 0])
    lon = np.radians(coords[:, 1])
    x = np.cos(lat) * np.cos(lon)
    y = np.cos(lat) * np.sin(lon)
    z = np.sin(lat)
    return np.column_stack((x, y, z))


def calculate_competition_by_zone(businesses: pd.DataFrame, zones: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    """
    Count businesses around each zone within a radius.

    Uses scipy.spatial.cKDTree instead of a pure Python O(n*m) loop. This makes
    the app much faster with real DENUE files.
    """
    result = zones.copy()

    if result.empty:
        result["competition_count"] = []
        result["nearest_competitor_km"] = []
        return result

    result["competition_count"] = 0
    result["nearest_competitor_km"] = np.nan

    if businesses is None or businesses.empty:
        return result

    required = {"latitude", "longitude"}
    if not required.issubset(businesses.columns) or not required.issubset(result.columns):
        return result

    biz = businesses.dropna(subset=["latitude", "longitude"]).copy()
    zdf = result.dropna(subset=["latitude", "longitude"]).copy()

    if biz.empty or zdf.empty:
        return result

    biz_coords = biz[["latitude", "longitude"]].to_numpy(dtype=float)
    zone_coords = zdf[["latitude", "longitude"]].to_numpy(dtype=float)

    biz_xyz = _latlon_to_unit_sphere(biz_coords)
    zone_xyz = _latlon_to_unit_sphere(zone_coords)

    tree = cKDTree(biz_xyz)
    angular_radius = radius_km / EARTH_RADIUS_KM
    chord_radius = 2 * np.sin(angular_radius / 2)

    counts = []
    nearest_distances = []

    biz_lat = biz["latitude"].to_numpy(dtype=float)
    biz_lon = biz["longitude"].to_numpy(dtype=float)

    for zone_row, zone_xyz_row in zip(zdf.itertuples(), zone_xyz):
        idxs = tree.query_ball_point(zone_xyz_row, chord_radius)
        counts.append(len(idxs))

        if idxs:
            distances = haversine_distance_km(
                zone_row.latitude,
                zone_row.longitude,
                biz_lat[idxs],
                biz_lon[idxs],
            )
            nearest_distances.append(round(float(np.min(distances)), 2))
        else:
            nearest_distances.append(None)

    result.loc[zdf.index, "competition_count"] = counts
    result.loc[zdf.index, "nearest_competitor_km"] = nearest_distances
    return result


def calculate_opportunity_score(zones_with_competition: pd.DataFrame) -> pd.DataFrame:
    """
    Score v2: demand potential + relative saturation + income + access gap.

    Better than using raw competition_count alone because it contextualizes
    competition against population: competitors per 10,000 inhabitants.
    """
    df = zones_with_competition.copy()

    if df.empty:
        for col in [
            "competition_count", "nearest_competitor_km", "saturation_ratio",
            "demand_potential", "demand_norm", "saturation_norm", "income_norm",
            "accessibility_bonus", "opportunity_score", "opportunity_level", "recommendation",
        ]:
            if col not in df.columns:
                df[col] = pd.Series(dtype="object")
        return df

    df["population"] = pd.to_numeric(df.get("population", 0), errors="coerce").fillna(0)
    df["competition_count"] = pd.to_numeric(df.get("competition_count", 0), errors="coerce").fillna(0)
    df["nearest_competitor_km"] = pd.to_numeric(df.get("nearest_competitor_km", np.nan), errors="coerce")

    if "income_index" in df.columns:
        df["income_index"] = pd.to_numeric(df["income_index"], errors="coerce").fillna(0.5)
    else:
        df["income_index"] = 0.5

    df["demand_potential"] = df["population"] * df["income_index"]
    df["demand_norm"] = minmax(df["demand_potential"])

    population_units = (df["population"] / 10_000).replace(0, np.nan)
    df["saturation_ratio"] = (df["competition_count"] / population_units).replace([np.inf, -np.inf], np.nan).fillna(0)
    df["saturation_norm"] = minmax(df["saturation_ratio"])
    df["income_norm"] = minmax(df["income_index"])

    df["accessibility_bonus"] = (df["nearest_competitor_km"].fillna(99) > 3).astype(float)

    df["opportunity_score"] = (
        0.45 * df["demand_norm"] +
        0.35 * (1 - df["saturation_norm"]) +
        0.10 * df["income_norm"] +
        0.10 * df["accessibility_bonus"]
    ) * 100
    df["opportunity_score"] = df["opportunity_score"].round(1)

    conditions = [
        df["opportunity_score"] >= 70,
        df["opportunity_score"].between(45, 69.999),
        df["opportunity_score"] < 45,
    ]
    labels = ["Alta", "Media", "Baja"]
    df["opportunity_level"] = np.select(conditions, labels, default="Baja")
    df["recommendation"] = [build_recommendation(row) for _, row in df.iterrows()]

    return df.sort_values("opportunity_score", ascending=False).reset_index(drop=True)


def build_recommendation(row: pd.Series) -> str:
    level = row.get("opportunity_level", "Media")
    pop = int(float(row.get("population", 0) or 0))
    comp = int(float(row.get("competition_count", 0) or 0))
    saturation = float(row.get("saturation_ratio", 0) or 0)

    if level == "Alta":
        return (
            f"Zona con alto potencial: población aproximada de {pop:,}, "
            f"{comp} competidores cercanos y saturación de {saturation:.1f} por cada 10k habitantes."
        )
    if level == "Media":
        return (
            f"Zona interesante, pero requiere validación comercial: {pop:,} habitantes, "
            f"{comp} competidores cercanos y saturación de {saturation:.1f} por cada 10k habitantes."
        )
    return (
        f"Zona de menor prioridad: relación población/competencia menos favorable, "
        f"con {comp} competidores cercanos y saturación de {saturation:.1f} por cada 10k habitantes."
    )
