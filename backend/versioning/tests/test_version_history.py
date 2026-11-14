"""
test_version_history.py

Unit tests for version history recording, persistence, and audit logging.
"""

import shutil
import tempfile
import unittest

from backend.versioning.version_history import VersionHistoryStore, UpdateRecord


class TestVersionHistory(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = VersionHistoryStore(storage_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_and_retrieve_update(self):
        rec = self.store.record_update(
            document_id="DOC_POLICY_100",
            session_id="session_abc_123",
            old_version=1,
            new_version=2,
            status="success",
            added_count=2,
            modified_count=1,
            deleted_count=1,
            unchanged_count=8,
            nodes_created=2,
            nodes_updated=1,
            nodes_deactivated=1,
            relationships_deactivated=3,
            duration_seconds=0.125,
        )

        self.assertEqual(rec.document_id, "DOC_POLICY_100")
        self.assertEqual(rec.status, "success")
        self.assertEqual(rec.added_count, 2)

        history = self.store.get_history("DOC_POLICY_100")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].update_id, rec.update_id)

    def test_persistence_across_instances(self):
        self.store.record_update(
            document_id="DOC_PERSIST_AUDIT",
            session_id="session_xyz",
            old_version=1,
            new_version=2,
            status="dry_run",
            added_count=3,
        )

        new_store = VersionHistoryStore(storage_dir=self.temp_dir)
        history = new_store.get_history("DOC_PERSIST_AUDIT")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].status, "dry_run")
        self.assertEqual(history[0].added_count, 3)

    def test_multiple_version_transitions(self):
        self.store.record_update(
            document_id="DOC_EVOLUTION",
            session_id="session_1",
            old_version=1,
            new_version=2,
            status="success",
        )
        self.store.record_update(
            document_id="DOC_EVOLUTION",
            session_id="session_2",
            old_version=2,
            new_version=3,
            status="success",
        )

        history = self.store.get_history("DOC_EVOLUTION")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].new_version, 2)
        self.assertEqual(history[1].new_version, 3)

        latest = self.store.get_latest_update("DOC_EVOLUTION")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.new_version, 3)


if __name__ == "__main__":
    unittest.main()
