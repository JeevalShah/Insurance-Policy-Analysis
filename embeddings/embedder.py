import json
import os
import numpy as np
import faiss
import ollama
from typing import List, Dict, Tuple


class PolicyEmbedder:
    """Class to manage policy text embedding generation and FAISS vector index creation."""

    def __init__(self, model_name: str = "nomic-embed-text"):
        """
        Initializes the PolicyEmbedder with the embedding model.

        Args:
            model_name (str): Name of the embedding model to use with Ollama.
        """
        self.model_name = model_name

    def generate_embeddings(self, clauses: List[Dict[str, str]]) -> Tuple[np.ndarray, List[Dict[str, str]]]:
        """
        Generates embeddings for each clause and returns the vectors and the ordered clause list.

        Args:
            clauses (List[Dict[str, str]]): List of clause dictionaries containing 'clause_id' and 'text'.

        Returns:
            Tuple[np.ndarray, List[Dict[str, str]]]: Tuple of:
                - numpy array of embeddings (float32, shape [N, dimension])
                - ordered list of clauses matching the embedding indices (each maps to FAISS index position)
        """
        embeddings = []
        valid_clauses = []

        for idx, clause in enumerate(clauses):
            text = clause.get("text", "").strip()
            if not text:
                continue

            try:
                # Generate embedding via Ollama
                response = ollama.embeddings(
                    model=self.model_name,
                    prompt=text
                )
                embedding = response.get("embedding")
                if embedding:
                    embeddings.append(embedding)
                    valid_clauses.append(clause)
            except Exception as e:
                print(f"Warning: Failed to generate embedding for clause {clause.get('clause_id')}: {e}")

        if not embeddings:
            raise ValueError("No embeddings were generated. Ensure clauses are valid and Ollama is running.")

        vectors = np.array(embeddings, dtype="float32")
        return vectors, valid_clauses

    def build_index(self, vectors: np.ndarray) -> faiss.IndexFlatL2:
        """
        Creates a FAISS index from the given embedding vectors.

        Args:
            vectors (np.ndarray): NumPy array of embeddings.

        Returns:
            faiss.IndexFlatL2: The built FAISS index.
        """
        dimension = vectors.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(vectors)
        return index

    def save_index_and_mapping(
        self,
        index: faiss.Index,
        clauses: List[Dict[str, str]],
        index_path: str,
        mapping_path: str
    ) -> None:
        """
        Saves the FAISS index and the 1-to-1 index-to-clause metadata mapping file.

        Args:
            index (faiss.Index): The built FAISS index.
            clauses (List[Dict[str, str]]): List of clause dictionaries.
            index_path (str): File path where the FAISS index should be saved.
            mapping_path (str): File path where the clause mapping JSON should be saved.
        """
        # Ensure target directories exist
        os.makedirs(os.path.dirname(os.path.abspath(index_path)), exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(mapping_path)), exist_ok=True)

        # Write FAISS index
        faiss.write_index(index, index_path)

        # Write JSON clause mapping
        with open(mapping_path, "w", encoding="utf-8") as f:
            json.dump(clauses, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    # Define file paths
    clauses_input_path = os.path.join("data", "structured_clauses.json")
    faiss_index_output_path = os.path.join("data", "faiss_index.bin")
    clause_mapping_output_path = os.path.join("data", "clause_mapping.json")

    # Load structured clauses
    if os.path.exists(clauses_input_path):
        print(f"Loading structured clauses from: {clauses_input_path}")
        with open(clauses_input_path, "r", encoding="utf-8") as f:
            clauses_data = json.load(f)

        print(f"Generating embeddings for {len(clauses_data)} clauses...")
        embedder = PolicyEmbedder()

        try:
            # Generate embeddings and the corresponding aligned clause list
            vectors, aligned_clauses = embedder.generate_embeddings(clauses_data)

            # Build FAISS index
            print(f"Building FAISS vector index with dimension {vectors.shape[1]}...")
            faiss_index = embedder.build_index(vectors)

            # Save the outputs
            print(f"Saving FAISS index to: {faiss_index_output_path}")
            print(f"Saving clause mapping metadata to: {clause_mapping_output_path}")
            embedder.save_index_and_mapping(
                faiss_index,
                aligned_clauses,
                faiss_index_output_path,
                clause_mapping_output_path
            )

            print(f"\nStored {faiss_index.ntotal} semantic embeddings successfully.")
        except Exception as e:
            print(f"Error during embedding generation or indexing: {e}")
    else:
        print(f"Error: Input file {clauses_input_path} not found. Please run the clause splitter first.")