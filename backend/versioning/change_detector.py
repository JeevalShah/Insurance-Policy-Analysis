"""
change_detector.py

High-level change detection coordinator for Sentra Engine document versioning.
Consumes old and new document versions, executes hybrid clause matching,
and compiles the structured Change Manifest.
"""

from dataclasses import dataclass, field
import logging
from typing import List, Dict, Optional, Any

from .document_identity import DocumentIdentity
from .version_manager import (
    VersionedClause,
    DocumentVersion,
    VersionManager,
)
from .clause_matcher import (
    ClauseMatcher,
    MatchResult,
    MatchType,
    MatchConfidence,
)
from .change_manifest import (
    ChangeType,
    ClauseChangeRecord,
    SplitMergeRecord,
    AmbiguousRecord,
    ChangeManifest,
)

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """
    Encapsulates the complete change detection output, including the manifest
    and direct object references to the affected clauses.
    """
    manifest: ChangeManifest
    old_version: DocumentVersion
    new_version: DocumentVersion
    unchanged_clauses: List[VersionedClause] = field(default_factory=list)
    modified_clauses: List[Dict[str, Any]] = field(default_factory=list)
    added_clauses: List[VersionedClause] = field(default_factory=list)
    deleted_clauses: List[VersionedClause] = field(default_factory=list)


class ChangeDetector:
    """
    Detects clause-level differences between document versions and produces ChangeManifests.
    """

    def __init__(self, matcher: Optional[ClauseMatcher] = None):
        self.matcher = matcher or ClauseMatcher()

    def detect_changes(
        self,
        old_version: DocumentVersion,
        new_version: DocumentVersion
    ) -> DetectionResult:
        """
        Compares two DocumentVersion instances and produces a structured ChangeManifest.
        """
        match_data = self.matcher.match(old_version.clauses, new_version.clauses)

        matches: List[MatchResult] = match_data["matches"]
        splits: List[Dict[str, Any]] = match_data["splits"]
        merges: List[Dict[str, Any]] = match_data["merges"]
        unmatched_old: List[VersionedClause] = match_data["unmatched_old"]
        unmatched_new: List[VersionedClause] = match_data["unmatched_new"]
        ambiguous_matches: List[MatchResult] = match_data["ambiguous"]

        manifest = ChangeManifest(
            document_id=new_version.doc_id,
            old_version=old_version.version_num,
            new_version=new_version.version_num,
            content_fingerprint_old=old_version.content_fingerprint,
            content_fingerprint_new=new_version.content_fingerprint,
        )

        unchanged_clauses: List[VersionedClause] = []
        modified_clauses: List[Dict[str, Any]] = []
        added_clauses: List[VersionedClause] = []
        deleted_clauses: List[VersionedClause] = []

        # 1. Process 1-to-1 matches
        for m in matches:
            if m.match_type == MatchType.EXACT_UNCHANGED:
                if m.new_clause and m.old_clause:
                    manifest.unchanged.append(m.new_clause.clause_id)
                    unchanged_clauses.append(m.new_clause)
                    manifest.records.append(ClauseChangeRecord(
                        stable_clause_id=m.new_clause.stable_clause_id,
                        clause_id=m.new_clause.clause_id,
                        change_type=ChangeType.UNCHANGED,
                        old_clause_id=m.old_clause.clause_id,
                        old_stable_id=m.old_clause.stable_clause_id,
                        old_fingerprint=m.old_clause.text_fingerprint,
                        new_fingerprint=m.new_clause.text_fingerprint,
                        similarity_score=1.0,
                        match_type=m.match_type.value,
                        notes=m.notes,
                    ))

            elif m.match_type in (
                MatchType.IN_PLACE_MODIFIED,
                MatchType.RENUMBERED_UNCHANGED,
                MatchType.RENUMBERED_MODIFIED,
            ):
                if m.new_clause and m.old_clause:
                    manifest.modified.append(m.new_clause.clause_id)
                    modified_clauses.append({
                        "old_clause": m.old_clause,
                        "new_clause": m.new_clause,
                        "similarity": m.similarity_score,
                        "match_type": m.match_type.value,
                    })
                    manifest.records.append(ClauseChangeRecord(
                        stable_clause_id=m.new_clause.stable_clause_id,
                        clause_id=m.new_clause.clause_id,
                        change_type=ChangeType.MODIFIED,
                        old_clause_id=m.old_clause.clause_id,
                        old_stable_id=m.old_clause.stable_clause_id,
                        old_fingerprint=m.old_clause.text_fingerprint,
                        new_fingerprint=m.new_clause.text_fingerprint,
                        similarity_score=m.similarity_score,
                        match_type=m.match_type.value,
                        notes=m.notes,
                        details={
                            "renumbered": m.old_clause.clause_id != m.new_clause.clause_id,
                            "content_identical": m.old_clause.text_fingerprint == m.new_clause.text_fingerprint,
                        }
                    ))

        # 2. Process Added Clauses
        for new_c in unmatched_new:
            manifest.added.append(new_c.clause_id)
            added_clauses.append(new_c)
            manifest.records.append(ClauseChangeRecord(
                stable_clause_id=new_c.stable_clause_id,
                clause_id=new_c.clause_id,
                change_type=ChangeType.ADDED,
                new_fingerprint=new_c.text_fingerprint,
                similarity_score=0.0,
                match_type=MatchType.UNMATCHED.value,
                notes=f"Newly added clause '{new_c.clause_id}' in version {new_version.version_num}.",
            ))

        # 3. Process Deleted Clauses
        for old_c in unmatched_old:
            manifest.deleted.append(old_c.clause_id)
            deleted_clauses.append(old_c)
            manifest.records.append(ClauseChangeRecord(
                stable_clause_id=old_c.stable_clause_id,
                clause_id=old_c.clause_id,
                change_type=ChangeType.DELETED,
                old_clause_id=old_c.clause_id,
                old_stable_id=old_c.stable_clause_id,
                old_fingerprint=old_c.text_fingerprint,
                similarity_score=0.0,
                match_type=MatchType.UNMATCHED.value,
                notes=f"Clause '{old_c.clause_id}' removed in version {new_version.version_num}.",
            ))

        # 4. Process Splits (reported, flagged, no unsafe mutations)
        for s in splits:
            old_c = s["old_clause"]
            target_clauses = s["target_new_clauses"]
            split_rec = SplitMergeRecord(
                event_type="split",
                source_clause_ids=[old_c.clause_id],
                target_clause_ids=[c.clause_id for c in target_clauses],
                similarity_score=s["similarity_score"],
                notes=s["notes"],
            )
            manifest.splits.append(split_rec)
            manifest.requires_human_review = True

            manifest.records.append(ClauseChangeRecord(
                stable_clause_id=old_c.stable_clause_id,
                clause_id=old_c.clause_id,
                change_type=ChangeType.SPLIT,
                old_clause_id=old_c.clause_id,
                old_stable_id=old_c.stable_clause_id,
                old_fingerprint=old_c.text_fingerprint,
                similarity_score=s["similarity_score"],
                match_type=MatchType.SPLIT_SOURCE.value,
                notes=s["notes"],
                details={"target_clause_ids": [c.clause_id for c in target_clauses]}
            ))

        # 5. Process Merges (reported, flagged, no unsafe mutations)
        for m in merges:
            source_clauses = m["source_old_clauses"]
            target_c = m["target_new_clause"]
            merge_rec = SplitMergeRecord(
                event_type="merge",
                source_clause_ids=[c.clause_id for c in source_clauses],
                target_clause_ids=[target_c.clause_id],
                similarity_score=m["similarity_score"],
                notes=m["notes"],
            )
            manifest.merges.append(merge_rec)
            manifest.requires_human_review = True

            manifest.records.append(ClauseChangeRecord(
                stable_clause_id=target_c.stable_clause_id,
                clause_id=target_c.clause_id,
                change_type=ChangeType.MERGED,
                new_fingerprint=target_c.text_fingerprint,
                similarity_score=m["similarity_score"],
                match_type=MatchType.MERGE_TARGET.value,
                notes=m["notes"],
                details={"source_clause_ids": [c.clause_id for c in source_clauses]}
            ))

        # 6. Process Ambiguous Matches
        for amb in ambiguous_matches:
            if amb.new_clause:
                amb_rec = AmbiguousRecord(
                    clause_id=amb.new_clause.clause_id,
                    stable_clause_id=amb.new_clause.stable_clause_id,
                    candidates=[{"clause_id": cid, "score": score} for cid, score in amb.candidate_matches],
                    notes=amb.notes,
                )
                manifest.ambiguous.append(amb_rec)
                manifest.requires_human_review = True

                manifest.records.append(ClauseChangeRecord(
                    stable_clause_id=amb.new_clause.stable_clause_id,
                    clause_id=amb.new_clause.clause_id,
                    change_type=ChangeType.AMBIGUOUS,
                    similarity_score=amb.similarity_score,
                    match_type=MatchType.AMBIGUOUS.value,
                    notes=amb.notes,
                    details={"candidates": amb.candidate_matches}
                ))

        # Sort summary arrays for deterministic output
        manifest.added.sort()
        manifest.modified.sort()
        manifest.deleted.sort()
        manifest.unchanged.sort()

        return DetectionResult(
            manifest=manifest,
            old_version=old_version,
            new_version=new_version,
            unchanged_clauses=unchanged_clauses,
            modified_clauses=modified_clauses,
            added_clauses=added_clauses,
            deleted_clauses=deleted_clauses,
        )

    def compare_raw_clauses(
        self,
        doc_id: str,
        old_raw_clauses: List[Dict[str, Any]],
        new_raw_clauses: List[Dict[str, Any]],
        old_version_num: int = 1,
        new_version_num: int = 2,
        doc_type: str = "unknown",
    ) -> DetectionResult:
        """
        Convenience method to compare two lists of raw clauses (straight from parser).
        """
        vm = VersionManager()
        old_ver = vm.register_version(
            doc_id=doc_id,
            raw_clauses=old_raw_clauses,
            version_num=old_version_num,
            doc_type=doc_type,
        )
        new_ver = vm.register_version(
            doc_id=doc_id,
            raw_clauses=new_raw_clauses,
            version_num=new_version_num,
            doc_type=doc_type,
            previous_version_num=old_version_num,
        )
        return self.detect_changes(old_ver, new_ver)
