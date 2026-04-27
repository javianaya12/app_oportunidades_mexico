"""Export utilities for Excel and PDF."""
from __future__ import annotations

from io import BytesIO
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="ranking_oportunidades")
    return output.getvalue()


def to_pdf_bytes(df: pd.DataFrame, title: str = "Reporte de oportunidades de negocio") -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph(title, styles["Title"]), Spacer(1, 12)]

    summary = (
        "Este reporte resume las zonas con mayor potencial comercial según población, "
        "competencia cercana y el score calculado por la aplicación."
    )
    elements.append(Paragraph(summary, styles["BodyText"]))
    elements.append(Spacer(1, 12))

    cols = ["zone_name", "city", "population", "competition_count", "opportunity_score", "opportunity_level"]
    available_cols = [c for c in cols if c in df.columns]
    table_data = [available_cols] + df[available_cols].head(15).astype(str).values.tolist()
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
    ]))
    elements.append(table)
    doc.build(elements)
    return output.getvalue()
