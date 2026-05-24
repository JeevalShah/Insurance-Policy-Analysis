import json
import faiss
import numpy as np
import ollama


# LOAD CLAUSES
with open(
    "data/structured_clauses.json",
    "r",
    encoding="utf-8"
) as f:

    clauses = json.load(f)


texts = [
    clause["text"]
    for clause in clauses
]


embeddings = []


# GENERATE EMBEDDINGS
for text in texts:

    response = ollama.embeddings(

        model="nomic-embed-text",

        prompt=text
    )

    embeddings.append(
        response["embedding"]
    )


# CONVERT TO NUMPY
vectors = np.array(
    embeddings,
    dtype='float32'
)


# CREATE FAISS INDEX
dimension = vectors.shape[1]

index = faiss.IndexFlatL2(dimension)

index.add(vectors)


# SAVE INDEX
faiss.write_index(
    index,
    "data/faiss_index.bin"
)


# SAVE CLAUSE MAP
with open(
    "data/clause_mapping.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        clauses,
        f,
        indent=4,
        ensure_ascii=False
    )


print(
    f"\nStored {index.ntotal} semantic embeddings"
)