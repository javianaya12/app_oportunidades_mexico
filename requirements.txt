"""Generate small simulated datasets for the SaaS market-opportunity MVP."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd


RNG = np.random.default_rng(42)

CITY_CENTERS = {
    "Colima": {"lat": 19.2433, "lon": -103.7249},
    "Guadalajara": {"lat": 20.6736, "lon": -103.3440},
    "Monterrey": {"lat": 25.6866, "lon": -100.3161},
    "CDMX": {"lat": 19.4326, "lon": -99.1332},
}

BUSINESS_TYPES = ["Farmacia", "Restaurante", "Ferretería", "Gimnasio", "Tienda de conveniencia"]


def _random_points_around(center_lat: float, center_lon: float, n: int, spread: float = 0.045) -> tuple[np.ndarray, np.ndarray]:
    """Return random lat/lon points around a city center."""
    lats = center_lat + RNG.normal(0, spread, n)
    lons = center_lon + RNG.normal(0, spread, n)
    return lats, lons


def generate_businesses(n_per_city: int = 120) -> pd.DataFrame:
    rows = []
    business_id = 1
    for city, center in CITY_CENTERS.items():
        lats, lons = _random_points_around(center["lat"], center["lon"], n_per_city)
        for i in range(n_per_city):
            business_type = RNG.choice(BUSINESS_TYPES, p=[0.22, 0.30, 0.16, 0.12, 0.20])
            rows.append({
                "business_id": business_id,
                "business_name": f"{business_type} {business_id}",
                "business_type": business_type,
                "city": city,
                "address": f"Calle Simulada {business_id}, {city}, México",
                "latitude": round(float(lats[i]), 6),
                "longitude": round(float(lons[i]), 6),
            })
            business_id += 1
    return pd.DataFrame(rows)


def generate_population_zones(zones_per_city: int = 18) -> pd.DataFrame:
    rows = []
    zone_id = 1
    for city, center in CITY_CENTERS.items():
        lats, lons = _random_points_around(center["lat"], center["lon"], zones_per_city, spread=0.055)
        for i in range(zones_per_city):
            population = int(RNG.integers(1800, 22000))
            income_index = round(float(RNG.uniform(0.35, 0.95)), 2)
            rows.append({
                "zone_id": f"ZONA-{zone_id:03d}",
                "zone_name": f"Zona {zone_id:03d} - {city}",
                "city": city,
                "latitude": round(float(lats[i]), 6),
                "longitude": round(float(lons[i]), 6),
                "population": population,
                "income_index": income_index,
            })
            zone_id += 1
    return pd.DataFrame(rows)


def create_sample_files(output_dir: str | Path = "data") -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    businesses = generate_businesses()
    zones = generate_population_zones()
    businesses.to_csv(output_path / "negocios_simulados.csv", index=False, encoding="utf-8-sig")
    zones.to_csv(output_path / "zonas_poblacion_simuladas.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(output_path / "datasets_simulados_mexico.xlsx", engine="openpyxl") as writer:
        businesses.to_excel(writer, sheet_name="negocios", index=False)
        zones.to_excel(writer, sheet_name="zonas_poblacion", index=False)


if __name__ == "__main__":
    create_sample_files("data")
