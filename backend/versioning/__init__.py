"""
backend/versioning/__init__.py

Version-Aware Knowledge Graph Maintenance Module for Sentra Engine.
Provides document identity, version management, clause matching,
change detection, manifest generation, audit history, incremental updates,
relationship invalidation, targeted reprocessing, safe rollback, and evaluation benchmarking.
"""

from .document_identity import (
    DocumentIdentity,
    DocumentType,
    AmbiguousDocumentIdentityError,
    extract_document_identity,
    resolve_document_identity,
)
from .version_manager import (
    VersionedClause,
    DocumentVersion,
    VersionStatus,
    VersionManager,
    normalize_clause_text,
    compute_clause_fingerprint,
    compute_document_fingerprint,
)
from .clause_matcher import (
    ClauseMatcher,
    MatchConfidence,
    MatchType,
    MatchResult,
    compute_text_similarity,
)
from .change_manifest import (
    ChangeType,
    ClauseChangeRecord,
    SplitMergeRecord,
    AmbiguousRecord,
    ChangeManifest,
)
from .change_detector import (
    ChangeDetector,
    DetectionResult,
)
from .version_history import (
    UpdateRecord,
    VersionHistoryStore,
)
from .incremental_graph_updater import (
    UpdatePlan,
    UpdateExecutionReport,
    IncrementalGraphUpdater,
)
from .relationship_invalidator import (
    RelationshipInvalidator,
    InvalidationReport,
)
from .targeted_reprocessor import (
    TargetedReprocessor,
    TargetedReprocessingReport,
)
from .rollback_manager import (
    RollbackManager,
    RollbackReport,
)
from .evaluation_benchmark import (
    IncrementalEvaluator,
    BenchmarkComparison,
)

__all__ = [
    "DocumentIdentity",
    "DocumentType",
    "AmbiguousDocumentIdentityError",
    "extract_document_identity",
    "resolve_document_identity",
    "VersionedClause",
    "DocumentVersion",
    "VersionStatus",
    "VersionManager",
    "normalize_clause_text",
    "compute_clause_fingerprint",
    "compute_document_fingerprint",
    "ClauseMatcher",
    "MatchConfidence",
    "MatchType",
    "MatchResult",
    "compute_text_similarity",
    "ChangeType",
    "ClauseChangeRecord",
    "SplitMergeRecord",
    "AmbiguousRecord",
    "ChangeManifest",
    "ChangeDetector",
    "DetectionResult",
    "UpdateRecord",
    "VersionHistoryStore",
    "UpdatePlan",
    "UpdateExecutionReport",
    "IncrementalGraphUpdater",
    "RelationshipInvalidator",
    "InvalidationReport",
    "TargetedReprocessor",
    "TargetedReprocessingReport",
    "RollbackManager",
    "RollbackReport",
    "IncrementalEvaluator",
    "BenchmarkComparison",
]
