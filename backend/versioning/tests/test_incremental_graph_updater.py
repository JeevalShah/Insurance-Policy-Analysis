"""
test_incremental_graph_updater.py

Unit and integration tests for incremental Neo4j updates, dry-run mode,
transaction safety, rollback on failure, and update idempotency.
"""

import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from backend.versioning.version_manager import VersionManager
from backend.versioning.change_detector import ChangeDetector
from backend.versioning.version_history import VersionHistoryStore
from backend.versioning.incremental_graph_updater import (
    IncrementalGraphUpdater,
    UpdatePlan,
    UpdateExecutionReport,
)


class MockTransaction:
    """Mock Neo4j transaction context tracking Cypher statements."""

    def __init__(self, should_fail: bool = False):
        self.statements = []
        self.committed = False
        self.rolled_back = False
        self.should_fail = should_fail

    def run(self, query: str, parameters: dict = None):
        if self.should_fail and "SET n.status = 'inactive'" in query:
            raise RuntimeError("Simulated transient database write failure")

        self.statements.append({"query": query, "parameters": parameters or {}})
        mock_result = MagicMock()
        mock_result.single.return_value = {"deleted_rels": 1}
        return mock_result

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        return False


class MockSession:
    """Mock Neo4j session."""

    def __init__(self, tx: MockTransaction):
        self.tx = tx

    def begin_transaction(self):
        return self.tx

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockDriver:
    """Mock Neo4j driver providing mock session and transaction."""

    def __init__(self, should_fail: bool = False):
        self.tx = MockTransaction(should_fail=should_fail)

    def session(self):
        return MockSession(self.tx)


class TestIncrementalGraphUpdater(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.history_store = VersionHistoryStore(storage_dir=self.temp_dir)
        self.vm = VersionManager()
        self.detector = ChangeDetector()

        # Build sample v1 and v2
        self.old_raw = [
            {"clause_id": "1.1", "text": "Unchanged clause text regarding general scope."},
            {"clause_id": "1.2", "text": "Notice of claim must be submitted within 30 days."},
            {"clause_id": "1.3", "text": "Telegraphic notices are permitted."},
        ]
        self.new_raw = [
            {"clause_id": "1.1", "text": "Unchanged clause text regarding general scope."},
            {"clause_id": "1.2", "text": "Notice of claim must be submitted within 15 days."},
            {"clause_id": "1.4", "text": "All submissions must be authenticated via 2FA portal."},
        ]

        self.v1 = self.vm.register_version("DOC_PLAN", self.old_raw, version_num=1)
        self.v2 = self.vm.register_version("DOC_PLAN", self.new_raw, version_num=2)
        self.detection_result = self.detector.detect_changes(self.v1, self.v2)
        self.manifest = self.detection_result.manifest

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_update_plan_generation(self):
        updater = IncrementalGraphUpdater(driver=None, history_store=self.history_store)
        plan = updater.generate_update_plan(
            manifest=self.manifest,
            session_id="test_session_1",
            new_version=self.v2,
            old_version=self.v1,
        )

        self.assertEqual(plan.document_id, "DOC_PLAN")
        self.assertEqual(plan.old_version, 1)
        self.assertEqual(plan.new_version, 2)
        self.assertEqual(len(plan.nodes_to_create), 1)  # 1.4 added
        self.assertEqual(len(plan.nodes_to_update), 1)  # 1.2 modified
        self.assertEqual(len(plan.nodes_to_deactivate), 1)  # 1.3 deleted
        self.assertEqual(len(plan.unchanged_nodes_retained), 1)  # 1.1 unchanged

        # Verify modified node update plan includes historical snapshot information
        update_item = plan.nodes_to_update[0]
        self.assertEqual(update_item["id"], "1.2")
        self.assertIn("30 days", update_item["old_text"])
        self.assertIn("15 days", update_item["new_text"])

    def test_dry_run_execution(self):
        updater = IncrementalGraphUpdater(driver=None, history_store=self.history_store)
        report = updater.apply_update(
            manifest=self.manifest,
            session_id="session_dry_run",
            new_version=self.v2,
            old_version=self.v1,
            dry_run=True,
        )

        self.assertEqual(report.status, "dry_run")
        self.assertEqual(report.nodes_created, 1)
        self.assertEqual(report.nodes_updated, 1)
        self.assertEqual(report.nodes_deactivated, 1)
        self.assertEqual(report.unchanged_reused, 1)

        # Audit history must have recorded the dry-run
        history = self.history_store.get_history("DOC_PLAN")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].status, "dry_run")

    def test_atomic_transaction_execution(self):
        mock_driver = MockDriver(should_fail=False)
        updater = IncrementalGraphUpdater(driver=mock_driver, history_store=self.history_store)

        report = updater.apply_update(
            manifest=self.manifest,
            session_id="session_atomic",
            new_version=self.v2,
            old_version=self.v1,
            dry_run=False,
        )

        self.assertEqual(report.status, "success")
        self.assertEqual(report.nodes_created, 1)
        self.assertEqual(report.nodes_updated, 1)
        self.assertEqual(report.nodes_deactivated, 1)
        self.assertTrue(mock_driver.tx.committed)
        self.assertFalse(mock_driver.tx.rolled_back)

        # Audit history must have recorded success
        history = self.history_store.get_history("DOC_PLAN")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].status, "success")

    def test_transaction_rollback_on_failure(self):
        mock_driver = MockDriver(should_fail=True)
        updater = IncrementalGraphUpdater(driver=mock_driver, history_store=self.history_store)

        report = updater.apply_update(
            manifest=self.manifest,
            session_id="session_failure",
            new_version=self.v2,
            old_version=self.v1,
            dry_run=False,
        )

        self.assertEqual(report.status, "failed")
        self.assertTrue(len(report.errors) > 0)
        self.assertFalse(mock_driver.tx.committed)
        self.assertTrue(mock_driver.tx.rolled_back)

        # Audit history must record failure
        history = self.history_store.get_history("DOC_PLAN")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].status, "failed")

    def test_idempotent_repeated_update(self):
        mock_driver = MockDriver(should_fail=False)
        updater = IncrementalGraphUpdater(driver=mock_driver, history_store=self.history_store)

        # First application
        report1 = updater.apply_update(
            manifest=self.manifest,
            session_id="session_idempotent",
            new_version=self.v2,
            old_version=self.v1,
            dry_run=False,
        )
        self.assertEqual(report1.status, "success")

        # Second application of identical update
        report2 = updater.apply_update(
            manifest=self.manifest,
            session_id="session_idempotent",
            new_version=self.v2,
            old_version=self.v1,
            dry_run=False,
        )
        self.assertEqual(report2.status, "success")
        self.assertEqual(report1.nodes_created, report2.nodes_created)
        self.assertEqual(report1.nodes_updated, report2.nodes_updated)


if __name__ == "__main__":
    unittest.main()
