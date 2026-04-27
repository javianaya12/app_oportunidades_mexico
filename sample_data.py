"""Opportunity scoring logic."""
from __future__ import annotations

import numpy as np
import pandas as pd
from .data_processing import haversine_distance_km


def minmax(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce").fillna(0)
    min_v, max_v = series.min(), series.max()
    if max_v == min_v:
        return pd.Series(np.ones(len(series)) * 0.5, index=series.index)
    return (series - min_v) / (max_v - min_v)


def calculate_competition_by_zone(businesses: pd.DataFrame, zones: pd.DataFrame, radius_km: float) -> pd.DataFrame:
    """Count businesses around each population zone within a radius."""
    result = zones.copy()
    counts = []
    nearest_distances = []

    for _, zone in result.iterrows():
        if businesses.empty:
            counts.append(0)
            nearest_distances.append(None)
            continue
        distances = haversine_distance_km(
            zone["latitude"], zone["longitude"],
            businesses["latitude"].to_numpy(), businesses["longitude"].to_numpy()
        )
        counts.append(int((distances <= radius_km).sum()))
        nearest_distances.append(round(float(distances.min()), 2) if len(distances) else None)

    result["competition_count"] = counts
    result["nearest_competitor_km"] = nearest_distances
    return result


def calculate_opportunity_score(zones_with_competition: pd.DataFrame) -> pd.DataFrame:
    """Score: high population + low competition + income index = high opportunity."""
    df = zones_with_competition.copy()
    df["population_norm"] = minmax(df["population"])
    df["competition_norm"] = minmax(df["competition_count"])

    if "income_index" in df.columns:
        df["income_norm"] = minmax(df["income_index"])
    else:
        df["income_norm"] = 0.5

    # Main formula: population potential is more important than income in this MVP.
    df["opportunity_score"] = (
        0.60 * df["population_norm"] +
        0.25 * (1 - df["competition_norm"]) +
        0.15 * df["income_norm"]
    ) * 100
    df["opportunity_score"] = df["opportunity_score"].round(1)

    conditions = [
        df["opportunity_score"] >= 70,
        df["opportunity_score"].between(45, 69.999),
        df["opportunity_score"] < 45,
    ]
    labels = ["Alta", "Media", "Baja"]
    df["opportunity_level"] = np.select(conditions, labels, default="Baja")
    df["recommendation"] = df.apply(build_recommendation, axis=1)
    return df.sort_values("opportunity_score", ascending=False).reset_index(drop=True)


def build_recommendation(row: pd.Series) -> str:
    level = row.get("opportunity_level", "Media")
    pop = int(row.get("population", 0))
    comp = int(row.get("competition_count", 0))
    if level == "Alta":
        return f"Zona con alto potencial: población aproximada de {pop:,} y solo {comp} competidores cercanos."
    if level == "Media":
        return f"Zona interesante, pero requiere validación comercial: {pop:,} habitantes y {comp} competidores cercanos."
    return f"Zona de menor prioridad: relación población/competencia poco favorable con {comp} competidores cercanos."
