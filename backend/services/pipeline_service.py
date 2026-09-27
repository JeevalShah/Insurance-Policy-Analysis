"""
pipeline_service.py  (updated)

Key changes from original:
  1. ingest_documents() now calls GraphIngestionPipeline.ingest() after
     building the FAISS index — so all graph writes happen at ingestion time.
  2. dependency_graph.build_dependency_graph() no longer writes to FalkorDB
     itself (remove the build_falkordb_graph call from dependency_graph.py —
     see note at bottom of this file).
  3. session.ingestion_report is stored for benchmarking endpoints.
"""

import os
import time
import logging
from typing import List
from werkzeug.datastructures import FileStorage

import config
from parsing import pdf_parsing, docx_parsing
from clause_extraction.clause_split import split_into_clauses
from embeddings.embedder import PolicyEmbedder
from reasoning.impact_analysis import analyze_impact
from reasoning.dependency_graph import build_dependency_graph
from reasoning import relationshipclassifier                    # ← pass as module
from services.graph_ingestion import GraphIngestionPipeline              # ← new
from services.session_store import SessionState

logger = logging.getLogger("PipelineService")

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


def _extract_text_from_file(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        pages = pdf_parsing.extract_text(file_path)
    elif ext == ".docx":
        pages = docx_parsing.extract_text(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}.")
    return "\n".join(page["text"] for page in pages)


def _save_uploads(session: SessionState, files: List[FileStorage], subfolder: str) -> List[str]:
    target_dir = os.path.join(session.session_dir, "raw", subfolder)
    os.makedirs(target_dir, exist_ok=True)
    saved_paths = []
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type '{ext}' for '{f.filename}'.")
        dest_path = os.path.join(target_dir, f.filename)
        f.save(dest_path)
        saved_paths.append(dest_path)
    return saved_paths


def ingest_documents(
    session: SessionState,
    regulation_files: List[FileStorage],
    policy_files: List[FileStorage],
) -> None:
    if not regulation_files:
        raise ValueError("At least one regulatory document is required.")
    if not policy_files:
        raise ValueError("At least one company policy document is required.")

    session.status = "ingesting"

    try:
        # ── 1. Save and parse ──────────────────────────────────────────────
        regulation_paths = _save_uploads(session, regulation_files, "regulation")
        policy_paths     = _save_uploads(session, policy_files, "policy")

        t0 = time.perf_counter()
        regulation_text = "\n".join(_extract_text_from_file(p) for p in regulation_paths)
        policy_text     = "\n".join(_extract_text_from_file(p) for p in policy_paths)
        logger.info(f"[PERF] Text extraction: {time.perf_counter() - t0:.2f}s")

        # ── 2. Clause splitting ────────────────────────────────────────────
        t0 = time.perf_counter()
        regulation_clauses = split_into_clauses(regulation_text)
        policy_clauses     = split_into_clauses(policy_text)
        logger.info(
            f"[PERF] Clause splitting: {time.perf_counter() - t0:.2f}s "
            f"({len(regulation_clauses)} reg, {len(policy_clauses)} policy clauses)"
        )

        if not policy_clauses:
            raise ValueError("No clauses extracted from policy document(s).")
        if not regulation_clauses:
            raise ValueError("No clauses extracted from regulatory document(s).")

        # ── 3. Embeddings + FAISS index (still needed for ingestion-time retrieval) ──
        embedder = PolicyEmbedder(
            model_name=config.EMBED_MODEL,
            max_workers=config.EMBED_MAX_WORKERS
        )
        vectors, valid_policy_clauses = embedder.generate_embeddings(policy_clauses)
        index = embedder.build_index(vectors)

        index_path   = os.path.join(session.session_dir, "faiss_index.bin")
        mapping_path = os.path.join(session.session_dir, "clause_mapping.json")
        embedder.save_index_and_mapping(index, valid_policy_clauses, index_path, mapping_path)
        # embedder.index is NOT manually attached here — secure_search() receives
        # the index as an explicit argument, so the embedder doesn't need to hold it
        # as an attribute. The index local variable is passed directly below.

        # ── 4. Dependency graph (pure Python adjacency dict — no FalkorDB side effect) ──
        # IMPORTANT: remove the build_falkordb_graph() call from dependency_graph.py.
        # Graph writes are centralised in GraphIngestionPipeline below.
        t0 = time.perf_counter()
        dependency_graph = build_dependency_graph(valid_policy_clauses)
        logger.info(f"[PERF] Dependency graph: {time.perf_counter() - t0:.2f}s")

        # ── 5. FalkorDB ingestion (nodes + edges + compliance classification) ──
        ingestion_pipeline = GraphIngestionPipeline(
            embedder=embedder,
            classifier=relationshipclassifier,
            index=index,                                           # faiss.Index built above
            top_k=config.SEARCH_TOP_K,
            model=config.CHAT_MODEL,
            distance_threshold=config.SEARCH_DISTANCE_THRESHOLD,
        )

        source_doc_names = (
            [os.path.basename(p) for p in regulation_paths] +
            [os.path.basename(p) for p in policy_paths]
        )

        ingestion_report = ingestion_pipeline.ingest(
            session_id=session.session_id,
            regulation_clauses=regulation_clauses,
            policy_clauses=valid_policy_clauses,
            dependency_graph=dependency_graph,
            source_docs=source_doc_names,
        )

        # ── 6. Store on session ────────────────────────────────────────────
        session.policy_clauses      = valid_policy_clauses
        session.regulation_clauses  = regulation_clauses
        session.embedder            = embedder
        session.index               = index
        session.dependency_graph    = dependency_graph
        session.ingestion_report    = ingestion_report  # ← new: for benchmarking endpoint
        session.status              = "ready"

        if ingestion_report.errors:
            logger.warning(
                f"Ingestion completed with {len(ingestion_report.errors)} non-fatal errors. "
                f"Check ingestion_report.errors for details."
            )

    except Exception as e:
        session.status = "error"
        session.error  = str(e)
        logger.exception("Document ingestion failed")
        raise


def run_analysis(session: SessionState) -> List[dict]:
    """
    At query time: zero LLM calls.
    impact_analysis.py should now call graph_ingestion.get_direct_impacts()
    and graph_ingestion.get_indirect_impacts() instead of SemanticSearch +
    classify_relationship().
    """
    if session.status not in ("ready", "analyzed"):
        raise ValueError(f"Session not ready (status={session.status}).")

    if session.status == "analyzed" and session.analysis_result is not None:
        return session.analysis_result

    session.status = "analyzing"
    try:
        result = analyze_impact(
            session_id=session.session_id,
            regulation_clauses=session.regulation_clauses,
        )
        session.analysis_result = result
        session.status          = "analyzed"
        return result
    except Exception as e:
        session.status = "error"
        session.error  = str(e)
        logger.exception("Impact analysis failed")
        raise


# ---------------------------------------------------------------------------
# NOTE: changes required in dependency_graph.py
# ---------------------------------------------------------------------------
# Remove the `build_falkordb_graph(clauses, result)` call at the bottom of
# build_dependency_graph().  The function should return the dict only.
# Also remove the `from reasoning.graph_store import policy_graph` import
# and the entire build_falkordb_graph() function — graph writes now belong
# exclusively to GraphIngestionPipeline.
#
# Minimal diff:
#
#   def build_dependency_graph(clauses):
#       ...
#       result = {k: sorted(v) for k, v in graph.items()}
#       logger.info(f"Built dependency graph with {len(result)} source clauses.")
#  -    build_falkordb_graph(clauses, result)    # ← DELETE THIS LINE
#       return result
#
#  -    def build_falkordb_graph(clauses, dependencies): ...  # ← DELETE ENTIRE FUNCTION
# ---------------------------------------------------------------------------