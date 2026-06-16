import re
import json
import os
from typing import List, Dict


class ClauseExtractor:
    """Class to parse policy texts and extract structured clauses based on layout and headings."""

    def __init__(self, pattern: str = r'(?m)^\s*(?:Clause|Section|Sec\.)?\s*(\d+(?:\.\d+)+)\b'):
        """
        Initializes the ClauseExtractor with a regex pattern.

        Args:
            pattern (str): Regex pattern to match clause headings.
        """
        self.pattern = re.compile(pattern)

    def extract(self, text: str) -> List[Dict[str, str]]:
        """
        Extracts clauses and their IDs from the given text.

        Args:
            text (str): Raw text of the policy document.

        Returns:
            List[Dict[str, str]]: List of dictionaries containing 'clause_id' and 'text'.
        """
        if not text:
            return []

        matches = list(self.pattern.finditer(text))
        if not matches:
            # Fallback if no structured clauses are matched
            return [{"clause_id": "FullText", "text": text.strip()}]

        clauses = []

        # Extract preamble if it exists and contains non-whitespace characters
        preamble_text = text[:matches[0].start()].strip()
        if preamble_text:
            clauses.append({
                "clause_id": "Preamble",
                "text": preamble_text
            })

        # Extract each clause
        for i, match in enumerate(matches):
            clause_id = match.group(1)
            start_pos = match.start()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            clause_text = text[start_pos:end_pos].strip()
            clauses.append({
                "clause_id": clause_id,
                "text": clause_text
            })

        return clauses


def split_into_clauses(text: str) -> List[Dict[str, str]]:
    """
    Convenience wrapper function to split text into clauses.
    Maintains backward compatibility with legacy scripts.

    Args:
        text (str): The raw text to split.

    Returns:
        List[Dict[str, str]]: The list of structured clauses.
    """
    extractor = ClauseExtractor()
    return extractor.extract(text)


if __name__ == "__main__":
    # Define file paths
    input_path = os.path.join("data", "extracted_text", "output.txt")
    output_path = os.path.join("data", "structured_clauses.json")

    # Read extracted text
    if os.path.exists(input_path):
        print(f"Reading extracted text from: {input_path}")
        with open(input_path, "r", encoding="utf-8") as f:
            text_data = f.read()

        # Extract clauses
        extractor = ClauseExtractor()
        extracted_clauses = extractor.extract(text_data)

        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Save to JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(extracted_clauses, f, indent=4, ensure_ascii=False)

        print(f"Successfully extracted {len(extracted_clauses)} clauses.")
        print(f"Saved structured clauses to: {output_path}")

        # Display sample clauses
        print("\n--- Sample Clauses (First 5) ---")
        for c in extracted_clauses[:5]:
            print(f"Clause ID: {c['clause_id']}")
            print(f"Text (trunc): {c['text'][:150]}...")
            print("-" * 30)
    else:
        print(f"Error: Input file {input_path} not found.")