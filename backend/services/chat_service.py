import logging
from typing import Any, Dict, List
import ollama
import config
from retrieval.semanticsearch import SemanticSearch
from services.session_store import SessionState
from reasoning.graph_store import policy_graph 

logger = logging.getLogger("ChatService")

SYSTEM_PROMPT = """You are an insurance compliance assistant helping a user understand a regulatory impact analysis. 
Rules:
- Answer only using the retrieved policy clauses and the Knowledge Graph context provided below.
- If the retrieved context does not contain the answer, say so plainly.
- Reference clause IDs (e.g. "Clause 2.1") when you rely on them.
- Be concise and precise, like a compliance analyst."""

def _get_graph_context(clause_ids: List[str]) -> str:
    """2. Queries FalkorDB natively for compliance status and dependencies."""
    if not clause_ids:
        return "(No graph context available.)"
        
    query = """
    MATCH (c:PolicyClause)
    WHERE c.id IN $clause_ids
    OPTIONAL MATCH (r:Regulation)-[rel:COMPLIANCE]->(c)
    OPTIONAL MATCH (c)-[:DEPENDS_ON]->(dep:PolicyClause)
    RETURN c.id as clause, 
           collect(DISTINCT {reg: r.id, status: rel.status, reasoning: rel.reasoning}) as compliance,
           collect(DISTINCT dep.id) as dependencies
    """
    try:
        result = policy_graph.query(query, {"clause_ids": clause_ids}).result_set
        
        blocks = []
        for row in result:
            clause_id, compliance_data, dependencies = row
            block = f"Graph Data for Clause {clause_id}:"
            
            # Format Compliance Edges
            for comp in compliance_data:
                if comp.get('status'):
                    block += f"\n  - Status: {comp['status']} (Regulation {comp['reg']}) - {comp['reasoning']}"
                    
            # Format Dependency Edges
            if dependencies and dependencies[0] is not None:
                block += f"\n  - Operationally affects downstream clauses: {', '.join(dependencies)}"
                
            blocks.append(block)
        return "\n\n".join(blocks)
    except Exception as e:
        logger.error(f"Graph query failed: {e}")
        return "(Error retrieving graph context.)"

def _format_context(retrieved: List[Dict[str, Any]]) -> str:
    if not retrieved:
        return "(No closely matching policy clauses were found for this question.)"
    blocks = [f"Clause {r['clause']['clause_id']}:\n{r['clause']['text']}" for r in retrieved]
    return "\n\n".join(blocks)

def chat(session: SessionState, user_message: str) -> Dict[str, Any]:
    """Answers follow-up questions using FAISS retrieval + FalkorDB context."""
    if session.index is None or not session.policy_clauses:
        raise ValueError("No document set has been ingested for this session yet.")
        
    searcher = SemanticSearch(session.index, session.policy_clauses, embedder=session.embedder)
    retrieved = searcher.search(
        user_message,
        k=config.CHAT_TOP_K,
        distance_threshold=config.CHAT_DISTANCE_THRESHOLD,
    )
    
    # 3. Retrieve clause IDs to query the graph
    clause_ids = [r["clause"]["clause_id"] for r in retrieved]
    
    text_context = _format_context(retrieved)
    graph_context = _get_graph_context(clause_ids)
    
    history = session.chat_history[-(config.MAX_CHAT_HISTORY_TURNS * 2):] if session.chat_history else []
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    
    # 4. Inject FAISS text + FalkorDB relations into the prompt
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