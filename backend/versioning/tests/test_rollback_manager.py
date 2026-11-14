"""
test_rollback_manager.py

Unit tests for safe, targeted rollback to an earlier document version.
"""

import shutil
import tempfile
import unittest

from backend.versioning.version_manager import VersionManager, VersionStatus
from backend.versioning.version_history import VersionHistoryStore
from backend.versioning.rollback_manager import RollbackManager


class TestRollbackManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vm = VersionManager(storage_dir=self.temp_dir)
        self.history_store = VersionHistoryStore(storage_dir=self.temp_dir)
        self.rollback_mgr = RollbackManager(
            version_manager=self.vm,
            history_store=self.history_store,
            driver=None,
        )

        # Version 1
        self.v1_raw = [
            {"clause_id": "1.1", "text": "Base clause text."},
            {"clause_id": "1.2", "text": "Notice within 30 days."},
        ]
        # Version 2 (1.2 modified, 1.3 added)
        self.v2_raw = [
            {"clause_id": "1.1", "text": "Base clause text."},
            {"clause_id": "1.2", "text": "Notice within 15 days."},
            {"clause_id": "1.3", "text": "New digital portal."},
        ]

        self.v1 = self.vm.register_version("DOC_ROLLBACK", self.v1_raw, version_num=1)
        self.v2 = self.vm.register_version("DOC_ROLLBACK", self.v2_raw, version_num=2)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dry_run_rollback(self):
        report = self.rollback_mgr.execute_rollback(
            document_id="DOC_ROLLBACK",
            target_version_num=1,
            session_id="session_rb",
            dry_run=True,
        )

        self.assertEqual(report.status, "dry_run")
        self.assertEqual(report.target_version, 1)
        self.assertEqual(report.from_version, 2)
        # 1.2 needs to be restored to 30 days
        self.assertEqual(report.clauses_restored, 1)
        # 1.3 was added in v2, needs deactivation
        self.assertEqual(report.clauses_deactivated, 1)

    def test_live_rollback_state_transition(self):
        # Current active version is v2
        self.assertEqual(self.vm.get_active_version("DOC_ROLLBACK").version_num, 2)

        report = self.rollback_mgr.execute_rollback(
            document_id="DOC_ROLLBACK",
            target_version_num=1,
            session_id="session_live_rb",
            dry_run=False,
        )

        self.assertEqual(report.status, "success")
        self.assertEqual(report.clauses_restored, 1)
        self.assertEqual(report.clauses_deactivated, 1)

        # After rollback, active version in VersionManager must now be v1!
        active_ver = self.vm.get_active_version("DOC_ROLLBACK")
        self.assertEqual(active_ver.version_num, 1)
        self.assertEqual(active_ver.status, VersionStatus.ACTIVE)

        v2 = self.vm.get_version("DOC_ROLLBACK", 2)
        self.assertEqual(v2.status, VersionStatus.ARCHIVED)

        # Audit history must have recorded rollback_success
        history = self.history_store.get_history("DOC_ROLLBACK")
        self.assertTrue(any(h.status == "rollback_success" for h in history))


if __name__ == "__main__":
    unittest.main()
