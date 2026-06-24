import json
import os
import logging
import concurrent.futures
import numpy as np
import faiss
import ollama
from typing import List, Dict, Tuple, Optional, Any

# Configure standard logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("PolicyEmbedder")


class PolicyEmbedder:
    """Manages concurrent embedding generation via Ollama and FAISS indexing for policy clauses."""

    def __init__(self, model_name: str = "nomic-embed-text", max_workers: int = 4):
        """
        Initializes the PolicyEmbedder.

        Args:
            model_name (str): The name of the embedding model to use with Ollama.
            max_workers (int): Number of parallel worker threads for Ollama embeddings.
        """
        self.model_name = model_name
        self.max_workers = max_workers

    def _embed_single(self, clause: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], List[float]]]:
        """
        Helper method to generate an embedding for a single clause.
        Executed in parallel by thread workers.
        """
        text = clause.get("text", "").strip()
        if not text:
            return None

        try:
            response = ollama.embeddings(
                model=self.model_name,
                prompt=text
            )
            embedding = response.get("embedding")
            if embedding:
                return (clause, embedding)
        except Exception as e:
            logger.warning(f"Failed to generate embedding for clause {clause.get('clause_id')}: {e}")
        return None

    def generate_embeddings(self, clauses: List[Dict[str, Any]]) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """
        Generates embeddings concurrently for a list of clauses.
        Preserves relative sequence mapping.

        Args:
            clauses (List[Dict[str, Any]]): List of clause dicts with 'clause_id', 'parent_id', 'text'.

        Returns:
            Tuple[np.ndarray, List[Dict[str, Any]]]: A tuple containing:
                - numpy array of embeddings (float32, [N, dimension])
                - ordered list of metadata corresponding to successfully indexed vectors.
        """
        if not clauses:
            logger.warning("Empty clause list passed to generate_embeddings.")
            return np.empty((0, 0), dtype="float32"), []

        embeddings: List[List[float]] = []
        valid_clauses: List[Dict[str, Any]] = []

        logger.info(f"Generating embeddings for {len(clauses)} clauses using {self.max_workers} threads...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit tasks to executor to preserve submission order
            futures = [executor.submit(self._embed_single, clause) for clause in clauses]

            for future in futures:
                try:
                    result = future.result()
                    if result is not None:
                        clause, embedding = result
                        embeddings.append(embedding)
                        valid_clauses.append(clause)
                except Exception as e:
                    logger.error(f"Error resolving future result: {e}")

        if not embeddings:
            logger.error("Zero clauses were successfully embedded.")
            raise ValueError("No embeddings generated. Ensure Ollama is running and the model is loaded.")

        vectors = np.array(embeddings, dtype="float32")
        logger.info(f"Successfully generated {len(valid_clauses)} embeddings out of {len(clauses)} chunks.")
        return vectors, valid_clauses

    def build_index(self, vectors: np.ndarray) -> faiss.IndexFlatL2:
        """
        Builds a FAISS IndexFlatL2 for L2 similarity search.

        Args:
            vectors (np.ndarray): NumPy array of embeddings, shape [N, dimension].

        Returns:
            faiss.IndexFlatL2: The built FAISS vector index.
        """
        if vectors.size == 0 or vectors.shape[0] == 0:
            raise ValueError("Cannot build FAISS index with empty vectors.")
        
        dimension = vectors.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(vectors)
        logger.info(f"Built FAISS index with {index.ntotal} vectors of dimension {dimension}.")
        return index

    def save_index_and_mapping(
        self,
        index: faiss.Index,
        clauses: List[Dict[str, Any]],
        index_path: str,
        mapping_path: str
    ) -> None:
        """
        Saves the FAISS index and the 1-to-1 index-to-clause metadata mapping file.

        Args:
            index (faiss.Index): The built FAISS index.
            clauses (List[Dict[str, Any]]): List of clause dictionaries.
            index_path (str): File path where the FAISS index should be saved.
            mapping_path (str): File path where the clause mapping JSON should be saved.
        """
        try:
            # Ensure directories exist
            os.makedirs(os.path.dirname(os.path.abspath(index_path)), exist_ok=True)
            os.makedirs(os.path.dirname(os.path.abspath(mapping_path)), exist_ok=True)

            # Write FAISS index
            faiss.write_index(index, index_path)
            logger.info(f"Saved FAISS index to {index_path}")

            # Structure mappings to include faiss_id 1-to-1 matching position
            clause_mappings = []
            for idx, clause in enumerate(clauses):
                clause_mappings.append({
                    "faiss_id": idx,
                    "clause_id": clause.get("clause_id"),
                    "parent_id": clause.get("parent_id"),
                    "text": clause.get("text")
                })

            # Write JSON clause mapping
            with open(mapping_path, "w", encoding="utf-8") as f:
                json.dump(clause_mappings, f, indent=4, ensure_ascii=False)
            logger.info(f"Saved {len(clause_mappings)} clause mappings to {mapping_path}")

        except Exception as e:
            logger.error(f"Failed to save index or mapping: {e}")
            raise

    def secure_search(
        self,
        index: faiss.Index,
        query_vector: np.ndarray,
        clauses: List[Dict[str, Any]],
        k: int = 5,
        distance_threshold: float = 1.0
    ) -> List[Dict[str, Any]]:
        """
        Performs nearest neighbor search in FAISS index with L2 distance filtering.

        Args:
            index (faiss.Index): The FAISS index.
            query_vector (np.ndarray): NumPy array of query embedding, shape (1, dimension).
            clauses (List[Dict[str, Any]]): The 1-to-1 mapped clause list.
            k (int): Number of nearest neighbors to retrieve.
            distance_threshold (float): Strict L2 distance threshold limit.

        Returns:
            List[Dict[str, Any]]: Filtered search result list.
        """
        try:
            query_vector = np.array(query_vector, dtype="float32")
            if len(query_vector.shape) == 1:
                query_vector = np.expand_dims(query_vector, axis=0)

            distances, indices = index.search(query_vector, k)

            results = []
            for i, idx in enumerate(indices[0]):
                if idx == -1 or idx >= len(clauses):
                    continue

                distance = float(distances[0][i])
                if distance <= distance_threshold:
                    clause_info = clauses[idx]
                    results.append({
                        "faiss_id": idx,
                        "distance": distance,
                        "clause_id": clause_info.get("clause_id"),
                        "parent_id": clause_info.get("parent_id"),
                        "text": clause_info.get("text")
                    })
            logger.info(f"Search matched {len(results)} items within L2 threshold of {distance_threshold}.")
            return results
        except Exception as e:
            logger.error(f"Error occurred during secure_search: {e}")
            return []


if __name__ == "__main__":
    clauses_input_path = os.path.join("data", "structured_clauses.json")
    faiss_index_output_path = os.path.join("data", "faiss_index.bin")
    clause_mapping_output_path = os.path.join("data", "clause_mapping.json")

    # Load structured clauses safely
    clauses_data = []
    if os.path.exists(clauses_input_path):
        try:
            logger.info(f"Loading structured clauses from: {clauses_input_path}")
            with open(clauses_input_path, "r", encoding="utf-8") as f:
                clauses_data = json.load(f)
        except Exception as err:
            logger.error(f"Failed to read or parse structured clauses file: {err}")
    else:
        logger.error(f"Structured clauses file not found at: {clauses_input_path}")

    # Check for empty clauses list edge case
    if not clauses_data:
        logger.warning("Zero structured clauses available. Ingestion halted.")
    else:
        logger.info(f"Loaded {len(clauses_data)} clauses. Starting embedding process...")
        embedder = PolicyEmbedder(max_workers=4)

        try:
            # Concurrently generate embeddings
            vectors, valid_clauses = embedder.generate_embeddings(clauses_data)

            # Build FAISS L2 Index
            faiss_index = embedder.build_index(vectors)

            # Save FAISS Index and Mapping
            embedder.save_index_and_mapping(
                faiss_index,
                valid_clauses,
                faiss_index_output_path,
                clause_mapping_output_path
            )
            logger.info("Ingestion completed successfully.")

        except Exception as ex:
            logger.error(f"Ingestion process failed: {ex}")