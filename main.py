from parsing.pdf_parsing import extract_text
from clause_extraction.clause_split import split_into_clauses


def main():

    pdf_path = "data/raw/sample-policy-sbi.pdf"

    pages = extract_text(pdf_path)

    full_text = ""

    for page in pages:

        full_text += page["text"] + "\n"

    clauses = split_into_clauses(full_text)

    print(f"\nTotal Clauses Extracted: {len(clauses)}\n")

    for clause in clauses[:5]:

        print(clause)
        print()


if __name__ == "__main__":

    main()