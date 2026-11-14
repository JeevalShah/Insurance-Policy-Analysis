"""
test_targeted_reprocessor.py

Unit tests for targeted embedding generation, candidate retrieval,
and dependency re-evaluation.
"""

import unittest
from unittest.mock import MagicMock

from backend.versioning.version_manager import VersionManager
from backend.versioning.change_detector import ChangeDetector
from backend.versioning.targeted_reprocessor import TargetedReprocessor


class TestTargetedReprocessor(unittest.TestCase):

    def setUp(self):
        self.vm = VersionManager()
        self.detector = ChangeDetector()

        self.old_raw = [
            {"clause_id": "1.1", "text": "General scope and definitions."},
            {"clause_id": "2.1", "text": "Notice of claim must be filed within 30 days."},
            {"clause_id": "2.2", "text": "Settlement takes place under terms of Clause 2.1."},
        ]
        self.new_raw = [
            {"clause_id": "1.1", "text": "General scope and definitions."},
            {"clause_id": "2.1", "text": "Notice of claim must be filed within 15 days."},
            {"clause_id": "2.2", "text": "Settlement takes place under terms of Clause 2.1."},
            {"clause_id": "3.1", "text": "All claims require verification as per clause 2.1 and Clause 1.1."},
        ]

        self.v1 = self.vm.register_version("DOC_TARGET", self.old_raw, version_num=1)
        self.v2 = self.vm.register_version("DOC_TARGET", self.new_raw, version_num=2)
        self.detection = self.detector.detect_changes(self.v1, self.v2)

    def test_targeted_embedding_and_dependency_reprocessing(self):
        # Mock embedder to verify only affected clauses are embedded
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 768

        reprocessor = TargetedReprocessor(embedder=mock_embedder, classifier=None, driver=None)

        reg_clauses = [
            {"clause_id": "REG_1", "text": "Insurers must provide clear notice of claim requirements within 15 days."},
            {"clause_id": "REG_2", "text": "Preamble and definitions statutory compliance."},
        ]

        report = reprocessor.reprocess_incremental_policy(
            manifest=self.detection.manifest,
            session_id="session_target",
            new_version=self.v2,
            old_version=self.v1,
            regulatory_clauses=reg_clauses,
            dry_run=False,
        )

        # In v2: 1.1 is unchanged, 2.2 is unchanged.
        # 2.1 is modified, 3.1 is added.
        # Total clauses in v2 = 4. Unchanged reused = 2. Affected embedded = 2.
        self.assertEqual(report.embeddings_reused, 2)
        self.assertEqual(report.embeddings_generated, 2)
        self.assertEqual(report.percentage_embeddings_saved, 50.0)

        # Mock embedder should have been called only 2 times (for 2.1 and 3.1), not 4 times!
        self.assertEqual(mock_embedder.embed_query.call_count, 2)

        # Dependency edge re-evaluation:
        # Clause 3.1 text references "clause 2.1" and "Clause 1.1" -> 2 dependency edges found
        self.assertTrue(report.dependency_edges_written >= 2)


if __name__ == "__main__":
    unittest.main()
