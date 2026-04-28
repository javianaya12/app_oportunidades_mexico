"""Data loading, cleaning, classification and geospatial helpers for the MVP."""
from __future__ import annotations

from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import time
import unicodedata
import numpy as np
import pandas as pd

REQUIRED_BUSINESS_COLUMNS = {"business_type", "city", "latitude", "longitude"}
REQUIRED_ZONE_COLUMNS = {"zone_id", "zone_name", "city", "latitude", "longitude", "population"}

COLUMN_ALIASES = {
    "lat": "latitude", "latitud": "latitude", "latitud_geo": "latitude",
    "lon": "longitude", "lng": "longitude", "longitud": "longitude", "longitud_geo": "longitude",
    "tipo": "business_type", "giro": "business_type", "actividad": "business_type",
    "nombre_act": "business_type", "clase_actividad": "business_type",
    "ciudad": "city", "municipio": "city", "nomb_mun": "city", "localidad": "locality",
    "entidad": "state", "nom_ent": "state",
    "poblacion": "population", "población": "population",
    "nombre": "business_name", "nom_estab": "business_name",
    "razon_social": "business_name", "razón_social": "business_name", "raz_social": "business_name",
    "direccion": "address", "dirección": "address", "domicilio": "address",
    "nom_vial": "street", "numero_ext": "external_number", "colonia": "neighborhood",
}

BUSINESS_KEYWORDS = {
    "Farmacia": ["farmacia", "medicamento", "botica"],
    "Restaurante": ["restaurante", "comida", "taquer", "cocina", "cafeter", "pizzeria", "pizza", "hamburgues", "torta"],
    "Ferretería": ["ferreter", "herramienta", "materiales"],
    "Gimnasio": ["gimnasio", "fitness", "entrenamiento", "acondicionamiento físico"],
    "Tienda de conveniencia": ["oxxo", "kiosko", "tienda", "conveniencia", "abarrotes"],
}


def _normalize_text_value(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = " ".join(text.split())
    return text.title()


def load_dataset(uploaded_file, expected_sheet: str | None = None) -> pd.DataFrame:
    if uploaded_file is None:
        return None

    name = getattr(uploaded_file, "name", "").lower()

    if name.endswith(".csv"):
        encodings = ["utf-8", "utf-8-sig", "latin1", "cp1252", "iso-8859-1"]
        last_error = None
        for encoding in encodings:
            try:
                uploaded_file.seek(0)
                return pd.read_csv(
                    uploaded_file,
                    encoding=encoding,
                    sep=None,
                    engine="python",
                    on_bad_lines="skip",
                )
            except Exception as exc:
                last_error = exc
        raise ValueError("No se pudo leer el CSV. Intenta guardarlo como CSV UTF-8 o revisa el archivo original.") from last_error

    if name.endswith((".xlsx", ".xls")):
        uploaded_file.seek(0)
        return pd.read_excel(uploaded_file, sheet_name=expected_sheet or 0)

    raise ValueError("Formato no soportado. Usa CSV, XLSX o XLS.")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()
    clean.columns = [
        str(c).strip().replace("\ufeff", "").lower().replace(" ", "_").replace("-", "_")
        for c in clean.columns
    ]
    clean = clean.rename(columns={c: COLUMN_ALIASES.get(c, c) for c in clean.columns})

    if "city" in clean.columns:
        clean["city"] = clean["city"].map(_normalize_text_value)
    if "state" in clean.columns:
        clean["state"] = clean["state"].map(_normalize_text_value)
    if "business_type" in clean.columns:
        clean["business_type"] = clean["business_type"].astype(str).str.strip()
    return clean


def validate_columns(df: pd.DataFrame, required: Iterable[str], dataset_name: str) -> list[str]:
    missing = sorted(set(required) - set(df.columns))
    if missing:
        return [f"{dataset_name}: faltan columnas requeridas: {', '.join(missing)}"]
    return []


def geocode_missing_coordinates(df: pd.DataFrame, max_rows: int = 25, pause_seconds: float = 1.1) -> pd.DataFrame:
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
        if current_value and current_value.lower() not in ["nan", "otro", "sin clasificar", "none"]:
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
        b = b[b["city"].astype(str).str.casefold() == selected_city.casefold()]
        z = z[z["city"].astype(str).str.casefold() == selected_city.casefold()]
    if selected_type != "Todos":
        b = b[b["business_type"].astype(str) == selected_type]
    return b, z


def haversine_distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
    lat2_rad, lon2_rad = np.radians(lat2), np.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))
