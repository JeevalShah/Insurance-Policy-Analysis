"""
Dependency graph for indirect-impact propagation.

The original prototype used a hardcoded `DEPENDENCIES` dict (a documented
current limitation in the README). This version auto-builds a dependency
graph per session by scanning each clause's text for references to other
clause IDs (e.g. "see Clause 4.4", "as per clause 2.2"), and keeps room
for a small set of manual overrides layered on top when the auto-detected
graph misses a real operational relationship.
"""
import re
import logging
from typing import Dict, List, Set, Any

logger = logging.getLogger("DependencyGraph")

_CLAUSE_REF_PATTERN = re.compile(
    r'\bclause[s]?\.?\s+(\d+(?:\.\d+)*)\b',
    re.IGNORECASE
)

# Optional manual overrides: clause_id -> [affected_clause_ids].
# Auto-detected references are merged with these, so this can stay empty
# and the graph still works from cross-references alone.
MANUAL_DEPENDENCIES: Dict[str, List[str]] = {}


def build_dependency_graph(clauses: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Scans clause text for references to other clause IDs and builds an
    adjacency map: clause_id -> list of clause_ids it operationally affects.

    Args:
        clauses (List[Dict[str, Any]]): Structured clause list, each with
            'clause_id' and 'text'.

    Returns:
        Dict[str, List[str]]: Dependency adjacency map.
    """
    known_ids = {c.get("clause_id") for c in clauses if c.get("clause_id")}
    graph: Dict[str, Set[str]] = {}

    for clause in clauses:
        clause_id = clause.get("clause_id")
        text = clause.get("text") or ""
        if not clause_id:
            continue

        referenced = set(_CLAUSE_REF_PATTERN.findall(text))
        referenced = {r for r in referenced if r in known_ids and r != clause_id}

        if referenced:
            graph.setdefault(clause_id, set()).update(referenced)

    for source, targets in MANUAL_DEPENDENCIES.items():
        graph.setdefault(source, set()).update(t for t in targets if t in known_ids)

    result = {k: sorted(v) for k, v in graph.items()}
    logger.info(f"Built dependency graph with {len(result)} source clauses.")
    return result


def get_indirect_impacts(
    direct_clause_ids: List[str],
    dependency_graph: Dict[str, List[str]],
    max_hops: int = 2
) -> Set[str]:
    """
    Traverses the dependency graph outward from directly impacted clauses
    to find indirectly impacted ones, up to `max_hops` hops away.
    """
    direct_set = set(direct_clause_ids)
    frontier = set(direct_clause_ids)
    indirect: Set[str] = set()

    for _ in range(max_hops):
        next_frontier: Set[str] = set()
        for clause_id in frontier:
            for dep in dependency_graph.get(clause_id, []):
                if dep not in direct_set and dep not in indirect:
                    indirect.add(dep)
                    next_frontier.add(dep)
        if not next_frontier:
            break
        frontier = next_frontier

    return indirect
