import logging
from typing import List, Dict

import docx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("DOCXParsing")


def extract_text(docx_path: str) -> List[Dict[str, str]]:
    """
    Extracts text from a DOCX file. Returns a single-page-style list so the
    caller can treat DOCX and PDF sources uniformly (`for page in pages`).

    Args:
        docx_path (str): Path to the DOCX file.

    Returns:
        List[Dict[str, str]]: [{"page": 1, "text": full_document_text}]
    """
    try:
        document = docx.Document(docx_path)
        blocks: List[str] = []

        for para in document.paragraphs:
            if para.text.strip():
                blocks.append(para.text)

        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    blocks.append(" | ".join(cells))

        full_text = "\n".join(blocks)
        logger.info(f"Extracted {len(blocks)} text blocks from {docx_path}")
        return [{"page": 1, "text": full_text}]
    except Exception as e:
        logger.error(f"Failed to parse DOCX {docx_path}: {e}")
        raise
