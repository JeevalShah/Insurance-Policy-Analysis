import re
import json


CLAUSE_PATTERN = r'(\d+\.\d+(?:\.\d+)*)'


def split_into_clauses(text):

    splits = re.split(CLAUSE_PATTERN, text)

    clauses = []

    for i in range(1, len(splits), 2):

        clause_id = splits[i]

        clause_text = splits[i + 1].strip()

        clauses.append({
            "clause_id": clause_id,
            "text": clause_text
        })

    return clauses


if __name__ == "__main__":

    with open(
        "data/extracted_text/output.txt",
        "r",
        encoding="utf-8"
    ) as f:

        text = f.read()

    clauses = split_into_clauses(text)

    with open(
        "data/structured_clauses.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            clauses,
            f,
            indent=4,
            ensure_ascii=False
        )

    print(f"Extracted {len(clauses)} clauses")