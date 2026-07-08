import re
import json
import os
import logging
from typing import List, Dict, Optional

# Configure standard logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("HierarchicalClauseExtractor")


class HierarchicalClauseExtractor:
    """Parses policy documents and extracts clauses hierarchically, preserving parent-child mapping."""

    def __init__(self, pattern: Optional[str] = None):
        """
        Initializes the extractor.

        Args:
            pattern (Optional[str]): Optional custom regex pattern (for legacy compatibility).
        """
        # Set up default extraction patterns
        self.dotted_pattern = re.compile(
            r'^(?:Clause|Section|Sec\.)?\s*(\d+(?:\.\d+)+)\b',
            re.IGNORECASE
        )
        self.section_pattern = re.compile(
            r'^(\d+)\.\s+([A-Z\s\(\)\’\-]{4,})\b'
        )
        self.subsection_pattern = re.compile(
            r'^[a-z]\)\s+SECTION\s+([I|V|X]+)\b',
            re.IGNORECASE
        )
        self.single_digit_pattern = re.compile(
            r'^(\d+)\.\s+(.*)$'
        )

        # Override dotted pattern if custom legacy pattern is provided
        if pattern:
            self.dotted_pattern = re.compile(pattern)

    def extract(self, text: str) -> List[Dict[str, Optional[str]]]:
        """
        Extracts structural clauses and sub-clauses from document text.

        Args:
            text (str): Raw text content of the policy document.

        Returns:
            List[Dict[str, Optional[str]]]: List of dictionaries containing:
                - 'clause_id': The matched clause heading number (e.g. '2.1' or '8.1').
                - 'parent_id': The parent clause number (e.g. '8' or '2') or None.
                - 'text': The text block belonging to this clause.
        """
        if not text or not text.strip():
            logger.warning("Empty text passed to extract. Returning 0 clauses.")
            return []

        lines = text.split("\n")
        clauses: List[Dict[str, Optional[str]]] = []

        current_section: Optional[str] = None
        current_subsection: Optional[str] = None

        current_clause_id: Optional[str] = "Preamble"
        current_clause_text_lines: List[str] = []

        def finalize_clause(next_id: Optional[str]):
            nonlocal current_clause_id, current_clause_text_lines
            clause_text = "\n".join(current_clause_text_lines).strip()

            # Deduce parent clause ID using dot notation
            if current_clause_id:
                parts = current_clause_id.split(".")
                parent_id = ".".join(parts[:-1]) if len(parts) > 2 else None

                if current_clause_id == "Preamble" and not clause_text:
                    pass  # Skip empty preamble
                else:
                    clauses.append({
                        "clause_id": current_clause_id,
                        "parent_id": parent_id,
                        "text": clause_text
                    })

            current_clause_id = next_id
            current_clause_text_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 1. Check dotted heading (e.g., Clause 1.1)
            dotted_match = self.dotted_pattern.match(stripped)
            if dotted_match:
                matched_id = dotted_match.group(1)
                parts = matched_id.split(".")
                current_section = parts[0]
                finalize_clause(matched_id)
                current_clause_text_lines.append(line)
                continue

            # 2. Check main section heading (e.g., 8. CONDITIONS)
            section_match = self.section_pattern.match(stripped)
            if section_match:
                current_section = section_match.group(1)
                current_subsection = None  # Reset subsection context
                finalize_clause(current_section)
                current_clause_text_lines.append(line)
                continue

            # 3. Check subsection heading (e.g., b) SECTION II)
            subsec_match = self.subsection_pattern.match(stripped)
            if subsec_match:
                current_subsection = subsec_match.group(1).upper()
                current_clause_text_lines.append(line)
                continue

            # 4. Check single digit heading (e.g., 1. Notice shall be given...)
            single_match = self.single_digit_pattern.match(stripped)
            if single_match:
                num = single_match.group(1)
                if current_section:
                    if current_section == "2" and current_subsection:
                        if current_subsection == "II":
                            # Section II Clause 1 -> 2.1
                            clause_id = f"2.{num}"
                        else:
                            # Section I Clause 1 -> 2.I.1
                            clause_id = f"2.{current_subsection}.{num}"
                    else:
                        clause_id = f"{current_section}.{num}"
                else:
                    clause_id = num

                finalize_clause(clause_id)
                current_clause_text_lines.append(line)
                continue

            # Otherwise, append normal line to the active clause text
            current_clause_text_lines.append(line)

        # Finalize the remaining text block
        finalize_clause(None)

        # Clean up last item if empty
        if clauses and clauses[-1]["clause_id"] is None:
            clauses.pop()

        logger.info(f"Successfully extracted {len(clauses)} clauses (including preamble/fallback if applicable).")
        return clauses


def split_into_clauses(text: str) -> List[Dict[str, Optional[str]]]:
    """
    Module-level compatibility wrapper function.

    Args:
        text (str): Raw text input.

    Returns:
        List[Dict[str, Optional[str]]]: List of structured clauses.
    """
    extractor = HierarchicalClauseExtractor()
    return extractor.extract(text)


if __name__ == "__main__":
    input_path = os.path.join("data", "extracted_text", "output.txt")
    output_path = os.path.join("data", "structured_clauses.json")

    try:
        if os.path.exists(input_path):
            logger.info(f"Loading policy text from: {input_path}")
            with open(input_path, "r", encoding="utf-8") as f:
                text_data = f.read()

            extractor = HierarchicalClauseExtractor()
            extracted = extractor.extract(text_data)

            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(extracted, f, indent=4, ensure_ascii=False)

            logger.info(f"Saved {len(extracted)} clauses to {output_path}")

            logger.info("Sample clauses:")
            for item in extracted[:3]:
                logger.info(f"ID: {item['clause_id']} | Parent: {item['parent_id']} | Length: {len(item['text'] or '')}")
        else:
            logger.error(f"Input file not found at {input_path}")
    except Exception as ex:
        logger.exception("An unexpected error occurred during execution:")
