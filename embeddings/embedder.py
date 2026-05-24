import json
import pickle
import numpy as np
import faiss

from sklearn.feature_extraction.text import TfidfVectorizer


# LOAD CLAUSES
with open(
    "data/structured_clauses.json",
    "r",
    encoding="utf-8"
) as f:

    clauses = json.load(f)


# EXTRACT TEXTS
texts = [
    clause["text"]
    for clause in clauses
]


# TF-IDF VECTORIZATION
vectorizer = TfidfVectorizer()

X = vectorizer.fit_transform(texts)


# CONVERT TO DENSE FLOAT32
dense_vectors = X.toarray().astype('float32')


# CREATE FAISS INDEX
dimension = dense_vectors.shape[1]

index = faiss.IndexFlatL2(dimension)

index.add(dense_vectors)


# SAVE FAISS INDEX
faiss.write_index(
    index,
    "data/faiss_index.bin"
)


# SAVE VECTORIZER
with open(
    "data/vectorizer.pkl",
    "wb"
) as f:

    pickle.dump(vectorizer, f)


# SAVE CLAUSE MAPPING
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


print(f"\nStored {index.ntotal} vectors in FAISS")