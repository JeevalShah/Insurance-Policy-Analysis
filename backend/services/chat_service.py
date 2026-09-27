"""
chat_service.py

Handles conversational context retrieval and LLM responses over FAISS search 
and the populated Neo4j knowledge graph.
"""

import logging
from typing import Any, Dict, List, Optional
import ollama
import config
from retrieval.semanticsearch import SemanticSearch
from services.session_store import SessionState

from reasoning.graph_store import (
    driver,
    NODE_REGULATORY,
    NODE_POLICY,
    EDGE_DEPENDS_ON,
)

logger = logging.getLogger("ChatService")

# Map specific Neo4j relationship types back to friendly labels
REL_TYPE_TO_LABEL = {
    "CONFLICTS_WITH": "CONFLICT",
    "COMPLIES_WITH":  "COMPLIANT",
    "SUPPORTS":       "SUPPORTING",
    "IS_REDUNDANT":   "REDUNDANT",
    "NOT_RELATED":    "NOT_RELATED"
}

SYSTEM_PROMPT = """You are an insurance compliance assistant helping a user understand a regulatory impact analysis. 
Rules:
- Answer only using the retrieved policy clauses and the Knowledge Graph context provided below.
- If the retrieved context does not contain the answer, say so plainly.
- Reference clause IDs (e.g. "Clause 2.1") when you rely on them.
- Be concise and precise, like a compliance analyst."""


def _get_graph_context(clause_ids: List[str], session_id: Optional[str] = None) -> str:
    """Queries Neo4j natively for compliance status and dependencies."""
    if not clause_ids:
        return "(No graph context available.)"
        
    query = f"""
    MATCH (c:{NODE_POLICY})
    WHERE c.id IN $clause_ids AND ($sid IS NULL OR c.session_id = $sid)
    OPTIONAL MATCH (r:{NODE_REGULATORY})-[rel]->(c)
    WHERE NOT type(rel) = $dep_edge
    OPTIONAL MATCH (c)-[:{EDGE_DEPENDS_ON}]->(dep:{NODE_POLICY})
    WITH c,
         CASE WHEN r IS NOT NULL THEN {{reg: r.id, status: type(rel), reasoning: rel.reasoning}} ELSE NULL END AS comp_item,
         dep.id AS dep_id
    RETURN c.id AS clause, 
           collect(DISTINCT comp_item) AS compliance,
           collect(DISTINCT dep_id) AS dependencies
    """
    try:
        with driver.session() as session:
            result = session.run(
                query,
                {
                    "clause_ids": clause_ids,
                    "sid": session_id,
                    "dep_edge": EDGE_DEPENDS_ON,
                }
            )
            records = [record.data() for record in result]
        
        blocks = []
        for record in records:
            clause_id = record.get("clause")
            compliance_data = record.get("compliance", [])
            dependencies = record.get("dependencies", [])
            
            block = f"Graph Data for Clause {clause_id}:"
            
            # Format Compliance Edges
            for comp in compliance_data:
                if comp and comp.get('status'):
                    raw_status = comp['status']
                    friendly_status = REL_TYPE_TO_LABEL.get(raw_status, raw_status)
                    reasoning_str = f" - {comp['reasoning']}" if comp.get('reasoning') else ""
                    block += f"\n  - Status: {friendly_status} (Regulation {comp.get('reg')}){reasoning_str}"
                    
            # Format Dependency Edges
            deps = [d for d in dependencies if d is not None]
            if deps:
                block += f"\n  - Operationally affects downstream clauses: {', '.join(deps)}"
                
            blocks.append(block)
            
        return "\n\n".join(blocks) if blocks else "(No graph context available.)"

    except Exception as e:
        logger.error(f"Graph query failed: {e}")
        return "(Error retrieving graph context.)"


def _format_context(retrieved: List[Dict[str, Any]]) -> str:
    if not retrieved:
        return "(No closely matching policy clauses were found for this question.)"
    blocks = [f"Clause {r['clause']['clause_id']}:\n{r['clause']['text']}" for r in retrieved]
    return "\n\n".join(blocks)


def chat(session: SessionState, user_message: str) -> Dict[str, Any]:
    """Answers follow-up questions using FAISS retrieval + Neo4j context."""
    if session.index is None or not session.policy_clauses:
        raise ValueError("No document set has been ingested for this session yet.")
        
    searcher = SemanticSearch(session.index, session.policy_clauses, embedder=session.embedder)
    retrieved = searcher.search(
        user_message,
        k=config.CHAT_TOP_K,
        distance_threshold=config.CHAT_DISTANCE_THRESHOLD,
    )
    
    # Retrieve clause IDs to query the graph
    clause_ids = [r["clause"]["clause_id"] for r in retrieved]
    session_id = getattr(session, "session_id", None)
    
    text_context = _format_context(retrieved)
    graph_context = _get_graph_context(clause_ids, session_id=session_id)
    
    history = session.chat_history[-(config.MAX_CHAT_HISTORY_TURNS * 2):] if session.chat_history else []
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    
    # Inject FAISS text + Neo4j relations into the prompt
    augmented_user_message = (
        f"Context for this question:\n"
        f"---\n"
        f"Retrieved Policy Clauses (Text Content):\n{text_context}\n\n"
        f"Knowledge Graph Context (Compliance & Dependencies):\n{graph_context}\n"
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

    session.chat_history.append({"role": "user", "content": user_message})
    session.chat_history.append({"role": "assistant", "content": answer})
    
    sources = [{"clause_id": c_id, "distance": r["distance"]} for c_id, r in zip(clause_ids, retrieved)]
    return {"answer": answer, "sources": sources}