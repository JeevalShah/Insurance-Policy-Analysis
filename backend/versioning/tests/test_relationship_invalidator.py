"""
test_relationship_invalidator.py

Unit tests for relationship invalidation and affected clause scoping.
"""

import unittest
from backend.versioning.version_manager import VersionManager
from backend.versioning.change_detector import ChangeDetector
from backend.versioning.relationship_invalidator import RelationshipInvalidator, InvalidationReport


class TestRelationshipInvalidator(unittest.TestCase):

    def setUp(self):
        self.vm = VersionManager()
        self.detector = ChangeDetector()
        self.invalidator = RelationshipInvalidator(driver=None)

    def test_invalidation_planning(self):
        old_raw = [
            {"clause_id": "1.1", "text": "Unchanged text."},
            {"clause_id": "1.2", "text": "Original notice period 30 days."},
            {"clause_id": "1.3", "text": "Deleted fax clause."},
        ]
        new_raw = [
            {"clause_id": "1.1", "text": "Unchanged text."},
            {"clause_id": "1.2", "text": "Amended notice period 15 days."},
            {"clause_id": "1.4", "text": "New electronic portal clause."},
        ]
        v1 = self.vm.register_version("DOC_INV", old_raw, version_num=1)
        v2 = self.vm.register_version("DOC_INV", new_raw, version_num=2)
        detection = self.detector.detect_changes(v1, v2)

        report = self.invalidator.plan_invalidation(
            manifest=detection.manifest,
            session_id="session_inv",
            doc_type="policy"
        )

        # 1.2 is modified, 1.3 is deleted -> both must be in affected policy clauses
        self.assertIn("1.2", report.affected_policy_clause_ids)
        self.assertIn("1.3", report.affected_policy_clause_ids)
        # 1.1 is unchanged, 1.4 is added -> neither was an old edge source that needs invalidation
        self.assertNotIn("1.1", report.affected_policy_clause_ids)
        self.assertNotIn("1.4", report.affected_policy_clause_ids)
        self.assertTrue(report.compliance_edges_invalidated >= 2)


if __name__ == "__main__":
    unittest.main()
