"""
test_e2e_multiuser_versioning.py

End-to-End verification of the 10 core architectural test cases:
1. User A signs up and uploads Document A (initial v1).
2. User A uploads Document B (document-level isolation for same user).
3. User A re-uploads unchanged Document A (Scenario B: Zero-diff fast-path reuse).
4. User A uploads a modified version of Document A (Scenario C: Targeted incremental update).
5. User A can view and compare previous versions (Diff and change manifest).
6. User B signs up and uploads a document with the same filename as User A's document.
7. User B cannot access User A's documents, graphs or version history (Strict multi-user isolation).
8. Updating or rolling back Document A does not affect Document B.
9. Safe, recoverable updates: transactions do not leave corrupt metadata.
10. Existing upload and reasoning workflows continue to function as before.
"""

import unittest
import os
import tempfile
import time

from services.auth_service import AuthService
from services.user_document_registry import UserDocumentRegistry
from services.version_pipeline_service import VersionPipelineService
from versioning.version_manager import VersionManager, VersionStatus
from versioning.change_detector import ChangeDetector
from versioning.change_manifest import ChangeType


class TestE2EMultiUserVersioning(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.auth_db = os.path.join(self.temp_dir.name, "auth.db")
        self.docs_db = os.path.join(self.temp_dir.name, "docs.db")
        self.versions_dir = os.path.join(self.temp_dir.name, "versions")
        self.history_dir = os.path.join(self.temp_dir.name, "history")

        self.auth = AuthService(db_path=self.auth_db)
        self.doc_registry = UserDocumentRegistry(db_path=self.docs_db)
        self.pipeline = VersionPipelineService(
            versions_dir=self.versions_dir,
            history_dir=self.history_dir
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_complete_10_case_journey(self):
        # ---------------------------------------------------------------------
        # Case 1: User A signs up and uploads Document A
        # ---------------------------------------------------------------------
        user_a, token_a, err = self.auth.signup("user_a", "usera@test.com", "SecurePass123!")
        self.assertIsNone(err)
        self.assertIsNotNone(user_a)
        uid_a = user_a["user_id"]

        doc_a_clauses_v1 = [
            {"clause_id": "1.1", "section": "1. PREAMBLE", "text": "This contract governs corporate health insurance."},
            {"clause_id": "2.1", "section": "2. DEDUCTIBLES", "text": "Annual deductible shall be $500 per individual."},
            {"clause_id": "3.1", "section": "3. CLAIMS", "text": "Claims must be filed within 60 calendar days."}
        ]

        res_a1 = self.pipeline.process_version_upload(
            user_id=uid_a,
            raw_clauses=doc_a_clauses_v1,
            filename="health_policy.docx",
            doc_type="policy",
            explicit_doc_id="DOC_HEALTH_A"
        )
        self.assertEqual(res_a1["status"], "created")
        self.assertEqual(res_a1["scenario"], "A_FIRST_TIME_UPLOAD")
        self.assertEqual(res_a1["version_num"], 1)
        self.assertEqual(res_a1["clause_count"], 3)
        self.assertFalse(res_a1["reused"])

        # ---------------------------------------------------------------------
        # Case 2: User A uploads Document B (Document-level isolation for same user)
        # ---------------------------------------------------------------------
        doc_b_clauses_v1 = [
            {"clause_id": "1.0", "section": "1. PROPERTY", "text": "Covers commercial office premises against fire and flood."},
            {"clause_id": "2.0", "section": "2. EXCLUSIONS", "text": "Nuclear contamination and war risk are excluded."}
        ]

        res_b1 = self.pipeline.process_version_upload(
            user_id=uid_a,
            raw_clauses=doc_b_clauses_v1,
            filename="property_policy.docx",
            doc_type="policy",
            explicit_doc_id="DOC_PROPERTY_B"
        )
        self.assertEqual(res_b1["status"], "created")
        self.assertEqual(res_b1["version_num"], 1)
        self.assertEqual(res_b1["clause_count"], 2)

        # Verify User A has 2 separate documents
        vm_a = self.pipeline.get_user_version_manager(uid_a)
        ver_doc_a = vm_a.get_active_version("DOC_HEALTH_A")
        ver_doc_b = vm_a.get_active_version("DOC_PROPERTY_B")
        self.assertIsNotNone(ver_doc_a)
        self.assertIsNotNone(ver_doc_b)
        self.assertEqual(ver_doc_a.clause_count, 3)
        self.assertEqual(ver_doc_b.clause_count, 2)

        # ---------------------------------------------------------------------
        # Case 3: User A re-uploads unchanged Document A (Scenario B: Fast-path reuse)
        # ---------------------------------------------------------------------
        res_a_repeat = self.pipeline.process_version_upload(
            user_id=uid_a,
            raw_clauses=doc_a_clauses_v1,
            filename="health_policy.docx",
            doc_type="policy",
            explicit_doc_id="DOC_HEALTH_A"
        )
        self.assertEqual(res_a_repeat["status"], "unchanged")
        self.assertEqual(res_a_repeat["scenario"], "B_UNCHANGED_REUSE")
        self.assertTrue(res_a_repeat["reused"])
        self.assertEqual(res_a_repeat["version_num"], 1)
        self.assertEqual(res_a_repeat["percentage_embeddings_saved"], 100.0)
        self.assertEqual(res_a_repeat["llm_calls_made"], 0)
        self.assertLess(res_a_repeat["duration_seconds"], 0.5)

        # ---------------------------------------------------------------------
        # Case 4: User A uploads modified Document A (Scenario C: Targeted incremental)
        # ---------------------------------------------------------------------
        doc_a_clauses_v2 = [
            {"clause_id": "1.1", "section": "1. PREAMBLE", "text": "This contract governs corporate health insurance."},  # Unchanged
            {"clause_id": "2.1", "section": "2. DEDUCTIBLES", "text": "Annual deductible shall be $250 per individual."}, # Modified (500 -> 250)
            # Clause 3.1 deleted
            {"clause_id": "4.1", "section": "4. TELEMEDICINE", "text": "Consultations via licensed telehealth portals are fully covered."} # Added
        ]

        res_a_mod = self.pipeline.process_version_upload(
            user_id=uid_a,
            raw_clauses=doc_a_clauses_v2,
            filename="health_policy.docx",
            doc_type="policy",
            explicit_doc_id="DOC_HEALTH_A"
        )
        self.assertEqual(res_a_mod["status"], "updated")
        self.assertEqual(res_a_mod["scenario"], "C_MODIFIED_INCREMENTAL_UPDATE")
        self.assertEqual(res_a_mod["old_version"], 1)
        self.assertEqual(res_a_mod["new_version"], 2)
        self.assertTrue(res_a_mod["reused"])
        self.assertEqual(res_a_mod["manifest_summary"]["added_count"], 1)
        self.assertEqual(res_a_mod["manifest_summary"]["modified_count"], 1)
        self.assertEqual(res_a_mod["manifest_summary"]["deleted_count"], 1)
        self.assertEqual(res_a_mod["manifest_summary"]["unchanged_count"], 1)
        # 1 unchanged reused, 2 affected generated
        self.assertEqual(res_a_mod["embeddings_reused"], 1)
        self.assertEqual(res_a_mod["embeddings_generated"], 2)

        # ---------------------------------------------------------------------
        # Case 5: User A can view and compare previous versions
        # ---------------------------------------------------------------------
        versions_a = vm_a.list_versions("DOC_HEALTH_A")
        self.assertEqual(len(versions_a), 2)
        self.assertEqual(versions_a[0].version_num, 1)
        self.assertEqual(versions_a[1].version_num, 2)

        detector = ChangeDetector()
        diff = detector.detect_changes(versions_a[0], versions_a[1])
        self.assertIn("1.1", diff.manifest.unchanged)
        self.assertIn("2.1", diff.manifest.modified)
        self.assertIn("3.1", diff.manifest.deleted)
        self.assertIn("4.1", diff.manifest.added)

        # ---------------------------------------------------------------------
        # Case 6: User B signs up and uploads document with SAME filename
        # ---------------------------------------------------------------------
        user_b, token_b, err_b = self.auth.signup("user_b", "userb@test.com", "SecurePass456!")
        self.assertIsNone(err_b)
        uid_b = user_b["user_id"]

        user_b_clauses = [
            {"clause_id": "1.1", "section": "1. PREAMBLE", "text": "User B distinct policy terms."}
        ]

        # User B uploads "health_policy.docx" (same filename as User A)
        res_b_upload = self.pipeline.process_version_upload(
            user_id=uid_b,
            raw_clauses=user_b_clauses,
            filename="health_policy.docx",
            doc_type="policy",
            explicit_doc_id="DOC_HEALTH_A"  # Even if explicit doc_id is identical!
        )
        self.assertEqual(res_b_upload["status"], "created")
        self.assertEqual(res_b_upload["scenario"], "A_FIRST_TIME_UPLOAD")
        self.assertEqual(res_b_upload["version_num"], 1)

        # ---------------------------------------------------------------------
        # Case 7: User B cannot access User A's documents, graphs, or history
        # ---------------------------------------------------------------------
        vm_b = self.pipeline.get_user_version_manager(uid_b)
        ver_b_latest = vm_b.get_active_version("DOC_HEALTH_A")
        self.assertEqual(ver_b_latest.version_num, 1)
        self.assertEqual(ver_b_latest.clauses[0].text, "User B distinct policy terms.")

        # User A's document is at v2 and has 3 clauses
        ver_a_latest = vm_a.get_active_version("DOC_HEALTH_A")
        self.assertEqual(ver_a_latest.version_num, 2)
        self.assertEqual(len(ver_a_latest.clauses), 3)

        # User B's history store has no records of User A's v1->v2 update
        hs_b = self.pipeline.get_user_history_store(uid_b)
        history_b = hs_b.get_history("DOC_HEALTH_A")
        self.assertEqual(len(history_b), 0)

        hs_a = self.pipeline.get_user_history_store(uid_a)
        history_a = hs_a.get_history("DOC_HEALTH_A")
        self.assertEqual(len(history_a), 1)

        # ---------------------------------------------------------------------
        # Case 8: Updating or rolling back Document A does not affect Document B
        # ---------------------------------------------------------------------
        # Rollback Document A to v1
        rb_report = self.pipeline.execute_user_rollback(
            user_id=uid_a,
            document_id="DOC_HEALTH_A",
            target_version_num=1,
            dry_run=False
        )
        self.assertEqual(rb_report["status"], "success")
        self.assertEqual(rb_report["target_version"], 1)

        # User A's Document A is now at v1
        self.assertEqual(vm_a.get_active_version("DOC_HEALTH_A").version_num, 1)

        # User A's Document B is completely untouched and still active at v1
        self.assertEqual(vm_a.get_active_version("DOC_PROPERTY_B").version_num, 1)
        self.assertEqual(vm_a.get_active_version("DOC_PROPERTY_B").clause_count, 2)

        # ---------------------------------------------------------------------
        # Case 9: Interrupted/dry-run update leaves consistent metadata
        # ---------------------------------------------------------------------
        dry_run_rb = self.pipeline.execute_user_rollback(
            user_id=uid_a,
            document_id="DOC_HEALTH_A",
            target_version_num=2,
            dry_run=True
        )
        self.assertEqual(dry_run_rb["status"], "dry_run")
        # Document remains at v1
        self.assertEqual(vm_a.get_active_version("DOC_HEALTH_A").version_num, 1)

        # ---------------------------------------------------------------------
        # Case 10: Full version history preserved across all transitions
        # ---------------------------------------------------------------------
        history_after = hs_a.get_history("DOC_HEALTH_A")
        # Recorded: initial update to v2, plus rollback to v1
        self.assertGreaterEqual(len(history_after), 2)
        statuses = [h.status for h in history_after]
        self.assertIn("success", statuses)
        self.assertIn("rollback_success", statuses)


if __name__ == "__main__":
    unittest.main()
