"""
relationship_invalidator.py

Identifies and invalidates directly affected graph relationships when a document
is updated incrementally. Ensures stale compliance claims and broken dependency
chains are removed or deactivated without traversing unrelated graph components.
"""

from dataclasses import dataclass, field
import logging
import time
from typing import List, Dict, Set, Optional, Any

from .change_manifest import ChangeManifest, ChangeType
from .version_manager import DocumentVersion

logger = logging.getLogger(__name__)


@dataclass
class InvalidationReport:
    """
    Summary of relationships invalidated and candidate pairs scheduled for re-evaluation.
    """
    document_id: str
    session_id: str
    compliance_edges_invalidated: int = 0
    dependency_edges_invalidated: int = 0
    affected_policy_clause_ids: Set[str] = field(default_factory=set)
    affected_regulatory_clause_ids: Set[str] = field(default_factory=set)
    invalidated_relationships: List[Dict[str, Any]] = field(default_factory=list)
    reclassification_candidates: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "session_id": self.session_id,
            "compliance_edges_invalidated": self.compliance_edges_invalidated,
            "dependency_edges_invalidated": self.dependency_edges_invalidated,
            "affected_policy_clause_ids": sorted(list(self.affected_policy_clause_ids)),
            "affected_regulatory_clause_ids": sorted(list(self.affected_regulatory_clause_ids)),
            "invalidated_relationships_count": len(self.invalidated_relationships),
            "reclassification_candidates_count": len(self.reclassification_candidates),
        }


class RelationshipInvalidator:
    """
    Analyzes which graph edges must be severed or recomputed when clauses are modified or deleted.
    """

    def __init__(self, driver=None):
        self.driver = driver

    def plan_invalidation(
        self,
        manifest: ChangeManifest,
        session_id: str,
        doc_type: str = "policy"
    ) -> InvalidationReport:
        """
        Calculates all relationships that must be invalidated for modified and deleted clauses.
        """
        report = InvalidationReport(
            document_id=manifest.document_id,
            session_id=session_id,
        )

        affected_ids = set(manifest.modified) | set(manifest.deleted)
        if doc_type == "policy":
            report.affected_policy_clause_ids.update(affected_ids)
        else:
            report.affected_regulatory_clause_ids.update(affected_ids)

        if not affected_ids:
            return report

        # If live Neo4j driver is present, inspect existing relationships
        if self.driver:
            try:
                with self.driver.session() as session:
                    # 1. Inspect compliance edges connected to affected clauses
                    if doc_type == "policy":
                        cypher_comp = """
                        MATCH (r:RegulatoryClause {session_id: $sid})-[e]->(p:PolicyClause {session_id: $sid})
                        WHERE p.id IN $affected_ids AND type(e) IN ['CONFLICTS_WITH', 'COMPLIES_WITH', 'SUPPORTS', 'IS_REDUNDANT', 'NOT_RELATED']
                        RETURN r.id AS reg_id, p.id AS pol_id, type(e) AS rel_type, e.reasoning AS reasoning
                        """
                    else:
                        cypher_comp = """
                        MATCH (r:RegulatoryClause {session_id: $sid})-[e]->(p:PolicyClause {session_id: $sid})
                        WHERE r.id IN $affected_ids AND type(e) IN ['CONFLICTS_WITH', 'COMPLIES_WITH', 'SUPPORTS', 'IS_REDUNDANT', 'NOT_RELATED']
                        RETURN r.id AS reg_id, p.id AS pol_id, type(e) AS rel_type, e.reasoning AS reasoning
                        """

                    res = session.run(cypher_comp, {"sid": session_id, "affected_ids": list(affected_ids)})
                    for rec in res:
                        report.compliance_edges_invalidated += 1
                        report.invalidated_relationships.append({
                            "type": "compliance",
                            "source_id": rec["reg_id"],
                            "target_id": rec["pol_id"],
                            "relationship": rec["rel_type"],
                            "reasoning": rec.get("reasoning", ""),
                        })
                        report.affected_regulatory_clause_ids.add(rec["reg_id"])
                        report.affected_policy_clause_ids.add(rec["pol_id"])

                    # 2. Inspect dependency edges (if policy doc)
                    if doc_type == "policy":
                        cypher_dep = """
                        MATCH (s:PolicyClause {session_id: $sid})-[r:DEPENDS_ON]-(t:PolicyClause {session_id: $sid})
                        WHERE s.id IN $affected_ids OR t.id IN $affected_ids
                        RETURN s.id AS src_id, t.id AS tgt_id
                        """
                        res_dep = session.run(cypher_dep, {"sid": session_id, "affected_ids": list(affected_ids)})
                        for rec in res_dep:
                            report.dependency_edges_invalidated += 1
                            report.invalidated_relationships.append({
                                "type": "dependency",
                                "source_id": rec["src_id"],
                                "target_id": rec["tgt_id"],
                                "relationship": "DEPENDS_ON",
                            })
                            report.affected_policy_clause_ids.add(rec["src_id"])
                            report.affected_policy_clause_ids.add(rec["tgt_id"])

            except Exception as e:
                logger.warning(f"Error querying relationships to invalidate: {e}")

        else:
            # Fallback estimation when driver is offline (e.g. unit tests or dry-run)
            for cid in affected_ids:
                report.invalidated_relationships.append({
                    "type": "estimated",
                    "clause_id": cid,
                    "reason": f"Clause {cid} was modified/deleted; connected edges invalidated."
                })
                report.compliance_edges_invalidated += 1

        return report

    def execute_invalidation(
        self,
        plan: InvalidationReport,
        session_id: str,
        dry_run: bool = False
    ) -> InvalidationReport:
        """
        Executes relationship deactivation in Neo4j.
        In dry-run mode, no mutations occur.
        """
        if dry_run or not self.driver:
            return plan

        affected_ids = list(plan.affected_policy_clause_ids | plan.affected_regulatory_clause_ids)
        if not affected_ids:
            return plan

        try:
            with self.driver.session() as session:
                with session.begin_transaction() as tx:
                    cypher = """
                    MATCH (n {session_id: $sid})-[r]-(m {session_id: $sid})
                    WHERE (n.id IN $affected_ids OR m.id IN $affected_ids)
                      AND type(r) <> 'PREVIOUS_VERSION'
                    DELETE r
                    """
                    tx.run(cypher, {"sid": session_id, "affected_ids": affected_ids})
                    tx.commit()
            logger.info(f"Invalidated active edges for {len(affected_ids)} affected clauses in session {session_id}")
        except Exception as e:
            logger.error(f"Failed to execute relationship invalidation: {e}")

        return plan
