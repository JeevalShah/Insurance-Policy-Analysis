import re
import json


CLAUSE_PATTERN = r'Clause\s+(\d+\.\d+)'


def split_into_clauses(text):

    matches = list(
        re.finditer(CLAUSE_PATTERN, text)
    )

    clauses = []

    for i in range(len(matches)):

        clause_id = matches[i].group(1)

        start = matches[i].end()

        if i + 1 < len(matches):

            end = matches[i + 1].start()

        else:

            end = len(text)

        clause_text = text[start:end].strip()

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

    print(f"\nExtracted {len(clauses)} clauses\n")

    for clause in clauses[:5]:

        print(clause)
        print()