"""
pipeline_service.py

The main orchestration layer for document uploads.
Combines vector indexing and Neo4j graph ingestion into a single workflow.
"""

import logging
from typing import List, Dict, Any

from backend.services.session_store import SessionStore
from backend.services.graph_ingestion import GraphIngestionPipeline

logger = logging.getLogger(__name__)

class UploadPipelineService:
    def __init__(
        self, 
        session_store: SessionStore, 
        graph_pipeline: GraphIngestionPipeline
    ):
        self.session_store = session_store
        self.graph_pipeline = graph_pipeline

    def process_upload(
        self, 
        session_id: str, 
        reg_docs: List[Dict[str, Any]], 
        policy_docs: List[Dict[str, Any]],
        dependency_graph: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """
        Executes the full ingestion pipeline: 
        1. Vectorize text 
        2. Construct Knowledge Graph
        """
        logger.info(f"Starting ingestion pipeline for session {session_id}")

        try:
            # 1. Prepare texts and metadata for Vector Store (Isolation setup)
            texts = []
            metadatas = []
            
            for doc in reg_docs + policy_docs:
                texts.append(doc["text"])
                metadatas.append({
                    "id": doc.get("clause_id") or doc.get("id"),
                    "session_id": session_id,
                    "type": "regulatory" if doc in reg_docs else "policy"
                })

            # 2. Ingest into Vector Store
            self.session_store.initialize_store(texts, metadatas)
            logger.info("Vector store initialization complete.")

            # 3. Trigger Zero-Time Graph Ingestion (Heavy LLM lifting happens here)
            report = self.graph_pipeline.ingest(
                session_id=session_id,
                regulation_clauses=reg_docs,
                policy_clauses=policy_docs,
                dependency_graph=dependency_graph,
                source_docs=["upload_batch"]
            )
            
            return {
                "status": "success",
                "message": "Documents successfully vectorized and compliance graph constructed.",
                "ingestion_metrics": {
                    "total_time_seconds": round(report.total_elapsed_s, 2),
                    "compliance_edges_created": report.compliance_edges_written,
                    "llm_calls_made": report.llm_calls_made
                }
            }

        except Exception as e:
            logger.error(f"Pipeline failed for session {session_id}: {e}")
            return {
                "status": "error",
                "message": str(e)
            }