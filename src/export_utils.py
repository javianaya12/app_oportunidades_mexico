"""Export utilities for Excel and PDF."""
from __future__ import annotations

from io import BytesIO
from datetime import datetime
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.units import inch

PUBLIC_RENAME = {
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


def _public_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "zone_name", "city", "population", "competition_count", "saturation_ratio",
        "nearest_competitor_km", "opportunity_score", "opportunity_level", "recommendation",
    ]
    available = [c for c in cols if c in df.columns]
    out = df[available].copy()
    return out.rename(columns=PUBLIC_RENAME)


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    public = _public_df(df)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        public.to_excel(writer, index=False, sheet_name="ranking_oportunidades")
        workbook = writer.book
        worksheet = writer.sheets["ranking_oportunidades"]
        header_format = workbook.add_format({"bold": True, "bg_color": "#1f2937", "font_color": "#FFFFFF"})
        for col_num, value in enumerate(public.columns.values):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, min(max(len(str(value)) + 4, 14), 42))
    return output.getvalue()


def to_pdf_bytes(
    df: pd.DataFrame,
    title: str = "Reporte de oportunidades de negocio",
    selected_city: str = "Todas",
    selected_type: str = "Todos",
    radius_km: float = 2.0,
    report_text: str | None = None,
) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=42,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], textColor=colors.HexColor("#1f2937")))

    elements = []
    elements.append(Paragraph(title, styles["Title"]))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["BodyText"]))
    elements.append(Paragraph(f"Ciudad/filtro: {selected_city} | Giro: {selected_type} | Radio: {radius_km:.1f} km", styles["BodyText"]))
    elements.append(Spacer(1, 14))

    if df is None or df.empty:
        elements.append(Paragraph("No hay zonas suficientes para generar el reporte.", styles["BodyText"]))
        doc.build(elements)
        return output.getvalue()

    high_count = int((df.get("opportunity_level", "") == "Alta").sum()) if "opportunity_level" in df.columns else 0
    avg_score = pd.to_numeric(df.get("opportunity_score", pd.Series(dtype=float)), errors="coerce").mean()
    elements.append(Paragraph("Resumen ejecutivo", styles["Section"]))
    elements.append(Paragraph(
        f"Se analizaron {len(df):,} zonas. Se detectaron {high_count:,} oportunidades altas. "
        f"El score promedio fue de {avg_score:.1f}/100. Este reporte usa el score como filtro inicial; "
        "la decisión final debe validarse con visita física, renta, tráfico y competencia real.",
        styles["BodyText"],
    ))
    elements.append(Spacer(1, 12))

    public = _public_df(df).head(12)
    table_data = [list(public.columns)] + public.astype(str).values.tolist()
    table = Table(table_data, repeatRows=1, colWidths=[1.25*inch, 0.8*inch, 0.65*inch, 0.8*inch, 0.8*inch, 0.8*inch, 0.55*inch, 0.55*inch, 1.6*inch])
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
    ])
    for idx, level in enumerate(public.get("Nivel", []), start=1):
        if level == "Alta":
            style.add("BACKGROUND", (7, idx), (7, idx), colors.HexColor("#dcfce7"))
        elif level == "Media":
            style.add("BACKGROUND", (7, idx), (7, idx), colors.HexColor("#fef9c3"))
        elif level == "Baja":
            style.add("BACKGROUND", (7, idx), (7, idx), colors.HexColor("#fee2e2"))
    table.setStyle(style)
    elements.append(Paragraph("Ranking de zonas", styles["Section"]))
    elements.append(table)

    if report_text:
        elements.append(PageBreak())
        elements.append(Paragraph("Hallazgos y recomendaciones", styles["Section"]))
        for line in report_text.splitlines():
            clean = line.replace("###", "").replace("####", "").replace("**", "").strip()
            if clean:
                elements.append(Paragraph(clean, styles["Small"]))
                elements.append(Spacer(1, 4))

    doc.build(elements)
    return output.getvalue()
