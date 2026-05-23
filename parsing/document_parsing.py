import pdfplumber
from collections import defaultdict


def remove_consecutive_duplicates(text):

    words = text.split()

    cleaned = []

    prev = None

    for word in words:

        if word != prev:

            cleaned.append(word)

        prev = word

    return " ".join(cleaned)


def reconstruct_lines(words):

    lines = defaultdict(list)

    for word in words:

        y = round(word['top'], 1)

        lines[y].append(word)

    final_text = []

    for y in sorted(lines.keys()):

        line_words = sorted(
            lines[y],
            key=lambda w: w['x0']
        )

        line = " ".join(
            [w['text'] for w in line_words]
        )

        final_text.append(line)

    return "\n".join(final_text)


def extract_text(pdf_path):

    pages_output = []

    with pdfplumber.open(pdf_path) as pdf:

        for page_num, page in enumerate(pdf.pages):

            words = page.extract_words(
                x_tolerance=3,
                y_tolerance=3,
                use_text_flow=True
            )

            filtered = []

            for w in words:

                if w['top'] < 50:
                    continue

                if w['top'] > page.height - 70:
                    continue

                filtered.append(w)

            text = reconstruct_lines(filtered)

            text = remove_consecutive_duplicates(text)

            pages_output.append({
                "page": page_num + 1,
                "text": text
            })

    return pages_output


if __name__ == "__main__":

    pdf_path = "data/raw/sample-policy-sbi.pdf"

    pages = extract_text(pdf_path)

    with open(
        "data/extracted_text/output.txt",
        "w",
        encoding="utf-8"
    ) as f:

        for p in pages:

            f.write(f"\nPAGE {p['page']}\n\n")

            f.write(p["text"])

            f.write("\n\n")

    print("Extraction Complete")