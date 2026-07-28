import os
import logging
from typing import List
from werkzeug.datastructures import FileStorage

import config
from parsing import pdf_parsing, docx_parsing
from clause_extraction.clause_split import split_into_clauses
from embeddings.embedder import PolicyEmbedder
from retrieval.semanticsearch import SemanticSearch
from reasoning.impact_analysis import analyze_impact
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
        raise ValueError(f"Unsupported file type: {ext}. Supported: {sorted(SUPPORTED_EXTENSIONS)}")

    full_text = ""
    for page in pages:
        full_text += page["text"] + "\n"
    return full_text


def _save_uploads(session: SessionState, files: List[FileStorage], subfolder: str) -> List[str]:
    target_dir = os.path.join(session.session_dir, "raw", subfolder)
    os.makedirs(target_dir, exist_ok=True)

    saved_paths = []
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type '{ext}' for '{f.filename}'. Only PDF and DOCX are accepted.")
        dest_path = os.path.join(target_dir, f.filename)
        f.save(dest_path)
        saved_paths.append(dest_path)
    return saved_paths


def ingest_documents(
    session: SessionState,
    regulation_files: List[FileStorage],
    policy_files: List[FileStorage],
) -> None:
    """
    Saves uploaded files, extracts text, splits into hierarchical clauses,
    embeds the policy corpus, and builds the FAISS index for the session.
    """
    if not regulation_files:
        raise ValueError("At least one regulatory document is required.")
    if not policy_files:
        raise ValueError("At least one company policy document is required.")

    session.status = "ingesting"

    try:
        regulation_paths = _save_uploads(session, regulation_files, "regulation")
        policy_paths = _save_uploads(session, policy_files, "policy")

        regulation_text = "\n".join(_extract_text_from_file(p) for p in regulation_paths)
        policy_text = "\n".join(_extract_text_from_file(p) for p in policy_paths)

        regulation_clauses = split_into_clauses(regulation_text)
        policy_clauses = split_into_clauses(policy_text)

        if not policy_clauses:
            raise ValueError("No clauses could be extracted from the policy document(s). Check the file content/format.")
        if not regulation_clauses:
            raise ValueError("No clauses could be extracted from the regulatory document. Check the file content/format.")

        embedder = PolicyEmbedder(model_name=config.EMBED_MODEL)
        vectors, valid_clauses = embedder.generate_embeddings(policy_clauses)
        index = embedder.build_index(vectors)

        index_path = os.path.join(session.session_dir, "faiss_index.bin")
        mapping_path = os.path.join(session.session_dir, "clause_mapping.json")
        embedder.save_index_and_mapping(index, valid_clauses, index_path, mapping_path)

        session.policy_clauses = valid_clauses
        session.regulation_clauses = regulation_clauses
        session.embedder = embedder
        session.index = index
        session.status = "ready"

    except Exception as e:
        session.status = "error"
        session.error = str(e)
        logger.exception("Document ingestion failed")
        raise


def run_analysis(session: SessionState) -> List[dict]:
    """Runs the direct + indirect impact analysis pipeline for a ready session."""
    if session.status not in ("ready", "analyzed"):
        raise ValueError(f"Session is not ready for analysis (status={session.status}).")

    if session.status == "analyzed" and session.analysis_result is not None:
        return session.analysis_result
    
    session.status = "analyzing"
    try:
        searcher = SemanticSearch(session.index, session.policy_clauses, embedder=session.embedder)
        result = analyze_impact(
            regulation_clauses=session.regulation_clauses,
            policy_clauses=session.policy_clauses,
            searcher=searcher,
            top_k=config.SEARCH_TOP_K,
            distance_threshold=config.SEARCH_DISTANCE_THRESHOLD,
            chat_model=config.CHAT_MODEL,
        )
        session.analysis_result = result
        session.status = "analyzed"
        return result
    except Exception as e:
        session.status = "error"
        session.error = str(e)
        logger.exception("Impact analysis failed")
        raise
