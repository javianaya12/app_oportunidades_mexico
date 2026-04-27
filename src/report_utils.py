"""Automatic business opportunity report utilities."""
from __future__ import annotations

import pandas as pd


def _fmt_int(value) -> str:
    try:
        return f"{int(float(value)):,}"
    except Exception:
        return "N/D"


def _fmt_float(value, decimals: int = 1) -> str:
    try:
        return f"{float(value):,.{decimals}f}"
    except Exception:
        return "N/D"


def _safe_value(row: pd.Series, column: str, default="N/D"):
    if column not in row.index:
        return default
    value = row.get(column, default)
    if pd.isna(value):
        return default
    return value


def _competition_label(value: float, low_limit: float, high_limit: float) -> str:
    if value <= low_limit:
        return "baja"
    if value >= high_limit:
        return "alta"
    return "media"


def _build_zone_sentence(row: pd.Series, radius_km: float, low_comp: float, high_comp: float, position: int) -> str:
    zone_name = _safe_value(row, "zone_name")
    city = _safe_value(row, "city")
    population = _fmt_int(_safe_value(row, "population", 0))
    competition = _fmt_int(_safe_value(row, "competition_count", 0))
    score = _fmt_float(_safe_value(row, "opportunity_score", 0), 1)
    level = _safe_value(row, "opportunity_level", "N/D")
    comp_label = _competition_label(float(_safe_value(row, "competition_count", 0)), low_comp, high_comp)

    return (
        f"{position}. **{zone_name} ({city})** — Score **{score}/100**, nivel **{level}**. "
        f"Población estimada: **{population}**. Competidores cercanos en {radius_km:.1f} km: "
        f"**{competition}**; saturación **{comp_label}**."
    )


def generate_opportunity_report(
    scored_zones: pd.DataFrame,
    selected_business_type: str,
    selected_city: str,
    radius_km: float,
    visible_businesses_count: int,
) -> str:
    """Return a markdown report with findings and practical recommendations."""
    if scored_zones is None or scored_zones.empty:
        return (
            "### 📋 Reporte automático\n\n"
            "No hay zonas suficientes para generar hallazgos. Carga datos de negocios y zonas/población, "
            "o ajusta los filtros para ampliar el análisis."
        )

    df = scored_zones.copy()
    df["competition_count"] = pd.to_numeric(df.get("competition_count", 0), errors="coerce").fillna(0)
    df["population"] = pd.to_numeric(df.get("population", 0), errors="coerce").fillna(0)
    df["opportunity_score"] = pd.to_numeric(df.get("opportunity_score", 0), errors="coerce").fillna(0)
    df = df.sort_values("opportunity_score", ascending=False).reset_index(drop=True)

    business_label = selected_business_type if selected_business_type != "Todos" else "todos los giros disponibles"
    city_label = selected_city if selected_city != "Todas" else "todas las ciudades cargadas"

    low_comp = float(df["competition_count"].quantile(0.25)) if len(df) > 1 else float(df["competition_count"].iloc[0])
    high_comp = float(df["competition_count"].quantile(0.75)) if len(df) > 1 else float(df["competition_count"].iloc[0])

    top_zones = df.head(3)
    low_zones = df.tail(min(3, len(df))).sort_values("opportunity_score", ascending=True)
    best = df.iloc[0]
    worst = df.iloc[-1]

    high_count = int((df.get("opportunity_level", "") == "Alta").sum()) if "opportunity_level" in df.columns else int((df["opportunity_score"] >= 70).sum())
    avg_score = df["opportunity_score"].mean()
    avg_competition = df["competition_count"].mean()
    total_population = df["population"].sum()

    report_lines = []
    report_lines.append("### 📋 Reporte automático de hallazgos y recomendaciones")
    report_lines.append("")
    report_lines.append(f"**Giro analizado:** {business_label}")
    report_lines.append(f"**Ciudad/filtro:** {city_label}")
    report_lines.append(f"**Radio de competencia:** {radius_km:.1f} km")
    report_lines.append(f"**Negocios considerados en el filtro:** {visible_businesses_count:,}")
    report_lines.append(f"**Zonas analizadas:** {len(df):,}")
    report_lines.append("")

    report_lines.append("#### Resumen ejecutivo")
    report_lines.append(
        f"Se detectaron **{high_count} zonas de oportunidad alta**. El score promedio de las zonas analizadas es "
        f"**{avg_score:.1f}/100** y la competencia promedio dentro del radio seleccionado es de "
        f"**{avg_competition:.1f} negocios cercanos**. La población total estimada en las zonas evaluadas es "
        f"de **{total_population:,.0f} personas**."
    )
    report_lines.append("")

    report_lines.append("#### Zonas con mayor potencial")
    for idx, (_, row) in enumerate(top_zones.iterrows(), start=1):
        report_lines.append(_build_zone_sentence(row, radius_km, low_comp, high_comp, idx))
    report_lines.append("")

    report_lines.append("#### Mejor recomendación")
    best_zone = _safe_value(best, "zone_name")
    best_city = _safe_value(best, "city")
    best_score = _fmt_float(_safe_value(best, "opportunity_score", 0), 1)
    best_pop = _fmt_int(_safe_value(best, "population", 0))
    best_comp = _fmt_int(_safe_value(best, "competition_count", 0))
    report_lines.append(
        f"La zona más atractiva es **{best_zone} ({best_city})**, con un score de **{best_score}/100**. "
        f"Tiene una población estimada de **{best_pop}** y **{best_comp} competidores cercanos** en un radio de "
        f"{radius_km:.1f} km. Conviene priorizar esta zona para una validación comercial más profunda: renta, "
        f"flujo peatonal/vehicular, visibilidad del local, accesos y poder adquisitivo."
    )
    report_lines.append("")

    report_lines.append("#### Zonas de menor prioridad o mayor riesgo")
    for idx, (_, row) in enumerate(low_zones.iterrows(), start=1):
        report_lines.append(_build_zone_sentence(row, radius_km, low_comp, high_comp, idx))
    report_lines.append("")

    worst_zone = _safe_value(worst, "zone_name")
    worst_city = _safe_value(worst, "city")
    worst_score = _fmt_float(_safe_value(worst, "opportunity_score", 0), 1)
    report_lines.append(
        f"La zona menos prioritaria según el score actual es **{worst_zone} ({worst_city})**, con "
        f"**{worst_score}/100**. No significa que sea imposible abrir ahí, pero sí que requiere mayor cautela "
        f"porque la relación entre población y competencia cercana es menos favorable frente a otras zonas."
    )
    report_lines.append("")

    report_lines.append("#### Recomendaciones prácticas")
    report_lines.append("- Priorizar las zonas con score alto para una visita física y validación de locales disponibles.")
    report_lines.append("- Revisar la competencia real: precios, horarios, reseñas, tamaño del local y posicionamiento.")
    report_lines.append("- Ajustar el radio según el giro: 1–2 km para negocios de barrio; 3–5 km para servicios más especializados.")
    report_lines.append("- Complementar el análisis con renta estimada, tráfico, nivel socioeconómico y ticket promedio esperado.")
    report_lines.append("- No tomar el score como decisión final; usarlo como filtro inicial para decidir dónde investigar primero.")

    return "\n".join(report_lines)
