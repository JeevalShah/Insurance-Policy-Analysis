from sentence_transformers import SentenceTransformer
import json
import faiss
import numpy as np


model = SentenceTransformer(
    'all-MiniLM-L6-v2'
)


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


embeddings = model.encode(texts)


dimension = embeddings.shape[1]

index = faiss.IndexFlatL2(dimension)

index.add(
    np.array(embeddings).astype('float32')
)

print(
    f"Stored {index.ntotal} clause embeddings"
)