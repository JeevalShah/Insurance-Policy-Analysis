"""
test_change_detector.py

Unit tests for change detection and change manifest compilation.
Verifies correct categorization of ADDED, MODIFIED, DELETED, UNCHANGED clauses,
preservation of stable IDs, cryptographic fingerprints, and manifest serialization.
"""

import json
import unittest

from backend.versioning.version_manager import VersionManager
from backend.versioning.change_detector import ChangeDetector
from backend.versioning.change_manifest import ChangeManifest, ChangeType


class TestChangeDetector(unittest.TestCase):

    def setUp(self):
        self.vm = VersionManager()
        self.detector = ChangeDetector()

    def test_standard_manifest_generation(self):
        # Scenario matching Prompt Section 5 Example:
        # added: ["1.4"], modified: ["1.2"], deleted: ["1.3"], unchanged: ["1.1"]
        old_raw = [
            {"clause_id": "1.1", "text": "Unchanged clause text regarding general scope."},
            {"clause_id": "1.2", "text": "Notice of claim must be submitted within 30 days of hospitalization."},
            {"clause_id": "1.3", "text": "Legacy claims submission via physical fax machine is acceptable."},
        ]
        new_raw = [
            {"clause_id": "1.1", "text": "Unchanged clause text regarding general scope."},
            {"clause_id": "1.2", "text": "Notice of claim must be submitted within 15 days of hospitalization."},
            {"clause_id": "1.4", "text": "All submissions must be authenticated via electronic two-factor portal."},
        ]

        result = self.detector.compare_raw_clauses(
            doc_id="DOC_A",
            old_raw_clauses=old_raw,
            new_raw_clauses=new_raw,
            old_version_num=1,
            new_version_num=2,
        )
        manifest = result.manifest

        # Verify summary arrays match the requested format
        self.assertEqual(manifest.document_id, "DOC_A")
        self.assertEqual(manifest.old_version, 1)
        self.assertEqual(manifest.new_version, 2)
        self.assertEqual(manifest.unchanged, ["1.1"])
        self.assertEqual(manifest.modified, ["1.2"])
        self.assertEqual(manifest.deleted, ["1.3"])
        self.assertEqual(manifest.added, ["1.4"])

        # Verify fingerprints exist and differ between versions
        self.assertTrue(bool(manifest.content_fingerprint_old))
        self.assertTrue(bool(manifest.content_fingerprint_new))
        self.assertNotEqual(manifest.content_fingerprint_old, manifest.content_fingerprint_new)

        # Verify detailed records
        record_by_id = {r.clause_id: r for r in manifest.records}
        self.assertEqual(record_by_id["1.1"].change_type, ChangeType.UNCHANGED)
        self.assertEqual(record_by_id["1.2"].change_type, ChangeType.MODIFIED)
        self.assertEqual(record_by_id["1.3"].change_type, ChangeType.DELETED)
        self.assertEqual(record_by_id["1.4"].change_type, ChangeType.ADDED)

        # Verify stable clause ID is present on all records
        for r in manifest.records:
            self.assertTrue(bool(r.stable_clause_id))
            self.assertIn("DOC_A", r.stable_clause_id)

    def test_manifest_json_roundtrip(self):
        old_raw = [{"clause_id": "1", "text": "Text 1"}]
        new_raw = [{"clause_id": "1", "text": "Text 1"}, {"clause_id": "2", "text": "Text 2"}]

        result = self.detector.compare_raw_clauses(
            doc_id="DOC_ROUNDTRIP",
            old_raw_clauses=old_raw,
            new_raw_clauses=new_raw,
        )
        manifest = result.manifest
        json_output = manifest.to_json()

        # Parse back
        loaded_manifest = ChangeManifest.from_json(json_output)
        self.assertEqual(loaded_manifest.document_id, manifest.document_id)
        self.assertEqual(loaded_manifest.old_version, manifest.old_version)
        self.assertEqual(loaded_manifest.new_version, manifest.new_version)
        self.assertEqual(loaded_manifest.unchanged, manifest.unchanged)
        self.assertEqual(loaded_manifest.added, manifest.added)
        self.assertEqual(len(loaded_manifest.records), len(manifest.records))

    def test_split_and_ambiguity_flags_human_review(self):
        old_raw = [
            {"clause_id": "4.1", "text": "Hospital bills must be submitted. Discharge summaries are mandatory."},
        ]
        new_raw = [
            {"clause_id": "4.1", "text": "Hospital bills must be submitted."},
            {"clause_id": "4.2", "text": "Discharge summaries are mandatory."},
        ]
        result = self.detector.compare_raw_clauses(
            doc_id="DOC_REVIEW",
            old_raw_clauses=old_raw,
            new_raw_clauses=new_raw,
        )
        manifest = result.manifest

        self.assertTrue(manifest.requires_human_review)
        self.assertEqual(len(manifest.splits), 1)
        self.assertEqual(manifest.splits[0].target_clause_ids, ["4.1", "4.2"])


if __name__ == "__main__":
    unittest.main()
