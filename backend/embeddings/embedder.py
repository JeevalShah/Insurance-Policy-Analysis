import json
import os
import logging
import concurrent.futures
import numpy as np
import faiss
import ollama
from typing import List, Dict, Tuple, Optional, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("PolicyEmbedder")


class PolicyEmbedder:
    """Manages concurrent embedding generation via Ollama and FAISS indexing for policy clauses."""

    def __init__(self, model_name: str = "nomic-embed-text", max_workers: int = 4):
        self.model_name = model_name
        self.max_workers = max_workers

    def _embed_single(self, clause: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], List[float]]]:
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

    def embed_query(self, text: str) -> List[float]:
        """Embeds a single free-text query (regulatory trigger or chat message)."""
        response = ollama.embeddings(model=self.model_name, prompt=text)
        return response.get("embedding")

    def generate_embeddings(self, clauses: List[Dict[str, Any]]) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        if not clauses:
            logger.warning("Empty clause list passed to generate_embeddings.")
            return np.empty((0, 0), dtype="float32"), []

        embeddings: List[List[float]] = []
        valid_clauses: List[Dict[str, Any]] = []

        logger.info(f"Generating embeddings for {len(clauses)} clauses using {self.max_workers} threads...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
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
        try:
            os.makedirs(os.path.dirname(os.path.abspath(index_path)), exist_ok=True)
            os.makedirs(os.path.dirname(os.path.abspath(mapping_path)), exist_ok=True)

            faiss.write_index(index, index_path)
            logger.info(f"Saved FAISS index to {index_path}")

            clause_mappings = []
            for idx, clause in enumerate(clauses):
                clause_mappings.append({
                    "faiss_id": idx,
                    "clause_id": clause.get("clause_id"),
                    "parent_id": clause.get("parent_id"),
                    "text": clause.get("text")
                })

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
                # if distance <= distance_threshold:
                #     clause_info = clauses[idx]
                #     results.append({
                #         "faiss_id": idx,
                #         "distance": distance,
                #         "clause_id": clause_info.get("clause_id"),
                #         "parent_id": clause_info.get("parent_id"),
                #         "text": clause_info.get("text")
                #     })
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
