import logging
from typing import Any, Dict, List

import ollama

import config
from retrieval.semanticsearch import SemanticSearch
from services.session_store import SessionState

logger = logging.getLogger("ChatService")

SYSTEM_PROMPT = """You are an insurance compliance assistant helping a user understand a regulatory \
impact analysis that has already been run on their policy documents.

Rules:
- Answer only using the retrieved policy clauses and analysis context provided below.
- If the retrieved context does not contain the answer, say so plainly instead of guessing.
- Reference clause IDs (e.g. "Clause 2.1") when you rely on them.
- Be concise and precise, like a compliance analyst, not a generic chatbot."""


def _format_context(retrieved: List[Dict[str, Any]]) -> str:
    if not retrieved:
        return "(No closely matching policy clauses were found for this question.)"

    blocks = []
    for r in retrieved:
        clause = r["clause"]
        blocks.append(f"Clause {clause['clause_id']}:\n{clause['text']}")
    return "\n\n".join(blocks)


def _format_analysis_summary(session: SessionState) -> str:
    if not session.analysis_result:
        return "(No impact analysis has been run yet.)"

    lines = []
    for entry in session.analysis_result:
        lines.append(f"Regulatory clause {entry['trigger_id']}:")
        for clause_id, data in entry["direct"].items():
            lines.append(f"  - Clause {clause_id}: {data['relationship']} — {data['reasoning']}")
        if entry["indirect"]:
            lines.append(f"  - Indirectly affected: {', '.join(entry['indirect'])}")
    return "\n".join(lines)


def chat(session: SessionState, user_message: str) -> Dict[str, Any]:
    """
    Answers a follow-up question using retrieval-augmented generation over
    the session's policy clause index, grounded in the prior analysis
    result and recent conversation history.
    """
    if session.index is None or not session.policy_clauses:
        raise ValueError("No document set has been ingested for this session yet.")

    searcher = SemanticSearch(session.index, session.policy_clauses, embedder=session.embedder)
    retrieved = searcher.search(
        user_message,
        k=config.CHAT_TOP_K,
        distance_threshold=config.CHAT_DISTANCE_THRESHOLD,
    )

    context_block = _format_context(retrieved)
    analysis_block = _format_analysis_summary(session)

    # Prevent potential errors if the history is empty
    history = session.chat_history[-(config.MAX_CHAT_HISTORY_TURNS * 2):] if session.chat_history else []

    # 1. Base system instructions
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # 2. Add conversational history FIRST
    messages.extend(history)
    
    # 3. Create a unified prompt combining context and the user's question LAST
    # This ensures the model's immediate attention is on the facts.
    augmented_user_message = (
        f"Context for this question:\n"
        f"---\n"
        f"Prior impact analysis summary:\n{analysis_block}\n\n"
        f"Retrieved policy clauses:\n{context_block}\n"
        f"---\n\n"
        f"User Question: {user_message}"
    )
    
    messages.append({"role": "user", "content": augmented_user_message})

    try:
        response = ollama.chat(model=config.CHAT_MODEL, messages=messages)
        answer = response["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Chat generation failed: {e}")
        raise RuntimeError("The local language model could not be reached. Is Ollama running?") from e

    # IMPORTANT: Save the ORIGINAL user_message to history, not the augmented one!
    # If you save the augmented one, your history will fill up with duplicate contexts.
    session.chat_history.append({"role": "user", "content": user_message})
    session.chat_history.append({"role": "assistant", "content": answer})

    sources = [
        {
            "clause_id": r["clause"]["clause_id"],
            "distance": r["distance"],
        }
        for r in retrieved
    ]

    return {"answer": answer, "sources": sources}