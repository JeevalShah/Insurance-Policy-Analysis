import re
import json


# CLAUSE_PATTERN = r'Clause\s+(\d+\.\d+)'


def split_into_clauses(text):

    chunk_size = 1000

    clauses = []

    for i in range(0, len(text), chunk_size):

        chunk = text[i:i+chunk_size]

        clauses.append({
            "clause_id": f"C{i//chunk_size + 1}",
            "text": chunk.strip()
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

    print(f"\nExtracted {len(clauses)} clauses\n")

    for clause in clauses[:5]:

        print(clause)
        print()