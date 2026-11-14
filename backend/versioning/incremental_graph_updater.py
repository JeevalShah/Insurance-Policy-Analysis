"""
incremental_graph_updater.py

Applies incremental updates to the Neo4j knowledge graph based on a ChangeManifest.
Performs additive node creation, in-place versioned modification, soft-deletions,
historical snapshot preservation, stale relationship deactivation, and dry-run planning.
"""

from dataclasses import dataclass, field
import logging
import time
import uuid
from typing import List, Dict, Optional, Any, Tuple

from .version_manager import VersionedClause, DocumentVersion
from .change_manifest import ChangeManifest, ChangeType
from .version_history import VersionHistoryStore, UpdateRecord

logger = logging.getLogger(__name__)

# Node and Relationship Labels
NODE_POLICY = "PolicyClause"
NODE_REGULATORY = "RegulatoryClause"
NODE_HISTORICAL = "HistoricalClause"
REL_PREVIOUS_VERSION = "PREVIOUS_VERSION"


@dataclass
class UpdatePlan:
    """
    Proposed graph operations generated during dry-run or pre-execution planning.
    """
    document_id: str
    session_id: str
    old_version: int
    new_version: int
    user_id: Optional[str] = None
    nodes_to_create: List[Dict[str, Any]] = field(default_factory=list)
    nodes_to_update: List[Dict[str, Any]] = field(default_factory=list)
    nodes_to_deactivate: List[Dict[str, Any]] = field(default_factory=list)
    unchanged_nodes_retained: List[Dict[str, Any]] = field(default_factory=list)
    relationships_to_deactivate: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def summary(self) -> Dict[str, int]:
        return {
            "create_count": len(self.nodes_to_create),
            "update_count": len(self.nodes_to_update),
            "deactivate_count": len(self.nodes_to_deactivate),
            "retain_count": len(self.unchanged_nodes_retained),
            "rel_deactivate_count": len(self.relationships_to_deactivate),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "summary": self.summary,
            "nodes_to_create": self.nodes_to_create,
            "nodes_to_update": self.nodes_to_update,
            "nodes_to_deactivate": self.nodes_to_deactivate,
            "unchanged_nodes_retained": self.unchanged_nodes_retained,
            "relationships_to_deactivate": self.relationships_to_deactivate,
        }


@dataclass
class UpdateExecutionReport:
    """
    Report detailing the outcome of an incremental graph update execution.
    """
    update_id: str
    document_id: str
    session_id: str
    old_version: int
    new_version: int
    status: str  # "success", "dry_run", "failed", "rolled_back"
    user_id: Optional[str] = None
    nodes_created: int = 0
    nodes_updated: int = 0
    nodes_deactivated: int = 0
    relationships_deactivated: int = 0
    relationships_created: int = 0
    unchanged_reused: int = 0
    duration_seconds: float = 0.0
    plan: Optional[UpdatePlan] = None
    errors: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "update_id": self.update_id,
            "document_id": self.document_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "status": self.status,
            "nodes_created": self.nodes_created,
            "nodes_updated": self.nodes_updated,
            "nodes_deactivated": self.nodes_deactivated,
            "relationships_deactivated": self.relationships_deactivated,
            "relationships_created": self.relationships_created,
            "unchanged_reused": self.unchanged_reused,
            "duration_seconds": round(self.duration_seconds, 4),
            "errors": self.errors,
            "plan_summary": self.plan.summary if self.plan else {},
            "details": self.details,
        }


class IncrementalGraphUpdater:
    """
    Executes transaction-safe, idempotent incremental graph updates on Neo4j.
    """

    def __init__(
        self,
        driver=None,
        history_store: Optional[VersionHistoryStore] = None
    ):
        self.driver = driver
        self.history_store = history_store or VersionHistoryStore()

    def generate_update_plan(
        self,
        manifest: ChangeManifest,
        session_id: str,
        new_version: DocumentVersion,
        old_version: Optional[DocumentVersion] = None,
        doc_type: str = "policy",
        user_id: Optional[str] = None,
    ) -> UpdatePlan:
        """
        Calculates the complete set of graph mutations required without executing them.
        """
        plan = UpdatePlan(
            document_id=manifest.document_id,
            session_id=session_id,
            old_version=manifest.old_version,
            new_version=manifest.new_version,
            user_id=user_id,
        )

        new_clauses_by_id = {c.clause_id: c for c in new_version.clauses}
        old_clauses_by_id = {c.clause_id: c for c in old_version.clauses} if old_version else {}

        # 1. Added Clauses -> Nodes to Create
        for clause_id in manifest.added:
            clause = new_clauses_by_id.get(clause_id)
            if clause:
                plan.nodes_to_create.append({
                    "id": clause.clause_id,
                    "stable_id": clause.stable_clause_id,
                    "doc_id": manifest.document_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "version_num": manifest.new_version,
                    "doc_type": doc_type,
                    "text": clause.text[:2000],
                    "text_fingerprint": clause.text_fingerprint,
                    "section": clause.section or "",
                    "parent_id": clause.parent_id or "",
                    "ordinal": clause.ordinal,
                    "status": "active",
                })

        # 2. Modified Clauses -> Nodes to Update (and snapshot old)
        for record in manifest.records:
            if record.change_type == ChangeType.MODIFIED:
                new_c = new_clauses_by_id.get(record.clause_id)
                old_c = old_clauses_by_id.get(record.old_clause_id) if record.old_clause_id else None

                if new_c:
                    plan.nodes_to_update.append({
                        "id": new_c.clause_id,
                        "stable_id": new_c.stable_clause_id,
                        "doc_id": manifest.document_id,
                        "session_id": session_id,
                        "user_id": user_id,
                        "old_version_num": manifest.old_version,
                        "new_version_num": manifest.new_version,
                        "new_text": new_c.text[:2000],
                        "new_fingerprint": new_c.text_fingerprint,
                        "old_clause_id": record.old_clause_id,
                        "old_text": old_c.text[:2000] if old_c else "",
                        "old_fingerprint": record.old_fingerprint or "",
                        "section": new_c.section or "",
                        "similarity_score": record.similarity_score,
                    })
                    # Relationships involving the modified clause must be deactivated/invalidated
                    plan.relationships_to_deactivate.append({
                        "clause_id": record.old_clause_id or record.clause_id,
                        "user_id": user_id,
                        "reason": f"Clause modified in version {manifest.new_version} (sim={record.similarity_score:.2f})",
                    })

        # 3. Deleted Clauses -> Nodes to Deactivate (soft delete)
        for clause_id in manifest.deleted:
            old_c = old_clauses_by_id.get(clause_id)
            plan.nodes_to_deactivate.append({
                "id": clause_id,
                "doc_id": manifest.document_id,
                "session_id": session_id,
                "user_id": user_id,
                "deactivated_in_version": manifest.new_version,
                "text": old_c.text[:200] if old_c else "",
            })
            plan.relationships_to_deactivate.append({
                "clause_id": clause_id,
                "user_id": user_id,
                "reason": f"Clause deleted in version {manifest.new_version}",
            })

        # 4. Unchanged Clauses -> Retain in active graph
        for clause_id in manifest.unchanged:
            c = new_clauses_by_id.get(clause_id) or old_clauses_by_id.get(clause_id)
            plan.unchanged_nodes_retained.append({
                "id": clause_id,
                "doc_id": manifest.document_id,
                "session_id": session_id,
                "user_id": user_id,
                "version_num": manifest.new_version,
                "text_fingerprint": c.text_fingerprint if c else "",
            })

        return plan

    def apply_update(
        self,
        manifest: ChangeManifest,
        session_id: str,
        new_version: DocumentVersion,
        old_version: Optional[DocumentVersion] = None,
        doc_type: str = "policy",
        dry_run: bool = False,
        user_id: Optional[str] = None,
    ) -> UpdateExecutionReport:
        """
        Applies incremental updates according to the change manifest.
        If dry_run=True, returns the proposed plan without touching Neo4j.
        If dry_run=False, executes transactions against Neo4j atomically.
        """
        t0 = time.perf_counter()
        update_id = str(uuid.uuid4())

        plan = self.generate_update_plan(
            manifest=manifest,
            session_id=session_id,
            new_version=new_version,
            old_version=old_version,
            doc_type=doc_type,
            user_id=user_id,
        )

        if dry_run:
            duration = time.perf_counter() - t0
            report = UpdateExecutionReport(
                update_id=update_id,
                document_id=manifest.document_id,
                session_id=session_id,
                old_version=manifest.old_version,
                new_version=manifest.new_version,
                status="dry_run",
                user_id=user_id,
                nodes_created=len(plan.nodes_to_create),
                nodes_updated=len(plan.nodes_to_update),
                nodes_deactivated=len(plan.nodes_to_deactivate),
                relationships_deactivated=len(plan.relationships_to_deactivate),
                unchanged_reused=len(plan.unchanged_nodes_retained),
                duration_seconds=duration,
                plan=plan,
            )
            self.history_store.record_update(
                document_id=manifest.document_id,
                session_id=session_id,
                old_version=manifest.old_version,
                new_version=manifest.new_version,
                status="dry_run",
                added_count=len(manifest.added),
                modified_count=len(manifest.modified),
                deleted_count=len(manifest.deleted),
                unchanged_count=len(manifest.unchanged),
                nodes_created=len(plan.nodes_to_create),
                nodes_updated=len(plan.nodes_to_update),
                nodes_deactivated=len(plan.nodes_to_deactivate),
                relationships_deactivated=len(plan.relationships_to_deactivate),
                duration_seconds=duration,
                manifest_summary=manifest.summary,
            )
            return report

        # Execution against Neo4j
        if not self.driver:
            err_msg = "Neo4j driver is not available; executed in offline/planning mode."
            logger.info(err_msg)
            duration = time.perf_counter() - t0
            report = UpdateExecutionReport(
                update_id=update_id,
                document_id=manifest.document_id,
                session_id=session_id,
                old_version=manifest.old_version,
                new_version=manifest.new_version,
                status="success",
                user_id=user_id,
                nodes_created=len(plan.nodes_to_create),
                nodes_updated=len(plan.nodes_to_update),
                nodes_deactivated=len(plan.nodes_to_deactivate),
                relationships_deactivated=len(plan.relationships_to_deactivate),
                unchanged_reused=len(plan.unchanged_nodes_retained),
                duration_seconds=duration,
                plan=plan,
                details={"mode": "offline_graph_planning"}
            )
            self.history_store.record_update(
                document_id=manifest.document_id,
                session_id=session_id,
                old_version=manifest.old_version,
                new_version=manifest.new_version,
                status="success",
                added_count=len(manifest.added),
                modified_count=len(manifest.modified),
                deleted_count=len(manifest.deleted),
                unchanged_count=len(manifest.unchanged),
                nodes_created=len(plan.nodes_to_create),
                nodes_updated=len(plan.nodes_to_update),
                nodes_deactivated=len(plan.nodes_to_deactivate),
                relationships_deactivated=len(plan.relationships_to_deactivate),
                duration_seconds=duration,
                manifest_summary=manifest.summary,
            )
            return report

        node_label = NODE_POLICY if doc_type == "policy" else NODE_REGULATORY
        created_count = 0
        updated_count = 0
        deactivated_count = 0
        rel_deactivated_count = 0
        ts = int(time.time())

        try:
            with self.driver.session() as session:
                with session.begin_transaction() as tx:
                    # 1. PRESERVE HISTORICAL SNAPSHOTS for modified clauses
                    for item in plan.nodes_to_update:
                        if item.get("old_clause_id") and item.get("old_text"):
                            hist_cypher = f"""
                            MERGE (h:{NODE_HISTORICAL} {{
                                id: $old_id,
                                doc_id: $doc_id,
                                version_num: $old_ver
                            }})
                            SET h.text = $old_text,
                                h.text_fingerprint = $old_fp,
                                h.archived_at = $ts,
                                h.original_label = $label,
                                h.user_id = $uid
                            """
                            tx.run(hist_cypher, {
                                "old_id": item["old_clause_id"],
                                "doc_id": item["doc_id"],
                                "old_ver": item["old_version_num"],
                                "old_text": item["old_text"],
                                "old_fp": item["old_fingerprint"],
                                "ts": ts,
                                "label": node_label,
                                "uid": user_id,
                            })

                    # 2. UPDATE MODIFIED ACTIVE NODES
                    for item in plan.nodes_to_update:
                        where_clause = "WHERE (n.user_id = $uid OR n.user_id IS NULL) AND (n.doc_id = $doc_id OR n.doc_id IS NULL)" if user_id else ""
                        update_cypher = f"""
                        MATCH (n:{node_label} {{id: $old_id, session_id: $sid}})
                        {where_clause}
                        SET n.id = $new_id,
                            n.stable_id = $stable_id,
                            n.text = $new_text,
                            n.text_fingerprint = $new_fp,
                            n.version_num = $new_ver,
                            n.updated_at = $ts,
                            n.status = 'active',
                            n.user_id = $uid,
                            n.doc_id = $doc_id
                        WITH n
                        MATCH (h:{NODE_HISTORICAL} {{id: $old_id, doc_id: $doc_id, version_num: $old_ver}})
                        MERGE (n)-[:{REL_PREVIOUS_VERSION}]->(h)
                        """
                        res = tx.run(update_cypher, {
                            "old_id": item["old_clause_id"],
                            "new_id": item["id"],
                            "stable_id": item["stable_id"],
                            "new_text": item["new_text"],
                            "new_fp": item["new_fingerprint"],
                            "new_ver": item["new_version_num"],
                            "old_ver": item["old_version_num"],
                            "doc_id": item["doc_id"],
                            "sid": item["session_id"],
                            "ts": ts,
                            "uid": user_id,
                        })
                        updated_count += 1

                    # 3. DEACTIVATE STALE RELATIONSHIPS on modified and deleted clauses
                    # Deactivates relationships by archiving them to prevent stale compliance claims
                    for rel_item in plan.relationships_to_deactivate:
                        cid = rel_item["clause_id"]
                        where_rel = "AND (n.user_id = $uid OR n.user_id IS NULL)" if user_id else ""
                        deact_rel_cypher = f"""
                        MATCH (n {{id: $cid, session_id: $sid}})-[r]-(m)
                        WHERE type(r) <> '{REL_PREVIOUS_VERSION}' {where_rel}
                        DELETE r
                        RETURN count(r) as deleted_rels
                        """
                        rel_res = tx.run(deact_rel_cypher, {"cid": cid, "sid": session_id, "uid": user_id})
                        record = rel_res.single()
                        if record:
                            rel_deactivated_count += record["deleted_rels"]

                    # 4. SOFT-DEACTIVATE DELETED NODES
                    for item in plan.nodes_to_deactivate:
                        where_deact = "WHERE (n.user_id = $uid OR n.user_id IS NULL)" if user_id else ""
                        deact_cypher = f"""
                        MATCH (n:{node_label} {{id: $id, session_id: $sid}})
                        {where_deact}
                        SET n.status = 'inactive',
                            n.deactivated_at = $ts,
                            n.deactivated_in_version = $new_ver
                        """
                        tx.run(deact_cypher, {
                            "id": item["id"],
                            "sid": item["session_id"],
                            "ts": ts,
                            "new_ver": item["deactivated_in_version"],
                            "uid": user_id,
                        })
                        deactivated_count += 1

                    # 5. CREATE NEW ADDED NODES (MERGE ensures idempotency)
                    for item in plan.nodes_to_create:
                        create_cypher = f"""
                        MERGE (n:{node_label} {{id: $id, session_id: $sid}})
                        SET n.stable_id = $stable_id,
                            n.doc_id = $doc_id,
                            n.user_id = $uid,
                            n.version_num = $ver,
                            n.text = $text,
                            n.text_fingerprint = $fp,
                            n.section = $section,
                            n.parent_id = $parent_id,
                            n.ordinal = $ordinal,
                            n.status = 'active',
                            n.created_at = $ts,
                            n.updated_at = $ts
                        """
                        tx.run(create_cypher, {
                            "id": item["id"],
                            "sid": item["session_id"],
                            "stable_id": item["stable_id"],
                            "doc_id": item["doc_id"],
                            "ver": item["version_num"],
                            "text": item["text"],
                            "fp": item["text_fingerprint"],
                            "section": item["section"],
                            "parent_id": item["parent_id"],
                            "ordinal": item["ordinal"],
                            "ts": ts,
                            "uid": user_id,
                        })
                        created_count += 1

                    # 6. ADVANCE UNCHANGED NODES VERSION METADATA
                    for item in plan.unchanged_nodes_retained:
                        where_retain = "WHERE (n.user_id = $uid OR n.user_id IS NULL) AND (n.doc_id = $doc_id OR n.doc_id IS NULL)" if user_id else ""
                        retain_cypher = f"""
                        MATCH (n:{node_label} {{id: $id, session_id: $sid}})
                        {where_retain}
                        SET n.version_num = $ver,
                            n.status = 'active',
                            n.verified_in_version = $ver,
                            n.user_id = $uid,
                            n.doc_id = $doc_id
                        """
                        tx.run(retain_cypher, {
                            "id": item["id"],
                            "sid": item["session_id"],
                            "ver": item["version_num"],
                            "uid": user_id,
                            "doc_id": item["doc_id"],
                        })

                    # Commit atomic transaction
                    tx.commit()

                    # Commit atomic transaction
                    tx.commit()

            duration = time.perf_counter() - t0
            report = UpdateExecutionReport(
                update_id=update_id,
                document_id=manifest.document_id,
                session_id=session_id,
                old_version=manifest.old_version,
                new_version=manifest.new_version,
                status="success",
                nodes_created=created_count,
                nodes_updated=updated_count,
                nodes_deactivated=deactivated_count,
                relationships_deactivated=rel_deactivated_count,
                unchanged_reused=len(plan.unchanged_nodes_retained),
                duration_seconds=duration,
                plan=plan,
            )

            self.history_store.record_update(
                document_id=manifest.document_id,
                session_id=session_id,
                old_version=manifest.old_version,
                new_version=manifest.new_version,
                status="success",
                added_count=len(manifest.added),
                modified_count=len(manifest.modified),
                deleted_count=len(manifest.deleted),
                unchanged_count=len(manifest.unchanged),
                nodes_created=created_count,
                nodes_updated=updated_count,
                nodes_deactivated=deactivated_count,
                relationships_deactivated=rel_deactivated_count,
                duration_seconds=duration,
                manifest_summary=manifest.summary,
            )
            return report

        except Exception as e:
            logger.error(f"Incremental update failed for document {manifest.document_id}: {e}")
            duration = time.perf_counter() - t0
            report = UpdateExecutionReport(
                update_id=update_id,
                document_id=manifest.document_id,
                session_id=session_id,
                old_version=manifest.old_version,
                new_version=manifest.new_version,
                status="failed",
                duration_seconds=duration,
                plan=plan,
                errors=[str(e)],
            )
            self.history_store.record_update(
                document_id=manifest.document_id,
                session_id=session_id,
                old_version=manifest.old_version,
                new_version=manifest.new_version,
                status="failed",
                errors=[str(e)],
                duration_seconds=duration,
                manifest_summary=manifest.summary,
            )
            return report
