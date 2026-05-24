import json
import pickle
import numpy as np
import faiss



index = faiss.read_index(
    "data/faiss_index.bin"
)



with open(
    "data/vectorizer.pkl",
    "rb"
) as f:

    vectorizer = pickle.load(f)



with open(
    "data/clause_mapping.json",
    "r",
    encoding="utf-8"
) as f:

    clauses = json.load(f)


def search(query, top_k=5):

    query_vector = vectorizer.transform(
        [query]
    )

    query_dense = query_vector.toarray().astype(
        'float32'
    )

    distances, indices = index.search(
        query_dense,
        top_k
    )

    results = []

    for i, idx in enumerate(indices[0]):

        results.append({

            "distance": float(
                distances[0][i]
            ),

            "clause": clauses[idx]
        })

    return results


if __name__ == "__main__":

    query = input(
        "\nEnter Regulatory Trigger:\n\n"
    )

    results = search(query)

    print("\nMost Relevant Clauses:\n")

    for r in results:

        print(
            f"Clause {r['clause']['clause_id']}"
        )

        print(
            f"Distance: {r['distance']:.4f}"
        )

        print(
            r['clause']['text']
        )

        print("\n-----------------\n")