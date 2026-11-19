"""Generate docs/AI-Services-Catalog-Table.docx: one table of service name, category, description.

Reuses the curated SERVICES list from generate_ai_services_catalog.py.
"""

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from generate_ai_services_catalog import CATEGORIES, SERVICES, set_run_font, shade_cell

OUT = Path(__file__).resolve().parent / "AI-Services-Catalog-Table.docx"

# Services present in the repo but missing from the curated list.
EXTRA = [
    (
        "RoleAwareTimelineService",
        "Role-Aware Timeline Service",
        "8040",
        "Clinical Documentation & Summaries",
        "Reads one chart extract and returns a shared timeline, a clinical summary, and role-specific highlights "
        "for a nurse, radiologist, or cardiologist.",
    ),
]

WIDTHS = [Cm(6.0), Cm(5.0), Cm(14.0)]
NAVY = RGBColor(0x1F, 0x3A, 0x5F)


def set_col_widths(table):
    for row in table.rows:
        for cell, width in zip(row.cells, WIDTHS):
            cell.width = width


def repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def main() -> None:
    services = list(SERVICES) + EXTRA
    order = {c: i for i, c in enumerate(CATEGORIES)}
    services.sort(key=lambda s: (order.get(s[3], 99), s[1].lower()))

    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    for side in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, side, Cm(1.5))

    title = doc.add_paragraph()
    set_run_font(title.add_run("AI Services Catalog"), size=22, bold=True, color=NAVY)

    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    for i, h in enumerate(["Service", "Category", "Description"]):
        cell = table.rows[0].cells[i]
        cell.text = h
        for run in cell.paragraphs[0].runs:
            set_run_font(run, size=10, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
        shade_cell(cell, "1F3A5F")
    repeat_header(table.rows[0])

    for n, (_folder, name, _port, cat, desc) in enumerate(services, 1):
        cells = table.add_row().cells
        for j, v in enumerate([name, cat, desc]):
            cells[j].text = v
            for run in cells[j].paragraphs[0].runs:
                set_run_font(run, size=9, bold=(j == 0))
        if n % 2 == 0:
            for c in cells:
                shade_cell(c, "F2F5F9")

    set_col_widths(table)
    doc.save(OUT)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(f"Services: {len(services)}")


if __name__ == "__main__":
    main()
