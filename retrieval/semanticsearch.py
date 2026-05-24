import json
import numpy as np
import faiss
import ollama


# LOAD INDEX
index = faiss.read_index(
    "data/faiss_index.bin"
)


# LOAD CLAUSES
with open(
    "data/clause_mapping.json",
    "r",
    encoding="utf-8"
) as f:

    clauses = json.load(f)


def search(query, top_k=5):

    response = ollama.embeddings(

        model="nomic-embed-text",

        prompt=query
    )

    query_embedding = np.array(
        [response["embedding"]],
        dtype='float32'
    )

    distances, indices = index.search(
        query_embedding,
        top_k
    )

    results = []

    MAX_DISTANCE = 400

    for i, idx in enumerate(indices[0]):

     distance = float(
        distances[0][i]
     )

     if distance <= MAX_DISTANCE:

        results.append({

            "distance": distance,

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