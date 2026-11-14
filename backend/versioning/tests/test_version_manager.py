"""
test_version_manager.py

Unit tests for version metadata, fingerprinting, stable clause ID generation,
and historical version management.
"""

import shutil
import tempfile
import unittest

from backend.versioning.version_manager import (
    VersionManager,
    VersionStatus,
    normalize_clause_text,
    compute_clause_fingerprint,
    compute_document_fingerprint,
    build_stable_clause_id,
)


class TestVersionManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vm = VersionManager(storage_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_text_normalization_and_fingerprinting(self):
        text_a = 'Clause 1.1: “Insurers shall notify within 24 hours.”  '
        text_b = 'clause 1.1: "insurers  shall notify within   24 hours."'
        text_c = 'Clause 1.1: Insurers shall notify within 48 hours.'

        norm_a = normalize_clause_text(text_a)
        norm_b = normalize_clause_text(text_b)

        self.assertEqual(norm_a, norm_b)
        self.assertEqual(compute_clause_fingerprint(text_a), compute_clause_fingerprint(text_b))
        self.assertNotEqual(compute_clause_fingerprint(text_a), compute_clause_fingerprint(text_c))

    def test_stable_clause_id_generation(self):
        id_1 = build_stable_clause_id("DOC_A", "1.1", section="1", parent_id="none", ordinal=0)
        id_2 = build_stable_clause_id("DOC_A", "1.1", section="2", parent_id="none", ordinal=5)
        # Even with identical raw clause ID "1.1", distinct sections/ordinals produce distinct stable IDs
        self.assertNotEqual(id_1, id_2)
        self.assertIn("DOC_A", id_1)
        self.assertIn("1.1", id_1)

    def test_repeated_clause_ids_in_different_sections(self):
        raw_clauses = [
            {"clause_id": "1", "section": "Chapter 1", "text": "First chapter clause 1"},
            {"clause_id": "2", "section": "Chapter 1", "text": "First chapter clause 2"},
            {"clause_id": "1", "section": "Chapter 2", "text": "Second chapter clause 1"},
        ]
        version = self.vm.register_version(doc_id="DOC_POLICY", raw_clauses=raw_clauses, version_num=1)
        self.assertEqual(version.clause_count, 3)

        stable_ids = [c.stable_clause_id for c in version.clauses]
        self.assertEqual(len(set(stable_ids)), 3, "Stable clause IDs must all be unique despite repeated clause_id '1'")

    def test_version_progression_and_archival(self):
        v1_clauses = [{"clause_id": "1.1", "text": "Initial text v1"}]
        v2_clauses = [{"clause_id": "1.1", "text": "Updated text v2"}]

        v1 = self.vm.register_version(doc_id="DOC_AUTO", raw_clauses=v1_clauses)
        self.assertEqual(v1.version_num, 1)
        self.assertEqual(v1.status, VersionStatus.ACTIVE)

        v2 = self.vm.register_version(doc_id="DOC_AUTO", raw_clauses=v2_clauses)
        self.assertEqual(v2.version_num, 2)
        self.assertEqual(v2.status, VersionStatus.ACTIVE)

        # Previous version should now be ARCHIVED
        stored_v1 = self.vm.get_version("DOC_AUTO", 1)
        self.assertEqual(stored_v1.status, VersionStatus.ARCHIVED)

        # Active version should be v2
        active = self.vm.get_active_version("DOC_AUTO")
        self.assertEqual(active.version_num, 2)

    def test_persistence_and_reload(self):
        raw_clauses = [{"clause_id": "1.1", "text": "Persisted text"}]
        self.vm.register_version(doc_id="DOC_PERSIST", raw_clauses=raw_clauses, version_num=1)

        # Create new manager pointing to same storage
        new_vm = VersionManager(storage_dir=self.temp_dir)
        loaded_v1 = new_vm.get_version("DOC_PERSIST", 1)
        self.assertIsNotNone(loaded_v1)
        self.assertEqual(loaded_v1.clause_count, 1)
        self.assertEqual(loaded_v1.clauses[0].clause_id, "1.1")
        self.assertEqual(loaded_v1.clauses[0].text, "Persisted text")


if __name__ == "__main__":
    unittest.main()
