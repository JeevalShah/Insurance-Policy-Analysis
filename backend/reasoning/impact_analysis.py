import logging
from typing import Any, Dict, List

from reasoning.relationshipclassifier import classify_relationship
from reasoning.dependency_graph import build_dependency_graph
import ollama 
from reasoning.graph_store import policy_graph

logger = logging.getLogger("ImpactAnalysis")


def generate_reasoning(trigger: str, clause_text: str, relationship: str, model: str = "llama3") -> str:
    """LLM-generated 1-2 sentence explanation of why a relationship holds."""
    prompt = f"""You are an insurance compliance analyst.

Regulatory Trigger:
{trigger}

Retrieved Clause:
{clause_text}

Relationship Classification:
{relationship}

Explain in 1-2 concise sentences why this relationship exists.
Do not speculate. Base your answer only on the trigger and clause.
Maximum 50 words."""

    try:
        print("="*60)
        print(f"Clause length: {len(clause_text.split())} words")
        print("="*60)
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Reasoning generation failed: {e}")
        return "Reasoning unavailable: the local language model could not be reached."


def save_compliance_relation(reg_id: str, reg_text: str, clause_id: str, relationship: str, reasoning: str):
    """Creates a relationship edge based on the Llama 3 classification."""
    policy_graph.query(
        """
        MERGE (r:Regulation {id: $reg_id})
        SET r.text = $reg_text
        MATCH (c:PolicyClause {id: $clause_id})
        MERGE (r)-[rel:COMPLIANCE {status: $status, reasoning: $reasoning}]->(c)
        """,
        {"reg_id": reg_id, "reg_text": reg_text, "clause_id": clause_id, "status": relationship, "reasoning": reasoning}
    )


def get_graph_impacts(reg_id: str) -> List[str]:
    """Retrieves indirect impacts natively from the graph using Cypher."""
    query = """
    MATCH (r:Regulation {id: $reg_id})-[rel:COMPLIANCE]->(direct:PolicyClause)
    OPTIONAL MATCH (direct)-[:DEPENDS_ON*1..3]->(indirect:PolicyClause)
    RETURN collect(DISTINCT indirect.id) as indirect_impacts
    """
    result = policy_graph.query(query, {"reg_id": reg_id}).result_set
    if result and len(result) > 0 and result[0][0]:
         # Filter out None values just in case there are no indirect impacts
         return sorted([impact for impact in result[0][0] if impact is not None])
    return []


def analyze_trigger(
    trigger_id: str,
    original_trigger: str,
    retrieval_trigger: str,
    searcher,
    top_k,
    distance_threshold,
    chat_model,
):
    """Runs direct retrieval + classification + indirect propagation for one regulatory clause."""
    retrieved = searcher.search(
        retrieval_trigger,
        k=top_k,
        distance_threshold=distance_threshold,
    )
    
    print(f"Retrieved {len(retrieved)} clauses")
    direct_impacts: Dict[str, Any] = {}
    for r in retrieved:
        clause = r["clause"]
        clause_id = clause["clause_id"]
        direct_impacts[clause_id] = {
            "text": clause["text"],
            "distance": r["distance"],
        }

    for clause_id, data in direct_impacts.items():
        print("Starting relationship classification...")
        relationship = classify_relationship(
            original_trigger,
            data["text"],
            model=chat_model
        )
        print("Relationship done")

        print("Starting reasoning...")
        reasoning = generate_reasoning(
            original_trigger,
            data["text"],
            relationship,
            model=chat_model
        )
        print("Reasoning done")

        data["relationship"] = relationship
        data["reasoning"] = reasoning

        save_compliance_relation(trigger_id, original_trigger, clause_id, relationship, reasoning)

    indirect_impacts = get_graph_impacts(trigger_id)

    return {
        "trigger_id": trigger_id,
        "trigger_text": original_trigger,       # original clause
        "retrieval_query": retrieval_trigger,   # summarized clause
        "direct": direct_impacts,
        "indirect": indirect_impacts,
    }


def analyze_impact(
    regulation_clauses: List[Dict[str, Any]],
    policy_clauses: List[Dict[str, Any]],
    searcher,
    top_k: int = 5,
    distance_threshold: float = 5.0,
    chat_model: str = "llama3",
) -> List[Dict[str, Any]]:
    

    build_dependency_graph(policy_clauses)

    results = []
    for reg_clause in regulation_clauses:
        original_trigger = (reg_clause.get("text") or "").strip()
        trigger_text = prepare_trigger(original_trigger, model=chat_model)
        
        trigger_id = reg_clause.get("clause_id", "Preamble")
        if not trigger_text:
            continue

        result = analyze_trigger(
            trigger_id,
            original_trigger,
            trigger_text,
            searcher,
            top_k,
            distance_threshold,
            chat_model,
        )
        results.append(result)

    logger.info(f"Completed impact analysis for {len(results)} regulatory clauses.")
    return results

MAX_QUERY_WORDS = 350

def prepare_trigger(text, model="llama3"):
    if len(text.split()) <= MAX_QUERY_WORDS:
        return text

    prompt = f"""
Summarize the following insurance regulation.

Requirements:
- Preserve all obligations.
- Preserve percentages.
- Preserve dates.
- Preserve monetary values.
- Preserve legal meaning.
- Maximum 200 words.

{text}
"""
    response = ollama.chat(
        model=model,
        messages=[{"role":"user","content":prompt}]
    )
    return response["message"]["content"].strip()