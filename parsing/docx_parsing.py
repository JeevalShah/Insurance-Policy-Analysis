from docx import Document


def extract_docx_text(docx_path):

    doc = Document(docx_path)

    full_text = []

    for para in doc.paragraphs:

        text = para.text.strip()

        if text:

            full_text.append(text)

    return "\n".join(full_text)


if __name__ == "__main__":

    text = extract_docx_text(
        "data/raw/DOC_1.docx"
    )

    with open(
        "data/extracted_text/output.txt",
        "w",
        encoding="utf-8"
    ) as f:

        f.write(text)

    print("DOCX Extraction Complete")