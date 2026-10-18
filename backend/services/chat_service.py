"""
chat_service.py

Handles conversational RAG queries from the user (/api/chat).
Combines FAISS vector retrieval with pre-computed Neo4j graph context 
to provide highly grounded, hallucination-free answers.
"""

import logging
from typing import Dict, Any, List
from reasoning.graph_store import driver, NODE_REGULATORY, NODE_POLICY
from reasoning.impact_analysis import ImpactAnalyzer

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self, llm_client, session_store, embedder):
        self.llm = llm_client
        self.session_store = session_store # Store the reference to the parent object
        self.embedder = embedder
        self.impact_analyzer = ImpactAnalyzer()

    def generate_response(self, session_id: str, query: str, chat_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        logger.info(f"Processing chat query for session {session_id}: {query}")
        
        vector_context = self._get_vector_context(session_id, query)
        graph_context = self._get_graph_context(session_id, vector_context)
        prompt = self._build_rag_prompt(query, vector_context, graph_context, chat_history)
        
        try:
            response_text = self.llm.predict(prompt)
            return {
                "status": "success",
                "session_id": session_id,
                "answer": response_text,
                "context_used": {
                    "vector_results": len(vector_context),
                    "graph_results": len(graph_context)
                }
            }
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return {"status": "error", "message": "Failed to generate response."}

    def _get_vector_context(self, session_id: str, query: str, k: int = 4) -> List[Dict[str, Any]]:
        try:
            # Added dynamic check for the vector store
            if not self.session_store.vector_store:
                return []
                
            query_vec = self.embedder.embed_query(query)
            results = self.session_store.vector_store.similarity_search_by_vector(
                query_vec, k=k, filter={"session_id": session_id}
            )
            return [
                {
                    "id": doc.metadata.get("id", "unknown"),
                    "text": doc.page_content,
                    "type": doc.metadata.get("type", "document")
                }
                for doc in results
            ]
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return []

    def _get_graph_context(self, session_id: str, vector_context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Uses the IDs retrieved from the vector search to pull connected compliance 
        relationships and pre-computed reasoning directly from Neo4j.
        """
        graph_data = []
        
        # Extract regulatory IDs from the vector results to seed the graph traversal
        reg_ids = [item["id"] for item in vector_context if item["type"] == "regulatory"]
        
        if not reg_ids:
            return graph_data

        with driver.session() as session:
            for rid in reg_ids:
                # Fetch pre-computed direct and indirect impacts
                impacts = self.impact_analyzer._get_direct_impacts(session_id, rid)
                if impacts:
                    graph_data.append({
                        "regulatory_id": rid,
                        "impacts": impacts
                    })
                    
        return graph_data

    def _build_rag_prompt(
        self, 
        query: str, 
        vector_context: List[Dict[str, Any]], 
        graph_context: List[Dict[str, Any]],
        chat_history: List[Dict[str, str]]
    ) -> str:
        """
        Formats the retrieved vector text and structured graph relationships into a single prompt.
        """
        # Format Text Context (truncate long text chunks to keep within context window)
        text_context_str = "\n".join([
            f"- [{c.get('type', 'doc').upper()} {c.get('id', '')}]: {(c.get('text', '')[:1200] + '...') if len(c.get('text', '')) > 1200 else c.get('text', '')}"
            for c in vector_context
        ])
        
        # Format Graph Context
        graph_context_str = ""
        for g in graph_context:
            graph_context_str += f"\nRegulatory Trigger: {g['regulatory_id']}\n"
            for impact in g['impacts']:
                graph_context_str += f"  -> {impact['relationship']} with Policy {impact['policy_id']}. Reasoning: {impact['reasoning']}\n"

        # Format History
        history_str = ""
        if chat_history:
            history_str = "\nRecent Conversation:\n" + "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history[-3:]])

        prompt = f"""
You are an expert regulatory compliance assistant. Answer the user's query using ONLY the provided context.

DOCUMENT CONTEXT (Text Chunks):
{text_context_str if text_context_str else "None"}

COMPLIANCE GRAPH CONTEXT (Pre-computed Relationships):
{graph_context_str if graph_context_str else "None"}
{history_str}

User Query: {query}

Instructions:
1. Base your answer strictly on the Document Context and Compliance Graph Context provided above.
2. If the answer is not contained in the context, state clearly that you do not have enough information.
3. When referencing a policy or regulation, cite its ID.
4. Utilize the pre-computed relationships and reasoning from the Graph Context to explain compliance statuses.
"""
        return prompt.strip()