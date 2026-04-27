"""Data loading, cleaning, classification and geospatial helpers for the MVP."""
from __future__ import annotations

from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import time
import numpy as np
import pandas as pd

REQUIRED_BUSINESS_COLUMNS = {"business_type", "city", "latitude", "longitude"}
REQUIRED_ZONE_COLUMNS = {"zone_id", "zone_name", "city", "latitude", "longitude", "population"}

COLUMN_ALIASES = {
    "lat": "latitude", "latitud": "latitude",
    "lon": "longitude", "lng": "longitude", "longitud": "longitude",
    "tipo": "business_type", "giro": "business_type", "actividad": "business_type",
    "ciudad": "city", "municipio": "city",
    "poblacion": "population", "población": "population",
    "nombre": "business_name", "razon_social": "business_name", "razón_social": "business_name",
    "direccion": "address", "dirección": "address",
}

BUSINESS_KEYWORDS = {
    "Farmacia": ["farmacia", "medicamento", "botica"],
    "Restaurante": ["restaurante", "comida", "taquer", "cocina", "cafeter"],
    "Ferretería": ["ferreter", "herramienta", "materiales"],
    "Gimnasio": ["gimnasio", "fitness", "entrenamiento"],
    "Tienda de conveniencia": ["oxxo", "kiosko", "tienda", "conveniencia", "abarrotes"],
}


def load_dataset(uploaded_file, expected_sheet: str | None = None) -> pd.DataFrame:
    name = getattr(uploaded_file, "name", "")
    if name.lower().endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file, sheet_name=expected_sheet or 0)
    raise ValueError("Formato no soportado. Usa CSV, XLSX o XLS.")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()
    clean.columns = [str(c).strip().lower().replace(" ", "_") for c in clean.columns]
    clean = clean.rename(columns={c: COLUMN_ALIASES.get(c, c) for c in clean.columns})
    return clean


def validate_columns(df: pd.DataFrame, required: Iterable[str], dataset_name: str) -> list[str]:
    missing = sorted(set(required) - set(df.columns))
    if missing:
        return [f"{dataset_name}: faltan columnas requeridas: {', '.join(missing)}"]
    return []


def geocode_missing_coordinates(df: pd.DataFrame, max_rows: int = 25, pause_seconds: float = 1.1) -> pd.DataFrame:
    """Geocode missing lat/lon with OpenStreetMap Nominatim for small demos only."""
    clean = df.copy()
    if "address" not in clean.columns:
        return clean
    if "latitude" not in clean.columns:
        clean["latitude"] = np.nan
    if "longitude" not in clean.columns:
        clean["longitude"] = np.nan
    missing_indexes = clean[clean["latitude"].isna() | clean["longitude"].isna()].head(max_rows).index
    for idx in missing_indexes:
        query = str(clean.at[idx, "address"])
        if not query or query.lower() == "nan":
            continue
        params = urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "mx"})
        request = Request(
            f"https://nominatim.openstreetmap.org/search?{params}",
            headers={"User-Agent": "mvp-oportunidades-mexico/1.0"},
        )
        try:
            with urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload:
                clean.at[idx, "latitude"] = float(payload[0]["lat"])
                clean.at[idx, "longitude"] = float(payload[0]["lon"])
        except Exception:
            pass
        time.sleep(pause_seconds)
    return clean


def clean_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()
    for col in ["latitude", "longitude"]:
        if col in clean.columns:
            clean[col] = pd.to_numeric(clean[col], errors="coerce")
        else:
            clean[col] = np.nan
    clean = clean.dropna(subset=["latitude", "longitude"])
    clean = clean[(clean["latitude"].between(14, 33)) & (clean["longitude"].between(-119, -86))]
    return clean


def classify_businesses(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()
    if "business_type" not in clean.columns:
        clean["business_type"] = "Otro"
    text_cols = [c for c in ["business_name", "address", "business_type"] if c in clean.columns]
    combined = clean[text_cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower()

    def classify(text: str, current: str) -> str:
        current_value = str(current).strip()
        if current_value and current_value.lower() not in ["nan", "otro", "sin clasificar"]:
            return current_value.title()
        for category, keywords in BUSINESS_KEYWORDS.items():
            if any(k in text for k in keywords):
                return category
        return "Otro"

    clean["business_type"] = [classify(t, c) for t, c in zip(combined, clean["business_type"])]
    return clean


def apply_filters(businesses: pd.DataFrame, zones: pd.DataFrame, selected_city: str, selected_type: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    b = businesses.copy()
    z = zones.copy()
    if selected_city != "Todas":
        b = b[b["city"] == selected_city]
        z = z[z["city"] == selected_city]
    if selected_type != "Todos":
        b = b[b["business_type"] == selected_type]
    return b, z


def haversine_distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
    lat2_rad, lon2_rad = np.radians(lat2), np.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))
