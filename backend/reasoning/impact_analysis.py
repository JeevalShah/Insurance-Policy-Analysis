"""
impact_analysis.py

Executes zero-LLM query-time impact analysis.
Relies entirely on the pre-computed compliance graph in Neo4j to guarantee
sub-second response times and eliminate redundant generative LLM costs.
"""

import logging
from typing import Dict, Any, List

# Adjust the import path based on your project structure
from reasoning.graph_store import (
    driver, 
    NODE_REGULATORY, 
    NODE_POLICY, 
    EDGE_DEPENDS_ON
)

logger = logging.getLogger(__name__)

class ImpactAnalyzer:
    """
    Analyzes regulatory impacts exclusively through Graph Traversals.
    No LLM calls or vector searches occur here.
    """
    def __init__(self, max_hops: int = 3):
        self.max_hops = max_hops

    def analyze_regulatory_impact(self, session_id: str, reg_clause_id: str) -> Dict[str, Any]:
        """
        Fetches direct and indirect policy impacts instantly from the Neo4j graph.
        """
        logger.info(f"Running zero-LLM impact analysis for reg_clause_id={reg_clause_id}, session_id={session_id}")
        
        try:
            direct_impacts = self._get_direct_impacts(session_id, reg_clause_id)
            indirect_impacts = self._get_indirect_impacts(session_id, reg_clause_id)
            
            return {
                "status": "success",
                "session_id": session_id,
                "regulatory_clause_id": reg_clause_id,
                "direct_impacts": direct_impacts,
                "indirect_impacts": indirect_impacts,
                "total_impacted_policies": len(direct_impacts) + len(indirect_impacts),
                "analysis_type": "Zero-LLM Graph Traversal"
            }
        except Exception as e:
            logger.error(f"Failed to analyze impact for {reg_clause_id}: {e}")
            return {
                "status": "error",
                "message": "Impact analysis failed."
            }

    def _get_direct_impacts(self, session_id: str, reg_clause_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves pre-computed compliance relationships and their cached LLM reasoning.
        """
        query = f"""
        MATCH (r:{NODE_REGULATORY} {{id: $rid, session_id: $sid}})
              -[e:CONFLICTS_WITH|COMPLIES_WITH|SUPPORTS|IS_REDUNDANT]->
              (p:{NODE_POLICY})
        RETURN p.id          AS policy_id,
               p.text        AS text,
               p.section     AS section,
               type(e)       AS relationship,
               e.classified_at AS classified_at,
               e.reasoning     AS reasoning
        ORDER BY relationship, p.id
        """
        with driver.session() as session:
            result = session.run(query, {"rid": reg_clause_id, "sid": session_id})
            return [record.data() for record in result]

    def _get_indirect_impacts(self, session_id: str, reg_clause_id: str) -> List[Dict[str, Any]]:
        """
        Traverses DEPENDS_ON edges to find operational documents impacted by direct policy changes.
        """
        hops = int(self.max_hops) if self.max_hops else 3
        query = f"""
        MATCH (r:{NODE_REGULATORY} {{id: $rid, session_id: $sid}})
              -[e:CONFLICTS_WITH|COMPLIES_WITH|SUPPORTS]->
              (direct:{NODE_POLICY})
        WITH direct
        MATCH path = (direct)-[:{EDGE_DEPENDS_ON}*1..{hops}]->(indirect:{NODE_POLICY} {{session_id: $sid}})
        WHERE indirect.id <> direct.id
        RETURN DISTINCT
               indirect.id      AS policy_id,
               indirect.text    AS text,
               indirect.section AS section,
               length(path)     AS hop_count,
               direct.id        AS triggered_by,
               [n IN nodes(path) | n.id] AS impact_chain,
               'INDIRECT_DEPENDENCY' AS relationship
        ORDER BY hop_count, indirect.id
        """
        with driver.session() as session:
            result = session.run(query, {"rid": reg_clause_id, "sid": session_id})
            return [record.data() for record in result]