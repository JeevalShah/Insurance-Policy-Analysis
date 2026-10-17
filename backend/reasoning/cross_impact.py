"""
cross_impact.py

Regulatory cross-impact detection purely from the Neo4j graph — zero LLM calls.
Provides:
  1. detect_regulatory_crossfire: finds policy clauses caught between contradictory
     regulatory demands (one says CONFLICTS_WITH, another says COMPLIES_WITH or SUPPORTS).
  2. detect_co_impact_clusters: finds pairs of regulatory clauses that impact the same policy clauses.
"""

import logging
from typing import Any, Dict, List

from reasoning.graph_store import (
    driver,
    NODE_REGULATORY,
    NODE_POLICY,
    EDGE_DEPENDS_ON,
    REL_CONFLICTS_WITH,
    REL_COMPLIES_WITH,
    REL_SUPPORTS,
)

logger = logging.getLogger("CrossImpact")


def detect_regulatory_crossfire(session_id: str) -> List[Dict[str, Any]]:
    """
    Finds policy clauses caught between contradictory regulatory demands —
    one regulatory clause says CONFLICTS_WITH while another says COMPLIES_WITH (or SUPPORTS)
    for the same policy clause.

    Returns:
        List of dicts, each containing:
            caught_clause_id: ID of the caught policy clause
            clause_text: Text of the policy clause
            clause_section: Section of the policy clause
            conflict_reg_id: ID of the conflicting regulatory clause
            conflict_reg_text: Text of the conflicting regulatory clause
            comply_reg_id: ID of the complying/supporting regulatory clause
            comply_reg_text: Text of the complying/supporting regulatory clause
    """
    try:
        with driver.session() as session:
            result = session.run(
                f"""
                MATCH (r1:{NODE_REGULATORY} {{session_id: $sid}})-[:{REL_CONFLICTS_WITH}]->(p:{NODE_POLICY})
                      <-[:{REL_COMPLIES_WITH}|{REL_SUPPORTS}]-(r2:{NODE_REGULATORY} {{session_id: $sid}})
                WHERE r1.id <> r2.id
                RETURN p.id      AS caught_clause_id,
                       p.text    AS clause_text,
                       p.section AS clause_section,
                       r1.id     AS conflict_reg_id,
                       r1.text   AS conflict_reg_text,
                       r2.id     AS comply_reg_id,
                       r2.text   AS comply_reg_text
                ORDER BY p.id
                """,
                {"sid": session_id}
            )

            crossfire: List[Dict[str, Any]] = []
            for record in result:
                data = record.data()
                crossfire.append({
                    "caught_clause_id":  data.get("caught_clause_id"),
                    "clause_text":       data.get("clause_text", ""),
                    "clause_section":    data.get("clause_section", ""),
                    "conflict_reg_id":   data.get("conflict_reg_id"),
                    "conflict_reg_text": data.get("conflict_reg_text", ""),
                    "comply_reg_id":     data.get("comply_reg_id"),
                    "comply_reg_text":   data.get("comply_reg_text", ""),
                })

            logger.info(
                f"detect_regulatory_crossfire: Found {len(crossfire)} contradictory "
                f"regulatory pairs for session {session_id}"
            )
            return crossfire

    except Exception as e:
        logger.error(f"detect_regulatory_crossfire failed for session {session_id}: {e}")
        return []


def detect_co_impact_clusters(session_id: str, min_shared: int = 1) -> List[Dict[str, Any]]:
    """
    Finds pairs of regulatory clauses that impact the same policy clauses.

    Parameters:
        session_id: Session identifier
        min_shared: Minimum number of shared policy clauses required to form a cluster (default: 1)

    Returns:
        List of dicts sorted by shared_clauses descending, each containing:
            reg1_id: First regulatory clause ID
            reg2_id: Second regulatory clause ID
            shared_clauses: Count of shared policy clauses
            shared_clause_ids: List of shared policy clause IDs
    """
    try:
        with driver.session() as session:
            result = session.run(
                f"""
                MATCH (r1:{NODE_REGULATORY} {{session_id: $sid}})-[e1]->(p:{NODE_POLICY})
                      <-[e2]-(r2:{NODE_REGULATORY} {{session_id: $sid}})
                WHERE r1.id < r2.id
                  AND NOT type(e1) = $dep_edge
                  AND NOT type(e2) = $dep_edge
                WITH r1.id AS reg1_id, r2.id AS reg2_id,
                     count(DISTINCT p) AS shared_clauses,
                     collect(DISTINCT p.id) AS shared_clause_ids
                WHERE shared_clauses >= $min_shared
                RETURN reg1_id, reg2_id, shared_clauses, shared_clause_ids
                ORDER BY shared_clauses DESC
                """,
                {
                    "sid": session_id,
                    "min_shared": min_shared,
                    "dep_edge": EDGE_DEPENDS_ON,
                }
            )

            clusters: List[Dict[str, Any]] = []
            for record in result:
                data = record.data()
                clusters.append({
                    "reg1_id":           data.get("reg1_id"),
                    "reg2_id":           data.get("reg2_id"),
                    "shared_clauses":    data.get("shared_clauses", 0),
                    "shared_clause_ids": data.get("shared_clause_ids", []),
                })

            logger.info(
                f"detect_co_impact_clusters: Found {len(clusters)} co-impact clusters "
                f"for session {session_id}"
            )
            return clusters

    except Exception as e:
        logger.error(f"detect_co_impact_clusters failed for session {session_id}: {e}")
        return []
