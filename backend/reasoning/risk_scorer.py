"""
risk_scorer.py

Computes compliance risk scores purely from the Neo4j graph — zero LLM calls.
Provides:
  1. compute_document_risk: aggregate document-level compliance health and risk.
  2. compute_clause_risk: individual policy clause risk score based on direct conflicts,
     redundancies, and cascading dependency risks.
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
    REL_IS_REDUNDANT,
)

logger = logging.getLogger("RiskScorer")


def compute_document_risk(session_id: str) -> Dict[str, Any]:
    """
    Computes document-wide compliance risk metrics from the Neo4j graph for a given session.

    Returns:
        Dict containing:
            total_policy_clauses: int
            total_regulatory_clauses: int
            conflict_count: number of CONFLICTS_WITH edges
            compliant_count: number of COMPLIES_WITH edges
            supporting_count: number of SUPPORTS edges
            redundant_count: number of IS_REDUNDANT edges
            unmatched_count: policy clauses with no incoming compliance edges
            health_pct: float rounded to 1 decimal place
            risk_level: "LOW" (>=80), "MEDIUM" (>=50), "HIGH" (>=25), "CRITICAL" (<25)
            high_risk_clauses: list of dicts for policy clauses that have conflicts
    """
    try:
        with driver.session() as session:
            # 1. Total counts of policy and regulatory clauses
            pol_count = session.run(
                f"MATCH (p:{NODE_POLICY} {{session_id: $sid}}) RETURN count(p) AS c",
                {"sid": session_id}
            ).single()["c"]

            reg_count = session.run(
                f"MATCH (r:{NODE_REGULATORY} {{session_id: $sid}}) RETURN count(r) AS c",
                {"sid": session_id}
            ).single()["c"]

            if pol_count == 0 and reg_count == 0:
                logger.warning(f"No graph data found for session {session_id}")
                return {}

            # 2. Compliance edge counts
            edge_res = session.run(
                f"""
                MATCH (r:{NODE_REGULATORY} {{session_id: $sid}})-[e]->(p:{NODE_POLICY})
                WHERE type(e) IN ['{REL_CONFLICTS_WITH}', '{REL_COMPLIES_WITH}', '{REL_SUPPORTS}', '{REL_IS_REDUNDANT}']
                RETURN type(e) AS rel_type, count(e) AS count
                """,
                {"sid": session_id}
            )
            edge_counts = {rec["rel_type"]: rec["count"] for rec in edge_res}
            conflict_count   = edge_counts.get(REL_CONFLICTS_WITH, 0)
            compliant_count  = edge_counts.get(REL_COMPLIES_WITH, 0)
            supporting_count = edge_counts.get(REL_SUPPORTS, 0)
            redundant_count  = edge_counts.get(REL_IS_REDUNDANT, 0)

            # 3. Unmatched policy clauses (no incoming compliance edges from regulatory clauses)
            unmatched_res = session.run(
                f"""
                MATCH (p:{NODE_POLICY} {{session_id: $sid}})
                WHERE NOT (:{NODE_REGULATORY} {{session_id: $sid}})-[:{REL_CONFLICTS_WITH}|{REL_COMPLIES_WITH}|{REL_SUPPORTS}|{REL_IS_REDUNDANT}]->(p)
                RETURN count(p) AS c
                """,
                {"sid": session_id}
            )
            unmatched_count = unmatched_res.single()["c"]

            # 4. High-risk clauses (policy clauses with CONFLICTS_WITH edges)
            high_risk_res = session.run(
                f"""
                MATCH (r:{NODE_REGULATORY} {{session_id: $sid}})-[e:{REL_CONFLICTS_WITH}]->(p:{NODE_POLICY} {{session_id: $sid}})
                RETURN p.id                   AS clause_id,
                       p.section              AS section,
                       count(e)               AS conflict_count,
                       collect(DISTINCT r.id) AS conflicting_reg_ids
                ORDER BY conflict_count DESC, p.id
                """,
                {"sid": session_id}
            )

            high_risk_clauses: List[Dict[str, Any]] = []
            for rec in high_risk_res:
                data = rec.data()
                high_risk_clauses.append({
                    "clause_id":           data.get("clause_id"),
                    "section":             data.get("section", ""),
                    "conflict_count":      data.get("conflict_count", 0),
                    "conflicting_reg_ids": data.get("conflicting_reg_ids", []),
                })

            clauses_with_conflicts = len(high_risk_clauses)

            # 5. Health percentage & Risk Level
            if pol_count > 0:
                health_pct = round(100.0 * (pol_count - clauses_with_conflicts) / pol_count, 1)
            else:
                health_pct = 100.0

            if health_pct >= 80.0:
                risk_level = "LOW"
            elif health_pct >= 50.0:
                risk_level = "MEDIUM"
            elif health_pct >= 25.0:
                risk_level = "HIGH"
            else:
                risk_level = "CRITICAL"

            return {
                "total_policy_clauses":     pol_count,
                "total_regulatory_clauses": reg_count,
                "conflict_count":           conflict_count,
                "compliant_count":          compliant_count,
                "supporting_count":         supporting_count,
                "redundant_count":          redundant_count,
                "unmatched_count":          unmatched_count,
                "health_pct":               health_pct,
                "risk_level":               risk_level,
                "high_risk_clauses":        high_risk_clauses,
            }

    except Exception as e:
        logger.error(f"compute_document_risk failed for session {session_id}: {e}")
        return {}


def compute_clause_risk(session_id: str, clause_id: str) -> Dict[str, Any]:
    """
    Computes risk score and dependency metrics for a specific policy clause.

    Returns:
        Dict containing:
            clause_id: str
            direct_conflicts: count of CONFLICTS_WITH edges targeting this clause
            direct_compliant: count of COMPLIES_WITH edges
            is_dependency_of: list of clause IDs that depend on this clause (reverse DEPENDS_ON)
            depends_on: list of clause IDs this clause depends on
            cascading_risk: bool (True if conflicts > 0 and dependent clauses exist)
            risk_score: float 0-1 (conflicts * 0.4 + (0.3 if cascading else 0) + redundant * 0.1, max 1.0)
    """
    try:
        with driver.session() as session:
            # 1. Ensure clause exists for this session
            exists = session.run(
                f"MATCH (p:{NODE_POLICY} {{id: $cid, session_id: $sid}}) RETURN p.id AS id",
                {"cid": clause_id, "sid": session_id}
            ).single()

            if not exists:
                logger.warning(f"Clause {clause_id} not found in session {session_id}")
                return {}

            # 2. Direct compliance edge counts targeting this clause
            edge_res = session.run(
                f"""
                MATCH (r:{NODE_REGULATORY} {{session_id: $sid}})-[e]->(p:{NODE_POLICY} {{id: $cid, session_id: $sid}})
                WHERE type(e) IN ['{REL_CONFLICTS_WITH}', '{REL_COMPLIES_WITH}', '{REL_IS_REDUNDANT}']
                RETURN type(e) AS rel_type, count(e) AS count
                """,
                {"cid": clause_id, "sid": session_id}
            )
            edge_counts = {rec["rel_type"]: rec["count"] for rec in edge_res}
            direct_conflicts = edge_counts.get(REL_CONFLICTS_WITH, 0)
            direct_compliant = edge_counts.get(REL_COMPLIES_WITH, 0)
            redundant        = edge_counts.get(REL_IS_REDUNDANT, 0)

            # 3. Clauses that depend on this clause (reverse DEPENDS_ON: other -> p)
            dep_of_res = session.run(
                f"""
                MATCH (other:{NODE_POLICY} {{session_id: $sid}})-[:{EDGE_DEPENDS_ON}]->(p:{NODE_POLICY} {{id: $cid, session_id: $sid}})
                RETURN DISTINCT other.id AS dep_id
                ORDER BY dep_id
                """,
                {"cid": clause_id, "sid": session_id}
            )
            is_dependency_of = [rec["dep_id"] for rec in dep_of_res if rec["dep_id"]]

            # 4. Clauses this clause depends on (forward DEPENDS_ON: p -> target)
            dep_on_res = session.run(
                f"""
                MATCH (p:{NODE_POLICY} {{id: $cid, session_id: $sid}})-[:{EDGE_DEPENDS_ON}]->(target:{NODE_POLICY} {{session_id: $sid}})
                RETURN DISTINCT target.id AS dep_id
                ORDER BY dep_id
                """,
                {"cid": clause_id, "sid": session_id}
            )
            depends_on = [rec["dep_id"] for rec in dep_on_res if rec["dep_id"]]

            # 5. Cascading risk & risk score calculation
            cascading_risk = bool(direct_conflicts > 0 and len(is_dependency_of) > 0)
            raw_score = (direct_conflicts * 0.4) + (0.3 if cascading_risk else 0.0) + (redundant * 0.1)
            risk_score = round(min(1.0, max(0.0, raw_score)), 2)

            return {
                "clause_id":        clause_id,
                "direct_conflicts": direct_conflicts,
                "direct_compliant": direct_compliant,
                "is_dependency_of": is_dependency_of,
                "depends_on":       depends_on,
                "cascading_risk":   cascading_risk,
                "risk_score":       risk_score,
            }

    except Exception as e:
        logger.error(f"compute_clause_risk failed for clause {clause_id} in session {session_id}: {e}")
        return {}
