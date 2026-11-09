"""Small generated PDF manuals for tests (Cyrillic text via PyMuPDF's HTML box)."""

import pymupdf

SPINDLE_PAGE = (
    "Подшипники шпинделя. Если шпиндель гудит или воет на высоких оборотах, проверьте смазку "
    "подшипников шпинделя и люфт. Смазку подшипников выполняйте каждые 500 часов работы."
)
COOLANT_PAGE = (
    "Система охлаждения. При слабой подаче СОЖ очистите фильтр насоса и проверьте уровень жидкости."
)


def manual_pdf(pages: list[str]) -> bytes:
    """One PDF page per string; an empty string makes a page without text (like a scan)."""
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_htmlbox(pymupdf.Rect(50, 50, 550, 800), f"<p>{text}</p>")
    return document.tobytes()


def standard_manual() -> bytes:
    """Page 1 title, page 2 spindle bearings, page 3 coolant, page 4 empty (scanned)."""
    title = "Паспорт станка. Общие сведения, назначение и технические характеристики фрезерного станка."
    return manual_pdf([title, SPINDLE_PAGE, COOLANT_PAGE, ""])
