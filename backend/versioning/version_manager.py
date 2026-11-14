"""
version_manager.py

Document version management and clause fingerprinting for the Sentra Engine.
Maintains historical document versions, clause content hashes, and stable clause identifiers.
"""

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import logging
import os
import re
import time
from typing import List, Dict, Optional, Any

from .document_identity import DocumentType

logger = logging.getLogger(__name__)


class VersionStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    STAGED = "staged"


def normalize_clause_text(text: str) -> str:
    """
    Normalizes clause text for deterministic fingerprinting and unchanged detection.
    Collapses whitespace, normalizes smart quotes and dashes, and lowercases.
    """
    if not text:
        return ""
    # Normalize unicode quotes and dashes
    t = text.strip()
    t = t.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    t = t.replace('—', '-').replace('–', '-')
    # Collapse multiple whitespace characters into single space
    t = re.sub(r'\s+', ' ', t)
    return t.lower()


def compute_clause_fingerprint(text: str) -> str:
    """
    Computes a cryptographic SHA-256 hash of normalized clause text.
    Identical clause content will always yield the exact same fingerprint.
    """
    norm = normalize_clause_text(text)
    return hashlib.sha256(norm.encode('utf-8')).hexdigest()


def compute_document_fingerprint(clauses: List["VersionedClause"]) -> str:
    """
    Computes a document-level fingerprint by hashing the ordered sequence of clause fingerprints.
    """
    concatenated = ":".join(c.text_fingerprint for c in clauses)
    return hashlib.sha256(concatenated.encode('utf-8')).hexdigest()


@dataclass
class VersionedClause:
    """
    Represents a specific clause within a document version.
    Carries both its raw extracted identifier and an unambiguous stable ID.
    """
    stable_clause_id: str
    clause_id: str
    doc_id: str
    version_num: int
    text: str
    text_fingerprint: str
    section: Optional[str] = None
    parent_id: Optional[str] = None
    ordinal: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stable_clause_id": self.stable_clause_id,
            "clause_id": self.clause_id,
            "doc_id": self.doc_id,
            "version_num": self.version_num,
            "text": self.text,
            "text_fingerprint": self.text_fingerprint,
            "section": self.section,
            "parent_id": self.parent_id,
            "ordinal": self.ordinal,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VersionedClause":
        return cls(
            stable_clause_id=data["stable_clause_id"],
            clause_id=data["clause_id"],
            doc_id=data["doc_id"],
            version_num=data["version_num"],
            text=data["text"],
            text_fingerprint=data.get("text_fingerprint") or compute_clause_fingerprint(data["text"]),
            section=data.get("section"),
            parent_id=data.get("parent_id"),
            ordinal=data.get("ordinal", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DocumentVersion:
    """
    Represents an immutable snapshot of a document at a specific version.
    """
    doc_id: str
    version_num: int
    content_fingerprint: str
    upload_timestamp: float = field(default_factory=time.time)
    previous_version_num: Optional[int] = None
    version_tag: Optional[str] = None
    doc_type: str = "unknown"
    status: VersionStatus = VersionStatus.ACTIVE
    clauses: List[VersionedClause] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def clause_count(self) -> int:
        return len(self.clauses)

    def get_clause_by_id(self, clause_id: str) -> Optional[VersionedClause]:
        for c in self.clauses:
            if c.clause_id == clause_id:
                return c
        return None

    def get_clause_by_stable_id(self, stable_id: str) -> Optional[VersionedClause]:
        for c in self.clauses:
            if c.stable_clause_id == stable_id:
                return c
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "version_num": self.version_num,
            "content_fingerprint": self.content_fingerprint,
            "upload_timestamp": self.upload_timestamp,
            "previous_version_num": self.previous_version_num,
            "version_tag": self.version_tag,
            "doc_type": self.doc_type,
            "status": self.status.value if isinstance(self.status, VersionStatus) else str(self.status),
            "clause_count": self.clause_count,
            "clauses": [c.to_dict() for c in self.clauses],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentVersion":
        clauses = [VersionedClause.from_dict(c) for c in data.get("clauses", [])]
        status_raw = data.get("status", "active")
        try:
            status = VersionStatus(status_raw)
        except ValueError:
            status = VersionStatus.ACTIVE

        return cls(
            doc_id=data["doc_id"],
            version_num=data["version_num"],
            content_fingerprint=data["content_fingerprint"],
            upload_timestamp=data.get("upload_timestamp", time.time()),
            previous_version_num=data.get("previous_version_num"),
            version_tag=data.get("version_tag"),
            doc_type=data.get("doc_type", "unknown"),
            status=status,
            clauses=clauses,
            metadata=data.get("metadata", {}),
        )


def build_stable_clause_id(
    doc_id: str,
    raw_clause_id: str,
    section: Optional[str] = None,
    parent_id: Optional[str] = None,
    ordinal: int = 0
) -> str:
    """
    Builds a globally unambiguous stable clause ID.
    Example: DOC_A::sec_1::parent_none::1.1#0
    """
    clean_doc = re.sub(r'[^a-zA-Z0-9_\-]', '_', doc_id)
    clean_sec = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(section)) if section else "root"
    clean_parent = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(parent_id)) if parent_id else "none"
    clean_raw = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', str(raw_clause_id))
    return f"{clean_doc}::{clean_sec}::{clean_parent}::{clean_raw}#{ordinal}"


class VersionManager:
    """
    Manages document version registration, lookup, persistence, and state transitions.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir
        # In-memory storage: doc_id -> {version_num: DocumentVersion}
        self._versions: Dict[str, Dict[int, DocumentVersion]] = {}

        if self.storage_dir:
            os.makedirs(self.storage_dir, exist_ok=True)
            self._load_from_storage()

    def _get_doc_dir(self, doc_id: str) -> str:
        safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', doc_id)
        return os.path.join(self.storage_dir, safe_id)

    def _load_from_storage(self) -> None:
        if not self.storage_dir or not os.path.exists(self.storage_dir):
            return

        for doc_dir_name in os.listdir(self.storage_dir):
            doc_path = os.path.join(self.storage_dir, doc_dir_name)
            if not os.path.isdir(doc_path):
                continue
            for file_name in os.listdir(doc_path):
                if file_name.endswith(".json") and file_name.startswith("v"):
                    file_path = os.path.join(doc_path, file_name)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            ver = DocumentVersion.from_dict(data)
                            self._versions.setdefault(ver.doc_id, {})[ver.version_num] = ver
                    except Exception as e:
                        logger.warning(f"Failed to load version file {file_path}: {e}")

    def _persist_version(self, version: DocumentVersion) -> None:
        if not self.storage_dir:
            return
        doc_dir = self._get_doc_dir(version.doc_id)
        os.makedirs(doc_dir, exist_ok=True)
        file_path = os.path.join(doc_dir, f"v{version.version_num}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(version.to_dict(), f, indent=2, ensure_ascii=False)

    def create_versioned_clauses(
        self,
        doc_id: str,
        version_num: int,
        raw_clauses: List[Dict[str, Any]]
    ) -> List[VersionedClause]:
        """
        Converts raw parsed clauses (as produced by the existing parser) into VersionedClause objects.
        """
        versioned_clauses = []
        # Track duplicate raw clause IDs to ensure stable disambiguation
        id_counts: Dict[str, int] = {}

        for idx, clause in enumerate(raw_clauses):
            raw_id = clause.get("clause_id") or clause.get("id") or f"clause_{idx}"
            text = clause.get("text", "")
            section = clause.get("section")
            parent_id = clause.get("parent_id")

            occurrence = id_counts.get(str(raw_id), 0)
            id_counts[str(raw_id)] = occurrence + 1

            stable_id = build_stable_clause_id(
                doc_id=doc_id,
                raw_clause_id=str(raw_id),
                section=section,
                parent_id=parent_id,
                ordinal=idx,
            )

            fingerprint = compute_clause_fingerprint(text)

            v_clause = VersionedClause(
                stable_clause_id=stable_id,
                clause_id=str(raw_id),
                doc_id=doc_id,
                version_num=version_num,
                text=text,
                text_fingerprint=fingerprint,
                section=section,
                parent_id=parent_id,
                ordinal=idx,
                metadata={
                    "source_doc": clause.get("source_doc", ""),
                    "occurrence_index": occurrence,
                }
            )
            versioned_clauses.append(v_clause)

        return versioned_clauses

    def register_version(
        self,
        doc_id: str,
        raw_clauses: List[Dict[str, Any]],
        version_num: Optional[int] = None,
        version_tag: Optional[str] = None,
        doc_type: str = "unknown",
        previous_version_num: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentVersion:
        """
        Registers a new document version from raw parsed clauses.
        Automatically resolves version numbers and archives prior active version.
        """
        doc_versions = self._versions.setdefault(doc_id, {})

        if version_num is None:
            if doc_versions:
                version_num = max(doc_versions.keys()) + 1
            else:
                version_num = 1

        if previous_version_num is None and version_num > 1:
            # Pick highest previous version
            prev_versions = [v for v in doc_versions.keys() if v < version_num]
            if prev_versions:
                previous_version_num = max(prev_versions)

        # Archive the previous version if it was active
        if previous_version_num and previous_version_num in doc_versions:
            prev_ver = doc_versions[previous_version_num]
            if prev_ver.status == VersionStatus.ACTIVE:
                prev_ver.status = VersionStatus.ARCHIVED
                self._persist_version(prev_ver)

        clauses = self.create_versioned_clauses(doc_id, version_num, raw_clauses)
        doc_fingerprint = compute_document_fingerprint(clauses)

        version = DocumentVersion(
            doc_id=doc_id,
            version_num=version_num,
            content_fingerprint=doc_fingerprint,
            upload_timestamp=time.time(),
            previous_version_num=previous_version_num,
            version_tag=version_tag or f"v{version_num}",
            doc_type=doc_type,
            status=VersionStatus.ACTIVE,
            clauses=clauses,
            metadata=metadata or {},
        )

        doc_versions[version_num] = version
        self._persist_version(version)
        return version

    def get_version(self, doc_id: str, version_num: int) -> Optional[DocumentVersion]:
        return self._versions.get(doc_id, {}).get(version_num)

    def get_latest_version(self, doc_id: str) -> Optional[DocumentVersion]:
        doc_versions = self._versions.get(doc_id, {})
        if not doc_versions:
            return None
        latest_num = max(doc_versions.keys())
        return doc_versions[latest_num]

    def get_active_version(self, doc_id: str) -> Optional[DocumentVersion]:
        doc_versions = self._versions.get(doc_id, {})
        for ver in doc_versions.values():
            if ver.status == VersionStatus.ACTIVE:
                return ver
        return self.get_latest_version(doc_id)

    def list_versions(self, doc_id: str) -> List[DocumentVersion]:
        doc_versions = self._versions.get(doc_id, {})
        return [doc_versions[k] for k in sorted(doc_versions.keys())]

    def archive_version(self, doc_id: str, version_num: int) -> None:
        version = self.get_version(doc_id, version_num)
        if version:
            version.status = VersionStatus.ARCHIVED
            self._persist_version(version)
