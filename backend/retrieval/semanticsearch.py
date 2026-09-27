"""
Session-aware semantic search over a policy clause FAISS index.

The original CLI prototype read a single global index/mapping pair from
disk. The Flask backend serves multiple concurrent sessions (one per
uploaded document set), so this module wraps the same FAISS + Ollama
mechanics from `embeddings.embedder.PolicyEmbedder` in a small class that
is instantiated per session instead of relying on module-level globals.
"""
import logging
from typing import Any, Dict, List, Optional

import faiss

from embeddings.embedder import PolicyEmbedder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("SemanticSearch")


class SemanticSearch:
    """Wraps a single session's FAISS index + clause mapping for querying."""

    def __init__(
        self,
        index: faiss.Index,
        clauses: List[Dict[str, Any]],
        embedder: Optional[PolicyEmbedder] = None,
        embed_model: str = "nomic-embed-text",
    ):
        self.index = index
        self.clauses = clauses
        self.embedder = embedder or PolicyEmbedder(model_name=embed_model)

    def search(self, query: str, k: int = 5, distance_threshold: float = 1.0) -> List[Dict[str, Any]]:
        """
        Embeds `query` and returns the nearest policy clauses within the
        distance threshold, in the same shape the reasoning layer expects:
        [{"clause": {...}, "distance": float}, ...]
        """
        if not query or not query.strip():
            return []
        if self.index is None or not self.clauses:
            logger.warning("Search called on an empty/unbuilt index.")
            return []

        query_vector = self.embedder.embed_query(query)
        raw_results = self.embedder.secure_search(
            self.index,
            query_vector,
            self.clauses,
            k=k,
            distance_threshold=distance_threshold
        )

        return [
            {
                "clause": {
                    "clause_id": r["clause_id"],
                    "parent_id": r["parent_id"],
                    "text": r["text"],
                },
                "distance": r["distance"],
            }
            for r in raw_results
        ]