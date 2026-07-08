import logging
from typing import List, Dict

import pdfplumber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("PDFParsing")


def extract_text(pdf_path: str) -> List[Dict[str, str]]:
    """
    Extracts text from a PDF, page by page, preserving reading order.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        List[Dict[str, str]]: One dict per page: {"page": int, "text": str}
    """
    pages: List[Dict[str, str]] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                raw = page.extract_text(x_tolerance=1.5, y_tolerance=3) or ""
                cleaned = _strip_headers_footers(raw)
                pages.append({"page": i, "text": cleaned})
        logger.info(f"Extracted {len(pages)} pages from {pdf_path}")
    except Exception as e:
        logger.error(f"Failed to parse PDF {pdf_path}: {e}")
        raise

    return pages


def _strip_headers_footers(text: str) -> str:
    """Removes common boilerplate lines (page numbers, repeated running headers)."""
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append(line)
            continue
        # Drop lone page-number lines like "Page 3 of 12" or "3"
        if stripped.lower().startswith("page ") and "of" in stripped.lower():
            continue
        if stripped.isdigit() and len(stripped) <= 4:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)
