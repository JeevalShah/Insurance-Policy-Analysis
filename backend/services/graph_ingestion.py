"""
graph_ingestion.py

Owns the entire Neo4j ingestion contract. Called once per document set
upload; never called at query time.

Ingestion stages (in order):
1. Clear stale graph data for this session's source docs (idempotency)
2. Write RegulatoryClause nodes (Batched UNWIND)
3. Write PolicyClause nodes (Batched UNWIND)
4. Write DEPENDS_ON edges (Batched UNWIND)
5. Find candidate pairs (FAISS — candidate generation)
6. Classify each pair & extract reasoning (LLM - Batched & Concurrent)
7. Write specific edges (CONFLICTS_WITH, COMPLIES_WITH, etc. with reasoning)
8. Return IngestionReport (timing + counts for benchmarking)
"""

import time
import logging
import math
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import re
import json

from reasoning.graph_store import (
    driver,
    NODE_REGULATORY,
    NODE_POLICY,
    EDGE_DEPENDS_ON,
    LABEL_TO_REL_TYPE,
    REL_NOT_RELATED,
    ALL_COMPLIANCE_RELS,
    ensure_indexes,
)

logger = logging.getLogger(__name__)


@dataclass
class StageTimer:
    name: str
    elapsed_s: float
    record_count: int
    notes: str = ""


@dataclass
class IngestionReport:
    session_id: str
    source_docs: List[str]
    regulatory_clauses_written: int = 0
    policy_clauses_written: int     = 0
    dependency_edges_written: int   = 0
    candidate_pairs_found: int      = 0
    compliance_edges_written: int   = 0
    unrelated_pairs_classified: int = 0
    llm_calls_made: int             = 0
    stages: List[StageTimer]        = field(default_factory=list)
    errors: List[str]               = field(default_factory=list)

    @property
    def total_elapsed_s(self) -> float:
        return sum(s.elapsed_s for s in self.stages)

    def summary(self) -> str:
        lines = [
            f"[IngestionReport] session={self.session_id}",
            f"  Regulatory clauses : {self.regulatory_clauses_written}",
            f"  Policy clauses     : {self.policy_clauses_written}",
            f"  DEPENDS_ON edges   : {self.dependency_edges_written}",
            f"  Candidate pairs    : {self.candidate_pairs_found}",
            f"  COMPLIANCE edges   : {self.compliance_edges_written}",
            f"  Unrelated pairs    : {self.unrelated_pairs_classified}",
            f"  LLM calls made     : {self.llm_calls_made}",
            f"  Total time         : {self.total_elapsed_s:.2f}s",
        ]
        for st in self.stages:
            lines.append(f"    [{st.name}] {st.elapsed_s:.2f}s  ({st.record_count} records)  {st.notes}")
        if self.errors:
            lines.append(f"  Errors ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"    - {e}")
        return "\n".join(lines)


class GraphIngestionPipeline:
    """
    Orchestrates the full ingestion sequence for one document upload session.
    """

    def __init__(
        self,
        embedder,
        classifier,
        index,
        top_k: int = 10,
        model: str = "llama3",
        distance_threshold: float = 0.6,  # Tightened FAISS Distance Guardrails
        max_embedding_workers: int = 10,
        max_llm_workers: int = 2,
    ):
        self.embedder           = embedder
        self.classifier         = classifier
        self.index              = index
        self.top_k              = top_k
        self.model              = model
        self.distance_threshold = distance_threshold
        
        # Tune Concurrency Limits: Decouple lightweight tasks from heavy LLM generation
        self.embedding_executor = ThreadPoolExecutor(max_workers=max_embedding_workers)
        self.llm_executor       = ThreadPoolExecutor(max_workers=max_llm_workers)
        ensure_indexes()

    def ingest(
        self,
        session_id: str,
        regulation_clauses: List[Dict[str, Any]],
        policy_clauses: List[Dict[str, Any]],
        dependency_graph: Dict[str, List[str]],
        source_docs: Optional[List[str]] = None,
    ) -> IngestionReport:
        report = IngestionReport(
            session_id=session_id,
            source_docs=source_docs or [],
        )

        steps = [
            ("clear_stale",        lambda: self._clear_session_nodes(session_id, report)),
            ("write_reg_nodes",    lambda: self._write_regulatory_nodes(regulation_clauses, session_id, report)),
            ("write_pol_nodes",    lambda: self._write_policy_nodes(policy_clauses, session_id, report)),
            ("write_dep_edges",    lambda: self._write_dependency_edges(dependency_graph, session_id, report)),
            ("classify_and_write", lambda: self._classify_and_write_compliance_edges(
                                               regulation_clauses, policy_clauses,
                                               session_id, report)),
        ]

        for stage_name, fn in steps:
            t0 = time.perf_counter()
            try:
                fn()
            except Exception as e:
                msg = f"Stage '{stage_name}' failed: {e}"
                logger.exception(msg)
                report.errors.append(msg)
            finally:
                elapsed = time.perf_counter() - t0
                if not report.stages or report.stages[-1].name != stage_name:
                    report.stages.append(StageTimer(stage_name, elapsed, 0, "fallback timer"))

        logger.info(report.summary())
        return report

    def _clear_session_nodes(self, session_id: str, report: IngestionReport) -> None:
        t0 = time.perf_counter()
        with driver.session() as session:
            session.run(
                f"MATCH (n:{NODE_REGULATORY} {{session_id: $sid}}) DETACH DELETE n",
                {"sid": session_id}
            )
            session.run(
                f"MATCH (n:{NODE_POLICY} {{session_id: $sid}}) DETACH DELETE n",
                {"sid": session_id}
            )
        elapsed = time.perf_counter() - t0
        report.stages.append(StageTimer("clear_stale", elapsed, 0,
            f"cleared stale nodes for session {session_id}"))
        logger.info(f"Cleared stale graph data for session={session_id}")

    def _write_regulatory_nodes(self, clauses: List[Dict[str, Any]], session_id: str, report: IngestionReport) -> None:
        t0 = time.perf_counter()
        batch = []
        for clause in clauses:
            clause_id  = clause.get("clause_id") or clause.get("id") or ""
            text       = clause.get("text", "")
            if not clause_id or not text:
                continue
            batch.append({
                "id": clause_id,
                "text": text[:2000],
                "source_doc": clause.get("source_doc", ""),
                "section": clause.get("section", ""),
            })

        written = len(batch)
        if batch:
            cypher = f"""
            UNWIND $batch AS item
            MERGE (n:{NODE_REGULATORY} {{id: item.id, session_id: $sid}})
            SET   n.text       = item.text,
                  n.source_doc = item.source_doc,
                  n.section    = item.section
            """
            with driver.session() as session:
                session.run(cypher, {"batch": batch, "sid": session_id})

        elapsed = time.perf_counter() - t0
        report.regulatory_clauses_written = written
        report.stages.append(StageTimer("write_reg_nodes", elapsed, written))

    def _write_policy_nodes(self, clauses: List[Dict[str, Any]], session_id: str, report: IngestionReport) -> None:
        t0 = time.perf_counter()
        batch = []
        for clause in clauses:
            clause_id  = clause.get("clause_id") or clause.get("id") or ""
            text       = clause.get("text", "")
            if not clause_id or not text:
                continue
            batch.append({
                "id": clause_id,
                "text": text[:2000],
                "source_doc": clause.get("source_doc", ""),
                "section": clause.get("section", ""),
            })

        written = len(batch)
        if batch:
            cypher = f"""
            UNWIND $batch AS item
            MERGE (n:{NODE_POLICY} {{id: item.id, session_id: $sid}})
            SET   n.text       = item.text,
                  n.source_doc = item.source_doc,
                  n.section    = item.section
            """
            with driver.session() as session:
                session.run(cypher, {"batch": batch, "sid": session_id})

        elapsed = time.perf_counter() - t0
        report.policy_clauses_written = written
        report.stages.append(StageTimer("write_pol_nodes", elapsed, written))

    def _write_dependency_edges(self, dependency_graph: Dict[str, List[str]], session_id: str, report: IngestionReport) -> None:
        t0 = time.perf_counter()
        pairs = [{"src": s, "tgt": t} for s, targets in dependency_graph.items() for t in targets]
        written = len(pairs)
        if pairs:
            cypher = f"""
            UNWIND $pairs AS pair
            MATCH (s:{NODE_POLICY} {{id: pair.src, session_id: $sid}})
            MATCH (t:{NODE_POLICY} {{id: pair.tgt, session_id: $sid}})
            MERGE (s)-[:{EDGE_DEPENDS_ON}]->(t)
            """
            with driver.session() as session:
                session.run(cypher, {"pairs": pairs, "sid": session_id})

        elapsed = time.perf_counter() - t0
        report.dependency_edges_written = written
        report.stages.append(StageTimer("write_dep_edges", elapsed, written))

    def _classify_and_write_compliance_edges(
        self,
        regulation_clauses: List[Dict[str, Any]],
        policy_clauses: List[Dict[str, Any]],
        session_id: str,
        report: IngestionReport,
    ) -> None:
        t0 = time.perf_counter()
        
        logger.info("Starting policy embedding generation")
        vectors, valid_clauses = self.embedder.generate_embeddings(policy_clauses)
        logger.info("Embedding generation complete: %d clauses", len(valid_clauses))

        logger.info("Building FAISS index")
        self.index = self.embedder.build_index(vectors)
        logger.info("FAISS index built")
        logger.info("Starting regulatory clause candidate retrieval")
        # ---------------------------------------------------------------
                 
        # 1. Retrieve candidates for all regulatory clauses
        reg_to_policies = {}
        retrieval_futures = {}
        for reg_clause in regulation_clauses:
            reg_id = reg_clause.get("clause_id") or reg_clause.get("id") or ""
            reg_text = reg_clause.get("text", "")
            if not reg_id or not reg_text:
                continue
            candidates = self._retrieve_candidates(reg_text, valid_clauses) # Use valid_clauses instead of policy_clauses
            report.candidate_pairs_found += len(candidates)
                         
            if candidates:
                reg_to_policies[reg_id] = {
                    "reg_text": reg_text,
                    "candidates": candidates
                }
        
        

        # 2. Concurrently process LLM batches
        futures = []
        for reg_id, data in reg_to_policies.items():
            report.llm_calls_made += 1
            futures.append(
                self.llm_executor.submit(self._process_batch, reg_id, data, session_id, report)
            )

        # Wait for completion and aggregate edges written
        for future in as_completed(futures):
            try:
                edges_written, unrelated_written = future.result()
                report.compliance_edges_written += edges_written
                report.unrelated_pairs_classified += unrelated_written
            except Exception as e:
                report.errors.append(f"Batch processing error: {e}")

        elapsed = time.perf_counter() - t0
        report.stages.append(StageTimer(
            "classify_and_write", elapsed, report.compliance_edges_written,
            f"{report.llm_calls_made} LLM calls for {report.candidate_pairs_found} pairs"
        ))

    def _process_batch(self, reg_id: str, data: Dict, session_id: str, report: IngestionReport) -> tuple[int, int]:
        """Handles LLM interaction and Neo4j edge generation for a single regulatory trigger."""
        reg_text_safe = data['reg_text'][:1500] + "..." if len(data['reg_text']) > 1500 else data['reg_text']
        policy_candidates = [
            {
                'policy_id': c.get('clause_id') or c.get('id'),
                'text': (c.get('text', '')[:700] + "...") if len(c.get('text', '')) > 1000 else c.get('text', '')
            }
            for c in data.get('candidates', [])
        ]

        response_schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "policy_id": {"type": "string", "enum": [str(c["policy_id"]) for c in policy_candidates]},
                    "relationship": {
                        "type": "string",
                        "enum": ["CONFLICTS_WITH", "COMPLIES_WITH", "SUPPORTS", "IS_REDUNDANT", "NONE"],
                    },
                    "reasoning": {"type": "string"},
                },
                "required": ["policy_id", "relationship", "reasoning"],
                "additionalProperties": False,
            },
            "minItems": len(policy_candidates),
            "maxItems": len(policy_candidates),
        }
        # line 347 replace if not working
        # Policies:
                #  {json.dumps([{'policy_id': c['clause_id'], 'text': c['text']} for c in data['candidates']], indent=2)}

        prompt = f"""
        Compare the regulatory clause with every policy clause. These clauses concern the same subject because they were retrieved as candidates. Classify their substantive relationship; do not label a pair NONE merely because the wording differs.

        Use CONFLICTS_WITH when requirements cannot both be satisfied, including different deadlines or limits. Use COMPLIES_WITH when the policy meets the regulatory requirement. Use SUPPORTS when the policy adds a compatible control that advances the requirement. Use IS_REDUNDANT when it repeats the same obligation without adding a distinct control. Use NONE only when the clauses have no meaningful compliance relationship.

        Regulation:
        {reg_text_safe}

        
        Policies:
        {json.dumps(policy_candidates, ensure_ascii=False)}
        
        Evaluate each policy against the regulation. Return a structured JSON array. 
        For each policy, provide:
        - "policy_id": The ID of the policy
        - "relationship": One of [CONFLICTS_WITH, COMPLIES_WITH, SUPPORTS, IS_REDUNDANT, NONE]
        - "reasoning": A 50-word context-grounded explanation for the classification.
        
        Output ONLY valid, raw JSON. Do not include markdown backticks (```), explanations, or conversational filler. Your entire response must be parsable by json.loads.
        """
        
        edges_written = 0
        unrelated_written = 0
        candidate_ids = {
            str(candidate.get("clause_id") or candidate.get("id") or "")
            for candidate in data.get("candidates", [])
        }
        candidate_ids.discard("")
        try:
            client = self.classifier.llm if hasattr(self.classifier, 'llm') else self.classifier
            
            # Constrain the response to one result per retrieved candidate.
            # Fall back to ordinary JSON mode for older Ollama versions that
            # do not accept JSON Schema as the format argument.
            try:
                response = client.predict(prompt, format=response_schema).strip()
            except Exception as schema_error:
                logger.warning(
                    "Structured output was rejected for reg %s; retrying in JSON mode: %s",
                    reg_id,
                    schema_error,
                )
                response = client.predict(prompt, format="json").strip()
            
            # Sanitize the LLM Output Before Parsing
            clean_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", response, flags=re.MULTILINE)
            match = re.search(r"(\{.*\}|\[.*\])", clean_text, re.DOTALL)
            if match:
                clean_text = match.group(1)
            
            classifications = json.loads(clean_text)
            
            # FIX: Ensure classifications is always a list
            if isinstance(classifications, dict):
                classifications = [classifications]
            elif not isinstance(classifications, list):
                classifications = []

            # Some model versions still omit items despite the schema. Keep
            # every retrieved candidate classified so it does not appear as
            # silently unclassified in the graph/dashboard.
            returned_ids = {
                str(item.get("policy_id", "")).strip()
                for item in classifications
                if isinstance(item, dict)
            }
            missing_ids = candidate_ids - returned_ids
            if missing_ids:
                logger.warning(
                    "Classifier omitted %d candidate(s) for reg %s; marking omitted results NOT_RELATED",
                    len(missing_ids),
                    reg_id,
                )
                classifications.extend(
                    {
                        "policy_id": policy_id,
                        "relationship": "NONE",
                        "reasoning": "The classifier returned no result for this retrieved candidate; it is recorded as unrelated pending review.",
                    }
                    for policy_id in sorted(missing_ids)
                )
            
            with driver.session() as session:
                for item in classifications:
                    # FIX: Guard against string outputs or malformed list items
                    if not isinstance(item, dict):
                        continue
                        
                    raw_label = str(item.get("relationship", "")).upper().strip()
                    rel_type = LABEL_TO_REL_TYPE.get(raw_label, REL_NOT_RELATED)
                    reasoning = item.get("reasoning", "")
                    pol_id = str(item.get("policy_id", "")).strip()
                    
                    if not rel_type or not pol_id or pol_id not in candidate_ids:
                        continue
                        
                    session.run(
                        f"""
                        MATCH (r:{NODE_REGULATORY} {{id: $rid, session_id: $sid}})
                        MATCH (p:{NODE_POLICY}     {{id: $pid, session_id: $sid}})
                        MERGE (r)-[e:{rel_type}]->(p)
                        SET   e.classified_at = $ts,
                              e.model         = $model,
                              e.reasoning     = $reasoning
                        """,
                        {
                            "rid": reg_id,
                            "sid": session_id,
                            "pid": pol_id,
                            "ts": int(time.time()),
                            "model": self.model,
                            "reasoning": reasoning
                        }
                    )
                    edges_written += 1
                    if rel_type == REL_NOT_RELATED:
                        unrelated_written += 1
                    
        except Exception as e:
            logger.error(f"Failed to process batch for reg {reg_id}: {e}")
            raise e
            
        return edges_written, unrelated_written

    def _retrieve_candidates(self, query_text: str, policy_clauses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            safe_query = query_text[:4000] if len(query_text) > 4000 else query_text
            query_vec = self.embedder.embed_query(safe_query)

            raw_results = self.embedder.secure_search(
                index=self.index,
                query_vector=query_vec,
                clauses=policy_clauses,
                k=self.top_k,
                distance_threshold=self.distance_threshold,
            )

            candidates = []
            for r in raw_results:
                clause_data = r.get("clause", r)
                cid = clause_data.get("clause_id") or clause_data.get("id")
                txt = clause_data.get("text")
                dist = r.get("distance", r.get("_distance", 0.0))

                # Aggressively filter low-confidence vector matches
                if cid and txt and dist <= self.distance_threshold:
                    candidates.append({
                        "clause_id": cid,
                        "text": txt,
                        "_distance": dist
                    })

            return candidates

        except Exception as e:
            logger.error(f"Candidate retrieval failed for query '{query_text[:60]}...': {e}")
            return []


# ---------------------------------------------------------------------------
# Query helpers — called by runtime components
# ---------------------------------------------------------------------------

def get_direct_impacts(
    reg_clause_id: str,
    session_id: str,
    rel_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    if rel_types is None:
        rel_types = ALL_COMPLIANCE_RELS

    rel_pattern = "|".join(rel_types)

    with driver.session() as session:
        result = session.run(
            f"""
            MATCH (r:{NODE_REGULATORY} {{id: $rid, session_id: $sid}})
                  -[e:{rel_pattern}]->
                  (p:{NODE_POLICY})
            RETURN p.id          AS clause_id,
                   p.text        AS text,
                   p.section     AS section,
                   type(e)       AS relationship,
                   e.classified_at AS classified_at,
                   e.reasoning     AS reasoning
            ORDER BY relationship, p.id
            """,
            {"rid": reg_clause_id, "sid": session_id}
        )
        return [record.data() for record in result]


def get_indirect_impacts(
    reg_clause_id: str,
    session_id: str,
    max_hops: int = 3,
) -> List[Dict[str, Any]]:
    with driver.session() as session:
        result = session.run(
            f"""
            MATCH (r:{NODE_REGULATORY} {{id: $rid, session_id: $sid}})
                  -[e:CONFLICTS_WITH|COMPLIES_WITH|SUPPORTS]->
                  (direct:{NODE_POLICY})
            WITH direct
            MATCH (direct)-[:{EDGE_DEPENDS_ON}*1..{max_hops}]->(indirect:{NODE_POLICY})
            WHERE indirect.id <> direct.id
            RETURN DISTINCT
                   indirect.id      AS clause_id,
                   indirect.text    AS text,
                   indirect.section AS section,
                   'INDIRECT'       AS relationship
            """,
            {"rid": reg_clause_id, "sid": session_id}
        )
        return [record.data() for record in result]
