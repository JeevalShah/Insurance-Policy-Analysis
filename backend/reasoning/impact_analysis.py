"""
impact_analysis.py

At query time this file makes ZERO LLM calls and ZERO FAISS searches.
All classification and reasoning happened at ingestion time and is stored
as edges in Neo4j.

This file only:
  1. Reads specific compliance edges for each regulatory clause (direct impacts)
  2. Traverses DEPENDS_ON chains from those clauses             (indirect impacts)
  3. Assembles the aggregate compliance summary
"""

import logging
from typing import Any, Dict, List, Optional

from reasoning.graph_store import (
    driver,
    NODE_REGULATORY,
    NODE_POLICY,
    EDGE_DEPENDS_ON,
    REL_NOT_RELATED,
)

logger = logging.getLogger("ImpactAnalysis")


# Map specific Neo4j edge types back to the human-readable relationship label
# expected by the frontend UI and chat service
REL_TYPE_TO_LABEL = {
    "CONFLICTS_WITH": "CONFLICT",
    "COMPLIES_WITH":  "COMPLIANT",
    "SUPPORTS":       "SUPPORTING",
    "IS_REDUNDANT":   "REDUNDANT",
    "NOT_RELATED":    "NOT_RELATED"
}


# ---------------------------------------------------------------------------
# Direct impacts — read specific compliance edges written at ingestion time
# ---------------------------------------------------------------------------

def get_direct_impacts(
    reg_clause_id: str,
    session_id: str,
    exclude_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if exclude_types is None:
        exclude_types = [REL_NOT_RELATED]

    try:
        with driver.session() as session:
            result = session.run(
                f"""
                MATCH (r:{NODE_REGULATORY} {{id: $rid, session_id: $sid}})
                      -[e]->
                      (p:{NODE_POLICY})
                WHERE NOT type(e) IN $exclude AND NOT type(e) = $dep_edge
                RETURN p.id            AS clause_id,
                       p.text          AS text,
                       p.section       AS section,
                       type(e)         AS rel_type,
                       e.reasoning     AS reasoning,
                       e.confidence    AS confidence,
                       e.classified_at AS classified_at
                ORDER BY rel_type, p.id
                """,
                {
                    "rid":      reg_clause_id,
                    "sid":      session_id,
                    "exclude":  exclude_types,
                    "dep_edge": EDGE_DEPENDS_ON,
                }
            )

            impacts: Dict[str, Any] = {}
            for record in result:
                data = record.data()
                clause_id = data.get("clause_id")
                rel_type  = data.get("rel_type", "NOT_RELATED")
                relationship_label = REL_TYPE_TO_LABEL.get(rel_type, rel_type)

                if clause_id:
                    impacts[clause_id] = {
                        "text":          data.get("text", ""),
                        "section":       data.get("section", ""),
                        "relationship":  relationship_label,
                        "reasoning":     data.get("reasoning", ""),
                        "confidence":    data.get("confidence"),
                        "classified_at": data.get("classified_at"),
                    }

        logger.debug(f"Direct impacts for {reg_clause_id}: {len(impacts)} clauses")
        return impacts

    except Exception as e:
        logger.error(f"get_direct_impacts failed for {reg_clause_id}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Indirect impacts — traverse DEPENDS_ON chains from directly impacted clauses
# ---------------------------------------------------------------------------

def get_indirect_impacts(
    reg_clause_id: str,
    session_id: str,
    max_hops: int = 3,
) -> List[Dict[str, Any]]:
    try:
        with driver.session() as session:
            result = session.run(
                f"""
                MATCH (r:{NODE_REGULATORY} {{id: $rid, session_id: $sid}})
                      -[e:CONFLICTS_WITH|COMPLIES_WITH|SUPPORTS]->
                      (direct:{NODE_POLICY})
                WITH collect(DISTINCT direct) AS direct_nodes

                UNWIND direct_nodes AS direct
                MATCH path = (direct)-[:{EDGE_DEPENDS_ON}*1..{max_hops}]->(indirect:{NODE_POLICY})
                WHERE NOT indirect IN direct_nodes

                RETURN DISTINCT
                       indirect.id      AS clause_id,
                       indirect.text    AS text,
                       indirect.section AS section,
                       length(path)     AS hop_count,
                       direct.id        AS triggered_by,
                       [n IN nodes(path) | n.id] AS impact_chain
                ORDER BY hop_count, indirect.id
                """,
                {
                    "rid": reg_clause_id,
                    "sid": session_id,
                }
            )

            indirect: List[Dict[str, Any]] = []
            for record in result:
                data = record.data()
                indirect.append({
                    "clause_id":    data.get("clause_id"),
                    "text":         data.get("text", ""),
                    "section":      data.get("section", ""),
                    "relationship": "INDIRECT",
                    "hop_count":    data.get("hop_count"),
                    "triggered_by": data.get("triggered_by"),
                    "impact_chain": data.get("impact_chain", []),
                })

        return indirect

    except Exception as e:
        logger.error(f"get_indirect_impacts failed for {reg_clause_id}: {e}")
        return []


# ---------------------------------------------------------------------------
# Compliance summary — aggregate stats for reporting / paper
# ---------------------------------------------------------------------------

def get_compliance_summary(session_id: str) -> Dict[str, Any]:
    try:
        with driver.session() as session:
            # Distribution of relationship types
            dist_res = session.run(
                f"""
                MATCH (r:{NODE_REGULATORY} {{session_id: $sid}})
                      -[e]->
                      (p:{NODE_POLICY})
                WHERE NOT type(e) = $dep_edge
                RETURN type(e) AS rel_type, count(*) AS count
                ORDER BY count DESC
                """,
                {"sid": session_id, "dep_edge": EDGE_DEPENDS_ON}
            )
            label_dist = {
                REL_TYPE_TO_LABEL.get(rec["rel_type"], rec["rel_type"]): rec["count"]
                for rec in dist_res
            }

            # Conflicts list
            conflict_res = session.run(
                f"""
                MATCH (r:{NODE_REGULATORY} {{session_id: $sid}})
                      -[e:CONFLICTS_WITH]->
                      (p:{NODE_POLICY})
                RETURN r.id        AS reg_id,
                       r.section   AS reg_section,
                       p.id        AS pol_id,
                       p.section   AS pol_section,
                       e.reasoning AS reasoning,
                       e.confidence AS confidence
                ORDER BY r.id, p.id
                """,
                {"sid": session_id}
            )
            conflict_pairs = [rec.data() for rec in conflict_res]

            # Unmatched policy clauses
            unmatched_res = session.run(
                f"""
                MATCH (p:{NODE_POLICY} {{session_id: $sid}})
                WHERE NOT (:{NODE_REGULATORY})-[]->(p)
                RETURN p.id AS clause_id, p.section AS section
                ORDER BY p.id
                """,
                {"sid": session_id}
            )
            unmatched = [rec.data() for rec in unmatched_res]

            # Counts
            reg_count = session.run(
                f"MATCH (r:{NODE_REGULATORY} {{session_id: $sid}}) RETURN count(r) AS c",
                {"sid": session_id}
            ).single()["c"]

            pol_count = session.run(
                f"MATCH (p:{NODE_POLICY} {{session_id: $sid}}) RETURN count(p) AS c",
                {"sid": session_id}
            ).single()["c"]

        return {
            "total_regulatory_clauses": reg_count,
            "total_policy_clauses":     pol_count,
            "label_distribution":       label_dist,
            "conflict_pairs":           conflict_pairs,
            "unmatched_policy_clauses": unmatched,
        }

    except Exception as e:
        logger.error(f"get_compliance_summary failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze_impact(
    session_id: str,
    regulation_clauses: List[Dict[str, Any]],
    max_hops: int = 3,
    exclude_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    for reg_clause in regulation_clauses:
        reg_id   = reg_clause.get("clause_id", "")
        reg_text = (reg_clause.get("text") or "").strip()

        if not reg_id or not reg_text:
            continue

        direct   = get_direct_impacts(reg_id, session_id, exclude_types)
        indirect = get_indirect_impacts(reg_id, session_id, max_hops)

        results.append({
            "trigger_id":   reg_id,
            "trigger_text": reg_text,
            "direct":       direct,
            "indirect":     indirect,
        })

    logger.info(
        f"analyze_impact: {len(results)} regulatory clauses processed "
        f"for session={session_id} — 0 LLM calls, 0 FAISS searches"
    )
    return results