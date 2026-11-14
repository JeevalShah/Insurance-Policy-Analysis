"""
rollback_manager.py

Provides safe, targeted version rollback for the Sentra Engine.
Restores an earlier document version's graph state and clause definitions without
blindly deleting session data or corrupting unrelated documents.
"""

from dataclasses import dataclass, field
import logging
import time
import uuid
from typing import List, Dict, Optional, Any

from .version_manager import VersionManager, DocumentVersion, VersionStatus
from .change_manifest import ChangeManifest, ChangeType
from .change_detector import ChangeDetector
from .version_history import VersionHistoryStore, UpdateRecord

logger = logging.getLogger(__name__)


@dataclass
class RollbackReport:
    """
    Summary of operations performed during a version rollback.
    """
    rollback_id: str
    document_id: str
    session_id: str
    from_version: int
    target_version: int
    status: str  # "success", "failed", "dry_run"
    clauses_restored: int = 0
    clauses_deactivated: int = 0
    clauses_reactivated: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rollback_id": self.rollback_id,
            "document_id": self.document_id,
            "session_id": self.session_id,
            "from_version": self.from_version,
            "target_version": self.target_version,
            "status": self.status,
            "clauses_restored": self.clauses_restored,
            "clauses_deactivated": self.clauses_deactivated,
            "clauses_reactivated": self.clauses_reactivated,
            "duration_seconds": round(self.duration_seconds, 4),
            "errors": self.errors,
            "details": self.details,
        }


class RollbackManager:
    """
    Manages safe restoration of earlier document versions.
    """

    def __init__(
        self,
        version_manager: Optional[VersionManager] = None,
        history_store: Optional[VersionHistoryStore] = None,
        driver=None,
    ):
        self.version_manager = version_manager or VersionManager()
        self.history_store = history_store or VersionHistoryStore()
        self.driver = driver
        self.detector = ChangeDetector()

    def execute_rollback(
        self,
        document_id: str,
        target_version_num: int,
        session_id: str = "default_session",
        dry_run: bool = False,
    ) -> RollbackReport:
        """
        Rolls back the document state to target_version_num.
        Restores modified clause contents, reactivates clauses deleted in later versions,
        and deactivates clauses introduced after the target version.
        """
        t0 = time.perf_counter()
        rollback_id = str(uuid.uuid4())

        current_ver = self.version_manager.get_active_version(document_id)
        target_ver = self.version_manager.get_version(document_id, target_version_num)

        if not current_ver or not target_ver:
            return RollbackReport(
                rollback_id=rollback_id,
                document_id=document_id,
                session_id=session_id,
                from_version=current_ver.version_num if current_ver else 0,
                target_version=target_version_num,
                status="failed",
                errors=[f"Target version {target_version_num} or current version for doc '{document_id}' not found."],
                duration_seconds=time.perf_counter() - t0,
            )

        if current_ver.version_num == target_version_num:
            return RollbackReport(
                rollback_id=rollback_id,
                document_id=document_id,
                session_id=session_id,
                from_version=current_ver.version_num,
                target_version=target_version_num,
                status="success",
                details={"message": "Document is already at target version."},
                duration_seconds=time.perf_counter() - t0,
            )

        # Detect diff between current version and target version
        detection = self.detector.detect_changes(current_ver, target_ver)
        manifest = detection.manifest

        target_clauses_by_id = {c.clause_id: c for c in target_ver.clauses}
        current_clauses_by_id = {c.clause_id: c for c in current_ver.clauses}

        # 1. Clauses added after target_ver -> need deactivation
        clauses_to_deactivate = [cid for cid in current_clauses_by_id if cid not in target_clauses_by_id]
        # 2. Clauses deleted after target_ver -> need reactivation
        clauses_to_reactivate = [cid for cid in target_clauses_by_id if cid not in current_clauses_by_id]
        # 3. Clauses modified after target_ver -> need restoration to target text
        clauses_to_restore = []
        for cid in target_clauses_by_id:
            if cid in current_clauses_by_id:
                if current_clauses_by_id[cid].text_fingerprint != target_clauses_by_id[cid].text_fingerprint:
                    clauses_to_restore.append(target_clauses_by_id[cid])

        if dry_run:
            return RollbackReport(
                rollback_id=rollback_id,
                document_id=document_id,
                session_id=session_id,
                from_version=current_ver.version_num,
                target_version=target_version_num,
                status="dry_run",
                clauses_restored=len(clauses_to_restore),
                clauses_deactivated=len(clauses_to_deactivate),
                clauses_reactivated=len(clauses_to_reactivate),
                duration_seconds=time.perf_counter() - t0,
                details={
                    "to_deactivate": clauses_to_deactivate,
                    "to_reactivate": clauses_to_reactivate,
                    "to_restore": [c.clause_id for c in clauses_to_restore],
                }
            )

        ts = int(time.time())

        # If live Neo4j driver is present, execute restoration queries
        if self.driver:
            try:
                with self.driver.session() as session:
                    with session.begin_transaction() as tx:
                        # Deactivate clauses that did not exist in target version
                        if clauses_to_deactivate:
                            tx.run("""
                            MATCH (n {session_id: $sid})
                            WHERE n.id IN $ids AND n.doc_id = $doc_id
                            SET n.status = 'inactive',
                                n.rolled_back_at = $ts
                            """, {"sid": session_id, "ids": clauses_to_deactivate, "doc_id": document_id, "ts": ts})

                        # Restore modified clauses
                        for c in clauses_to_restore:
                            tx.run("""
                            MATCH (n {session_id: $sid, id: $cid, doc_id: $doc_id})
                            SET n.text = $text,
                                n.text_fingerprint = $fp,
                                n.version_num = $target_ver,
                                n.status = 'active',
                                n.restored_at = $ts
                            """, {
                                "sid": session_id,
                                "cid": c.clause_id,
                                "doc_id": document_id,
                                "text": c.text,
                                "fp": c.text_fingerprint,
                                "target_ver": target_version_num,
                                "ts": ts
                            })

                        # Reactivate clauses deleted in later versions
                        for cid in clauses_to_reactivate:
                            c = target_clauses_by_id[cid]
                            tx.run("""
                            MERGE (n:PolicyClause {id: $cid, session_id: $sid})
                            SET n.doc_id = $doc_id,
                                n.version_num = $target_ver,
                                n.text = $text,
                                n.text_fingerprint = $fp,
                                n.status = 'active',
                                n.reactivated_at = $ts
                            """, {
                                "sid": session_id,
                                "cid": cid,
                                "doc_id": document_id,
                                "target_ver": target_version_num,
                                "text": c.text,
                                "fp": c.text_fingerprint,
                                "ts": ts
                            })

                        tx.commit()
            except Exception as e:
                logger.error(f"Rollback transaction failed: {e}")
                return RollbackReport(
                    rollback_id=rollback_id,
                    document_id=document_id,
                    session_id=session_id,
                    from_version=current_ver.version_num,
                    target_version=target_version_num,
                    status="failed",
                    errors=[str(e)],
                    duration_seconds=time.perf_counter() - t0,
                )

        # Update version status in VersionManager
        current_ver.status = VersionStatus.ARCHIVED
        target_ver.status = VersionStatus.ACTIVE
        self.version_manager._persist_version(current_ver)
        self.version_manager._persist_version(target_ver)

        # Record audit log
        duration = time.perf_counter() - t0
        self.history_store.record_update(
            document_id=document_id,
            session_id=session_id,
            old_version=current_ver.version_num,
            new_version=target_version_num,
            status="rollback_success",
            details={
                "rollback_id": rollback_id,
                "clauses_restored": len(clauses_to_restore),
                "clauses_deactivated": len(clauses_to_deactivate),
                "clauses_reactivated": len(clauses_to_reactivate),
            },
            duration_seconds=duration,
        )

        return RollbackReport(
            rollback_id=rollback_id,
            document_id=document_id,
            session_id=session_id,
            from_version=current_ver.version_num,
            target_version=target_version_num,
            status="success",
            clauses_restored=len(clauses_to_restore),
            clauses_deactivated=len(clauses_to_deactivate),
            clauses_reactivated=len(clauses_to_reactivate),
            duration_seconds=duration,
        )
