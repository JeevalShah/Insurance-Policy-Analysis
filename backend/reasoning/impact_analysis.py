import logging
from typing import Any, Dict, List

from reasoning.relationshipclassifier import classify_relationship
from reasoning.dependency_graph import build_dependency_graph, get_indirect_impacts

logger = logging.getLogger("ImpactAnalysis")


def generate_reasoning(trigger: str, clause_text: str, relationship: str, model: str = "llama3") -> str:
    """LLM-generated 1-2 sentence explanation of why a relationship holds."""
    import ollama

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
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Reasoning generation failed: {e}")
        return "Reasoning unavailable: the local language model could not be reached."


def analyze_trigger(
    trigger_id: str,
    trigger_text: str,
    searcher,
    dependency_graph: Dict[str, List[str]],
    top_k: int,
    distance_threshold: float,
    chat_model: str,
) -> Dict[str, Any]:
    """Runs direct retrieval + classification + indirect propagation for one regulatory clause."""
    retrieved = searcher.search(trigger_text, k=top_k, distance_threshold=distance_threshold)

    direct_impacts: Dict[str, Any] = {}
    for r in retrieved:
        clause = r["clause"]
        clause_id = clause["clause_id"]
        direct_impacts[clause_id] = {
            "text": clause["text"],
            "distance": r["distance"],
        }

    for clause_id, data in direct_impacts.items():
        relationship = classify_relationship(trigger_text, data["text"], model=chat_model)
        reasoning = generate_reasoning(trigger_text, data["text"], relationship, model=chat_model)
        data["relationship"] = relationship
        data["reasoning"] = reasoning

    indirect_impacts = get_indirect_impacts(list(direct_impacts.keys()), dependency_graph)

    return {
        "trigger_id": trigger_id,
        "trigger_text": trigger_text,
        "direct": direct_impacts,
        "indirect": sorted(indirect_impacts),
    }


def analyze_impact(
    regulation_clauses: List[Dict[str, Any]],
    policy_clauses: List[Dict[str, Any]],
    searcher,
    top_k: int = 5,
    distance_threshold: float = 1.0,
    chat_model: str = "llama3",
) -> List[Dict[str, Any]]:
    """
    Runs the full impact analysis: each regulation clause becomes a
    regulatory trigger, searched against the policy index, classified, and
    propagated through the auto-built dependency graph.

    Args:
        regulation_clauses: structured clauses extracted from the regulation doc.
        policy_clauses: structured clauses extracted from the company policy doc(s),
            i.e. the corpus that was embedded and indexed.
        searcher: a retrieval.semanticsearch.SemanticSearch bound to the policy index.

    Returns:
        List of per-regulation-clause impact analysis results.
    """
    dependency_graph = build_dependency_graph(policy_clauses)

    results = []
    for reg_clause in regulation_clauses:
        trigger_id = reg_clause.get("clause_id", "Preamble")
        trigger_text = (reg_clause.get("text") or "").strip()
        if not trigger_text:
            continue

        result = analyze_trigger(
            trigger_id,
            trigger_text,
            searcher,
            dependency_graph,
            top_k,
            distance_threshold,
            chat_model,
        )
        results.append(result)

    logger.info(f"Completed impact analysis for {len(results)} regulatory clauses.")
    return results
