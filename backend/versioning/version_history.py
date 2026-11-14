"""
version_history.py

Maintains an immutable audit log of document updates, version transitions,
and graph maintenance operations for the Sentra Engine.
"""

from dataclasses import dataclass, field
import json
import logging
import os
import re
import time
import uuid
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class UpdateRecord:
    """
    Detailed audit record of an incremental update or dry-run operation.
    """
    update_id: str
    document_id: str
    session_id: str
    old_version: int
    new_version: int
    timestamp: float = field(default_factory=time.time)
    status: str = "success"  # "success", "dry_run", "failed", "rolled_back"
    added_count: int = 0
    modified_count: int = 0
    deleted_count: int = 0
    unchanged_count: int = 0
    nodes_created: int = 0
    nodes_updated: int = 0
    nodes_deactivated: int = 0
    relationships_deactivated: int = 0
    relationships_created: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    manifest_id: Optional[str] = None
    manifest_summary: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "update_id": self.update_id,
            "document_id": self.document_id,
            "session_id": self.session_id,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "timestamp": self.timestamp,
            "status": self.status,
            "added_count": self.added_count,
            "modified_count": self.modified_count,
            "deleted_count": self.deleted_count,
            "unchanged_count": self.unchanged_count,
            "nodes_created": self.nodes_created,
            "nodes_updated": self.nodes_updated,
            "nodes_deactivated": self.nodes_deactivated,
            "relationships_deactivated": self.relationships_deactivated,
            "relationships_created": self.relationships_created,
            "duration_seconds": round(self.duration_seconds, 4),
            "errors": self.errors,
            "manifest_id": self.manifest_id,
            "manifest_summary": self.manifest_summary,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UpdateRecord":
        return cls(
            update_id=data["update_id"],
            document_id=data["document_id"],
            session_id=data["session_id"],
            old_version=data["old_version"],
            new_version=data["new_version"],
            timestamp=data.get("timestamp", time.time()),
            status=data.get("status", "success"),
            added_count=data.get("added_count", 0),
            modified_count=data.get("modified_count", 0),
            deleted_count=data.get("deleted_count", 0),
            unchanged_count=data.get("unchanged_count", 0),
            nodes_created=data.get("nodes_created", 0),
            nodes_updated=data.get("nodes_updated", 0),
            nodes_deactivated=data.get("nodes_deactivated", 0),
            relationships_deactivated=data.get("relationships_deactivated", 0),
            relationships_created=data.get("relationships_created", 0),
            duration_seconds=data.get("duration_seconds", 0.0),
            errors=data.get("errors", []),
            manifest_id=data.get("manifest_id"),
            manifest_summary=data.get("manifest_summary", {}),
            details=data.get("details", {}),
        )


class VersionHistoryStore:
    """
    Stores and retrieves audit records for document updates and version history.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir
        # In-memory map: doc_id -> List[UpdateRecord]
        self._history: Dict[str, List[UpdateRecord]] = {}

        if self.storage_dir:
            os.makedirs(self.storage_dir, exist_ok=True)
            self._load_from_storage()

    def _get_doc_file(self, doc_id: str) -> str:
        safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', doc_id)
        return os.path.join(self.storage_dir, f"{safe_id}_history.json")

    def _load_from_storage(self) -> None:
        if not self.storage_dir or not os.path.exists(self.storage_dir):
            return

        for filename in os.listdir(self.storage_dir):
            if filename.endswith("_history.json"):
                filepath = os.path.join(self.storage_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        doc_id = data.get("document_id")
                        records = [UpdateRecord.from_dict(r) for r in data.get("records", [])]
                        if doc_id:
                            self._history[doc_id] = records
                except Exception as e:
                    logger.warning(f"Failed to load history from {filepath}: {e}")

    def _persist_doc_history(self, doc_id: str) -> None:
        if not self.storage_dir:
            return
        records = self._history.get(doc_id, [])
        filepath = self._get_doc_file(doc_id)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "document_id": doc_id,
                "record_count": len(records),
                "records": [r.to_dict() for r in records],
            }, f, indent=2, ensure_ascii=False)

    def record_update(
        self,
        document_id: str,
        session_id: str,
        old_version: int,
        new_version: int,
        status: str = "success",
        added_count: int = 0,
        modified_count: int = 0,
        deleted_count: int = 0,
        unchanged_count: int = 0,
        nodes_created: int = 0,
        nodes_updated: int = 0,
        nodes_deactivated: int = 0,
        relationships_deactivated: int = 0,
        relationships_created: int = 0,
        duration_seconds: float = 0.0,
        errors: Optional[List[str]] = None,
        manifest_id: Optional[str] = None,
        manifest_summary: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> UpdateRecord:
        """
        Appends a new audit record to the history for a document.
        """
        record = UpdateRecord(
            update_id=str(uuid.uuid4()),
            document_id=document_id,
            session_id=session_id,
            old_version=old_version,
            new_version=new_version,
            timestamp=time.time(),
            status=status,
            added_count=added_count,
            modified_count=modified_count,
            deleted_count=deleted_count,
            unchanged_count=unchanged_count,
            nodes_created=nodes_created,
            nodes_updated=nodes_updated,
            nodes_deactivated=nodes_deactivated,
            relationships_deactivated=relationships_deactivated,
            relationships_created=relationships_created,
            duration_seconds=duration_seconds,
            errors=errors or [],
            manifest_id=manifest_id,
            manifest_summary=manifest_summary or {},
            details=details or {},
        )

        self._history.setdefault(document_id, []).append(record)
        self._persist_doc_history(document_id)
        return record

    def get_history(self, document_id: str) -> List[UpdateRecord]:
        return list(self._history.get(document_id, []))

    def get_latest_update(self, document_id: str) -> Optional[UpdateRecord]:
        records = self._history.get(document_id, [])
        return records[-1] if records else None

    def list_all_documented_ids(self) -> List[str]:
        return sorted(list(self._history.keys()))
