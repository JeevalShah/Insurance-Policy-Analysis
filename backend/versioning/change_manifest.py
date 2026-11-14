"""
change_manifest.py

Defines the structured Change Manifest for version comparisons in the Sentra Engine.
Records clause-level additions, modifications, deletions, unchanged status, splits,
merges, and ambiguity flags along with cryptographic content fingerprints.
"""

from dataclasses import dataclass, field
from enum import Enum
import json
import time
from typing import List, Dict, Optional, Any


class ChangeType(str, Enum):
    UNCHANGED = "UNCHANGED"
    MODIFIED = "MODIFIED"
    ADDED = "ADDED"
    DELETED = "DELETED"
    SPLIT = "SPLIT"
    MERGED = "MERGED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class ClauseChangeRecord:
    """
    Detailed change description for a single clause transition.
    """
    stable_clause_id: str
    clause_id: str
    change_type: ChangeType
    old_clause_id: Optional[str] = None
    old_stable_id: Optional[str] = None
    old_fingerprint: Optional[str] = None
    new_fingerprint: Optional[str] = None
    similarity_score: float = 1.0
    match_type: str = ""
    notes: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stable_clause_id": self.stable_clause_id,
            "clause_id": self.clause_id,
            "change_type": self.change_type.value if isinstance(self.change_type, ChangeType) else str(self.change_type),
            "old_clause_id": self.old_clause_id,
            "old_stable_id": self.old_stable_id,
            "old_fingerprint": self.old_fingerprint,
            "new_fingerprint": self.new_fingerprint,
            "similarity_score": round(self.similarity_score, 4),
            "match_type": self.match_type,
            "notes": self.notes,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClauseChangeRecord":
        c_type_raw = data.get("change_type", "UNCHANGED")
        try:
            c_type = ChangeType(c_type_raw)
        except ValueError:
            c_type = ChangeType.UNCHANGED

        return cls(
            stable_clause_id=data["stable_clause_id"],
            clause_id=data["clause_id"],
            change_type=c_type,
            old_clause_id=data.get("old_clause_id"),
            old_stable_id=data.get("old_stable_id"),
            old_fingerprint=data.get("old_fingerprint"),
            new_fingerprint=data.get("new_fingerprint"),
            similarity_score=data.get("similarity_score", 1.0),
            match_type=data.get("match_type", ""),
            notes=data.get("notes", ""),
            details=data.get("details", {}),
        )


@dataclass
class SplitMergeRecord:
    """
    Records detected clause splitting or merging events.
    """
    event_type: str  # "split" or "merge"
    source_clause_ids: List[str]
    target_clause_ids: List[str]
    similarity_score: float
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "source_clause_ids": self.source_clause_ids,
            "target_clause_ids": self.target_clause_ids,
            "similarity_score": round(self.similarity_score, 4),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SplitMergeRecord":
        return cls(
            event_type=data["event_type"],
            source_clause_ids=data["source_clause_ids"],
            target_clause_ids=data["target_clause_ids"],
            similarity_score=data.get("similarity_score", 0.0),
            notes=data.get("notes", ""),
        )


@dataclass
class AmbiguousRecord:
    """
    Records an ambiguous clause match that requires human review.
    """
    clause_id: str
    stable_clause_id: str
    candidates: List[Dict[str, Any]]
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clause_id": self.clause_id,
            "stable_clause_id": self.stable_clause_id,
            "candidates": self.candidates,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AmbiguousRecord":
        return cls(
            clause_id=data["clause_id"],
            stable_clause_id=data["stable_clause_id"],
            candidates=data.get("candidates", []),
            notes=data.get("notes", ""),
        )


@dataclass
class ChangeManifest:
    """
    Structured manifest describing all differences between two document versions.
    Includes both clean human-readable arrays and detailed change tracking records.
    """
    document_id: str
    old_version: int
    new_version: int
    content_fingerprint_old: str = ""
    content_fingerprint_new: str = ""
    created_at: float = field(default_factory=time.time)

    # Clean clause ID lists for backward-compatible consumption
    added: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)

    # Detailed change records
    records: List[ClauseChangeRecord] = field(default_factory=list)
    splits: List[SplitMergeRecord] = field(default_factory=list)
    merges: List[SplitMergeRecord] = field(default_factory=list)
    ambiguous: List[AmbiguousRecord] = field(default_factory=list)

    # Operational review flags
    requires_human_review: bool = False

    @property
    def summary(self) -> Dict[str, int]:
        return {
            "added_count": len(self.added),
            "modified_count": len(self.modified),
            "deleted_count": len(self.deleted),
            "unchanged_count": len(self.unchanged),
            "split_count": len(self.splits),
            "merged_count": len(self.merges),
            "ambiguous_count": len(self.ambiguous),
            "total_changes": len(self.added) + len(self.modified) + len(self.deleted),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "content_fingerprint_old": self.content_fingerprint_old,
            "content_fingerprint_new": self.content_fingerprint_new,
            "created_at": self.created_at,
            "summary": self.summary,
            "requires_human_review": self.requires_human_review,
            "added": self.added,
            "modified": self.modified,
            "deleted": self.deleted,
            "unchanged": self.unchanged,
            "records": [r.to_dict() for r in self.records],
            "splits": [s.to_dict() for s in self.splits],
            "merges": [m.to_dict() for m in self.merges],
            "ambiguous": [a.to_dict() for a in self.ambiguous],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangeManifest":
        records = [ClauseChangeRecord.from_dict(r) for r in data.get("records", [])]
        splits = [SplitMergeRecord.from_dict(s) for s in data.get("splits", [])]
        merges = [SplitMergeRecord.from_dict(m) for m in data.get("merges", [])]
        ambiguous = [AmbiguousRecord.from_dict(a) for a in data.get("ambiguous", [])]

        return cls(
            document_id=data["document_id"],
            old_version=data["old_version"],
            new_version=data["new_version"],
            content_fingerprint_old=data.get("content_fingerprint_old", ""),
            content_fingerprint_new=data.get("content_fingerprint_new", ""),
            created_at=data.get("created_at", time.time()),
            added=data.get("added", []),
            modified=data.get("modified", []),
            deleted=data.get("deleted", []),
            unchanged=data.get("unchanged", []),
            records=records,
            splits=splits,
            merges=merges,
            ambiguous=ambiguous,
            requires_human_review=data.get("requires_human_review", False),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ChangeManifest":
        return cls.from_dict(json.loads(json_str))
