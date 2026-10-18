import json
import os
import time
import logging
import threading
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

# Optional import -- keep the embedder importable/testable without config.py
# present (e.g. in isolated unit tests).
try:
    import config as _config
    _STRONG_MATCH_DISTANCE = _config.STRONG_MATCH_DISTANCE
    _WEAK_MATCH_DISTANCE = _config.WEAK_MATCH_DISTANCE
except Exception:  # pragma: no cover - fallback for standalone use/testing
    _STRONG_MATCH_DISTANCE = 0.6
    _WEAK_MATCH_DISTANCE = 1.2


def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
    """L2-normalizes each row of a 2D array. Rows that are all-zero (or
    otherwise degenerate) are left as-is rather than divided by zero."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    safe_norms = np.where(norms == 0, 1.0, norms)
    return vectors / safe_norms


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0 or not np.isfinite(norm):
        return vector
    return vector / norm


def _match_quality(distance: float) -> str:
    """Purely for debug logging -- does not affect what's returned/filtered."""
    if distance <= _STRONG_MATCH_DISTANCE:
        return "STRONG"
    if distance <= _WEAK_MATCH_DISTANCE:
        return "WEAK"
    return "NO_MEANINGFUL_MATCH"


class PolicyEmbedder:
    """Manages concurrent embedding generation via Ollama and FAISS indexing for policy clauses.

    NOTE ON NORMALIZATION: embeddings are L2-normalized before being added to
    the FAISS index and before being used as a query vector. IndexFlatL2 is
    kept unchanged (no index-type migration needed), but on unit vectors,
    L2_distance^2 = 2 - 2*cos_similarity, so distances are now meaningful in a
    fixed [0, 4] range instead of the previous unnormalized range (observed
    ~185-207 on nomic-embed-text output), which made any fixed threshold
    meaningless. This was determined by inspecting the raw embedding norms
    (they were not unit length) rather than by picking a new threshold
    arbitrarily.
    """

    def __init__(self, model_name: str = "nomic-embed-text", max_workers: int = 4):
        self.model_name = model_name
        self.max_workers = max_workers

        # Simple in-memory cache for query embeddings (regulatory triggers /
        # chat questions) generated during THIS embedder instance's lifetime
        # (i.e. scoped to one session, not persisted across sessions).
        self._query_embedding_cache: Dict[str, List[float]] = {}
        self._cache_lock = threading.Lock()

        # Call counters, used for the end-of-analysis LLM call report.
        self.embed_call_count = 0
        self._counter_lock = threading.Lock()

    def _increment_embed_calls(self):
        with self._counter_lock:
            self.embed_call_count += 1

    def _embed_single(self, clause: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], List[float]]]:
        text = clause.get("text", "").strip()
        if not text:
            return None

        # Truncate text to stay safely within model context window (~1500 words / 6000 chars)
        if len(text) > 6000:
            text = text[:6000]

        try:
            self._increment_embed_calls()
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
        """Embeds a single free-text query (regulatory trigger or chat message).

        Cached per-embedder-instance: if the same session re-queries the same
        text (e.g. re-running analysis, or a repeated chat question), no new
        Ollama call is made.
        """
        clean_text = (text or "").strip()
        if not clean_text:
            return [0.0] * 768

        # nomic-embed-text max context is 2048 tokens (~1500 words / 6000 chars)
        if len(clean_text) > 6000:
            clean_text = clean_text[:6000]

        cache_key = clean_text
        with self._cache_lock:
            cached = self._query_embedding_cache.get(cache_key)
        if cached is not None:
            return cached

        self._increment_embed_calls()
        response = ollama.embeddings(model=self.model_name, prompt=text)
        embedding = response.get("embedding")
        if embedding:
            normalized = _normalize_vector(np.array(embedding, dtype="float32")).tolist()
            with self._cache_lock:
                self._query_embedding_cache[cache_key] = normalized
            return normalized
        return embedding

    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Langchain-compatible method for embedding multiple text documents.
        Required by langchain_community.vectorstores.FAISS.
        """
        results = [None] * len(texts)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            def _embed_str(index: int, t: str):
                # Reuse embed_query to benefit from caching and normalization
                emb = self.embed_query(t)
                # Fallback to zero vector if embedding fails to prevent Langchain FAISS from crashing
                if not emb:
                    emb = [0.0] * 768 # Default dimensionality for nomic-embed-text
                return index, emb

            futures = [executor.submit(_embed_str, i, text) for i, text in enumerate(texts)]
            for future in concurrent.futures.as_completed(futures):
                index, embedding = future.result()
                results[index] = embedding
                
        return results

    
    def generate_embeddings(self, clauses: List[Dict[str, Any]]) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        if not clauses:
            logger.warning("Empty clause list passed to generate_embeddings.")
            return np.empty((0, 0), dtype="float32"), []

        embeddings: List[List[float]] = []
        valid_clauses: List[Dict[str, Any]] = []

        logger.info(f"Generating embeddings for {len(clauses)} clauses using {self.max_workers} threads...")
        t0 = time.perf_counter()

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Map futures to preserve order if needed, or simply use as_completed
            futures = {executor.submit(self._embed_single, clause): clause for clause in clauses}
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    if result is not None:
                        clause, embedding = result
                        embeddings.append(embedding)
                        valid_clauses.append(clause)
                except Exception as e:
                    logger.error(f"Error resolving future result: {e}")

        elapsed = time.perf_counter() - t0

        if not embeddings:
            logger.error("Zero clauses were successfully embedded.")
            raise ValueError("No embeddings generated. Ensure Ollama is running and the model is loaded.")

        vectors = np.array(embeddings, dtype="float32")
        vectors = _normalize_rows(vectors)
        logger.info(
            f"Successfully generated {len(valid_clauses)} embeddings out of {len(clauses)} chunks."
        )
        logger.info(f"[PERF] Policy embedding: {elapsed:.2f}s ({len(valid_clauses)} clauses, "
                     f"{elapsed / max(len(valid_clauses), 1):.3f}s/clause avg)")
        return vectors, valid_clauses

    def build_index(self, vectors: np.ndarray) -> faiss.IndexFlatL2:
        if vectors.size == 0 or vectors.shape[0] == 0:
            raise ValueError("Cannot build FAISS index with empty vectors.")

        t0 = time.perf_counter()
        dimension = vectors.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(vectors)
        elapsed = time.perf_counter() - t0
        logger.info(f"Built FAISS index with {index.ntotal} vectors of dimension {dimension}.")
        logger.info(f"[PERF] FAISS index build: {elapsed:.2f}s")
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
        """Runs the FAISS search and ACTUALLY applies distance_threshold now
        (previously accepted but silently ignored -- everything within top-k
        was returned regardless of quality). Candidates beyond the threshold
        are dropped rather than surfaced as if they were meaningful matches.
        """
        try:
            t0 = time.perf_counter()
            query_vector = np.array(query_vector, dtype="float32")

            if len(query_vector.shape) == 1:
                query_vector = np.expand_dims(query_vector, axis=0)
            query_vector = _normalize_rows(query_vector)

            distances, indices = index.search(query_vector, k)
            elapsed = time.perf_counter() - t0

            results = []
            rejected = 0

            for i, idx in enumerate(indices[0]):

                if idx == -1 or idx >= len(clauses):
                    continue

                distance = float(distances[0][i])

                if distance > distance_threshold:
                    rejected += 1
                    continue

                clause_info = clauses[idx]

                results.append({
                    "faiss_id": idx,
                    "distance": distance,
                    "clause_id": clause_info.get("clause_id"),
                    "parent_id": clause_info.get("parent_id"),
                    "text": clause_info.get("text")
                })

            raw_distances = [float(d) for d in distances[0] if d != -1]
            quality_breakdown = [_match_quality(d) for d in raw_distances]
            logger.info(
                f"[PERF] FAISS retrieval: {elapsed:.3f}s | "
                f"raw_distances={['%.3f' % d for d in raw_distances]} | "
                f"quality={quality_breakdown} | "
                f"accepted={len(results)} rejected={rejected} (threshold={distance_threshold})"
            )

            return results

        except Exception as e:
            logger.error(f"Error occurred during secure_search: {e}")
            return []