import unittest
import os
import tempfile
import time
from services.version_pipeline_service import VersionPipelineService
from services.user_document_registry import UserDocumentRegistry

class TestVersionPipelineService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.versions_dir = os.path.join(self.temp_dir.name, "versions")
        self.history_dir = os.path.join(self.temp_dir.name, "history")
        self.pipeline = VersionPipelineService(
            versions_dir=self.versions_dir,
            history_dir=self.history_dir
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scenarios_a_b_c_pipeline(self):
        user_id = "user_alpha"
        filename = "corporate_policy_2026.docx"
        clauses_v1 = [
            {"clause_id": "1.1", "section": "1. PREAMBLE", "text": "This Policy applies to all full-time employees."},
            {"clause_id": "2.1", "section": "2. CLAIMS", "text": "Claims must be submitted within 30 days of incident."},
            {"clause_id": "3.1", "section": "3. NOTICES", "text": "Notice may be sent via electronic email."}
        ]

        # -----------------------------------------------------------------
        # SCENARIO A: First-time document upload
        # -----------------------------------------------------------------
        res_a = self.pipeline.process_version_upload(
            user_id=user_id,
            raw_clauses=clauses_v1,
            filename=filename,
            doc_type="policy",
            explicit_doc_id="POLICY_CORP_2026"
        )
        self.assertEqual(res_a["status"], "created")
        self.assertEqual(res_a["scenario"], "A_FIRST_TIME_UPLOAD")
        self.assertEqual(res_a["version_num"], 1)
        self.assertFalse(res_a["reused"])
        self.assertEqual(res_a["clause_count"], 3)
        self.assertGreater(res_a["duration_seconds"], 0)

        # -----------------------------------------------------------------
        # SCENARIO B: Re-upload of UNCHANGED document
        # -----------------------------------------------------------------
        res_b = self.pipeline.process_version_upload(
            user_id=user_id,
            raw_clauses=clauses_v1,
            filename=filename,
            doc_type="policy",
            explicit_doc_id="POLICY_CORP_2026"
        )
        self.assertEqual(res_b["status"], "unchanged")
        self.assertEqual(res_b["scenario"], "B_UNCHANGED_REUSE")
        self.assertEqual(res_b["version_num"], 1)
        self.assertTrue(res_b["reused"])
        self.assertEqual(res_b["embeddings_reused"], 3)
        self.assertEqual(res_b["embeddings_generated"], 0)
        self.assertEqual(res_b["percentage_embeddings_saved"], 100.0)
        self.assertLess(res_b["duration_seconds"], 0.5)

        # -----------------------------------------------------------------
        # SCENARIO C: Re-upload of MODIFIED document (Targeted Incremental)
        # -----------------------------------------------------------------
        clauses_v2 = [
            {"clause_id": "1.1", "section": "1. PREAMBLE", "text": "This Policy applies to all full-time employees."},  # Unchanged
            {"clause_id": "2.1", "section": "2. CLAIMS", "text": "Claims must be submitted within 15 days of incident."}, # Modified (30 -> 15)
            # Clause 3.1 deleted
            {"clause_id": "4.1", "section": "4. SECURITY", "text": "All remote connections must use two-factor authentication."} # Added
        ]

        res_c = self.pipeline.process_version_upload(
            user_id=user_id,
            raw_clauses=clauses_v2,
            filename=filename,
            doc_type="policy",
            explicit_doc_id="POLICY_CORP_2026"
        )
        self.assertEqual(res_c["status"], "updated")
        self.assertEqual(res_c["scenario"], "C_MODIFIED_INCREMENTAL_UPDATE")
        self.assertEqual(res_c["old_version"], 1)
        self.assertEqual(res_c["new_version"], 2)
        self.assertTrue(res_c["reused"])
        self.assertEqual(res_c["manifest_summary"]["added_count"], 1)
        self.assertEqual(res_c["manifest_summary"]["modified_count"], 1)
        self.assertEqual(res_c["manifest_summary"]["deleted_count"], 1)
        self.assertEqual(res_c["manifest_summary"]["unchanged_count"], 1)
        # Embeddings reused for 1 unchanged clause, generated for 2 affected clauses
        self.assertEqual(res_c["embeddings_reused"], 1)
        self.assertEqual(res_c["embeddings_generated"], 2)

    def test_multi_user_graph_and_version_isolation(self):
        # User A and User B upload the exact same document content
        clauses = [
            {"clause_id": "1.0", "section": "SEC1", "text": "Standard confidentiality clause."}
        ]

        # User A uploads
        res_a = self.pipeline.process_version_upload(
            user_id="user_A",
            raw_clauses=clauses,
            filename="confidentiality.docx",
            explicit_doc_id="DOC_CONFIDENTIAL"
        )
        self.assertEqual(res_a["status"], "created")

        # User B uploads the same file
        # User B MUST NOT reuse User A's data; User B gets their own first-time upload
        res_b = self.pipeline.process_version_upload(
            user_id="user_B",
            raw_clauses=clauses,
            filename="confidentiality.docx",
            explicit_doc_id="DOC_CONFIDENTIAL"
        )
        self.assertEqual(res_b["status"], "created")
        self.assertEqual(res_b["scenario"], "A_FIRST_TIME_UPLOAD")

        # User A updates their document to v2
        clauses_modified = [
            {"clause_id": "1.0", "section": "SEC1", "text": "Standard confidentiality clause with strict NDA penalties."}
        ]
        res_a2 = self.pipeline.process_version_upload(
            user_id="user_A",
            raw_clauses=clauses_modified,
            filename="confidentiality.docx",
            explicit_doc_id="DOC_CONFIDENTIAL"
        )
        self.assertEqual(res_a2["new_version"], 2)

        # User B's document must still be at v1
        vm_b = self.pipeline.get_user_version_manager("user_B")
        ver_b = vm_b.get_active_version("DOC_CONFIDENTIAL")
        self.assertEqual(ver_b.version_num, 1)
        self.assertEqual(ver_b.clauses[0].text, "Standard confidentiality clause.")

    def test_user_version_rollback(self):
        user_id = "user_roller"
        doc_id = "DOC_ROLLBACK"
        v1_clauses = [{"clause_id": "1.0", "text": "Original text v1"}]
        v2_clauses = [{"clause_id": "1.0", "text": "Updated text v2"}]

        # Create v1 and v2
        self.pipeline.process_version_upload(user_id=user_id, raw_clauses=v1_clauses, filename="doc.pdf", explicit_doc_id=doc_id)
        self.pipeline.process_version_upload(user_id=user_id, raw_clauses=v2_clauses, filename="doc.pdf", explicit_doc_id=doc_id)

        vm = self.pipeline.get_user_version_manager(user_id)
        self.assertEqual(vm.get_active_version(doc_id).version_num, 2)

        # Rollback to v1
        report = self.pipeline.execute_user_rollback(user_id=user_id, document_id=doc_id, target_version_num=1, dry_run=False)
        self.assertEqual(report["status"], "success")
        self.assertEqual(report["target_version"], 1)

        # Active version is now v1
        self.assertEqual(vm.get_active_version(doc_id).version_num, 1)

if __name__ == "__main__":
    unittest.main()
