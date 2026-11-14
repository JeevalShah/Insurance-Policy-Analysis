import unittest
import os
import tempfile
from services.user_document_registry import UserDocumentRegistry
from versioning.version_manager import VersionManager
from versioning.version_history import VersionHistoryStore
from versioning.document_identity import AmbiguousDocumentIdentityError

class TestUserDocumentRegistry(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, "test_docs.db")
        self.registry = UserDocumentRegistry(db_path=db_path)
        self.storage_dir = os.path.join(self.temp_dir.name, "versions")
        self.history_dir = os.path.join(self.temp_dir.name, "history")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_multi_user_document_isolation(self):
        # User A registers 'policy.docx'
        doc_a = self.registry.register_document(
            user_id="user_A",
            doc_id="DOC_POLICY_A",
            filename="policy.docx",
            doc_type="policy",
            title="User A Policy"
        )
        self.assertIsNotNone(doc_a)

        # User B registers 'policy.docx' with same filename
        doc_b = self.registry.register_document(
            user_id="user_B",
            doc_id="DOC_POLICY_B",
            filename="policy.docx",
            doc_type="policy",
            title="User B Policy"
        )
        self.assertIsNotNone(doc_b)

        # User A list does not contain User B's doc
        docs_a = self.registry.list_user_documents("user_A")
        self.assertEqual(len(docs_a), 1)
        self.assertEqual(docs_a[0]["doc_id"], "DOC_POLICY_A")

        # User B cannot get User A's doc
        self.assertIsNone(self.registry.get_document("user_B", "DOC_POLICY_A"))
        self.assertIsNotNone(self.registry.get_document("user_B", "DOC_POLICY_B"))

    def test_document_level_isolation_same_user(self):
        # Same user owns multiple independent documents
        self.registry.register_document("user_1", "DOC_1", "doc1.pdf", "policy")
        self.registry.register_document("user_1", "DOC_2", "doc2.pdf", "regulatory")

        # Updating DOC_1 does not affect DOC_2
        self.registry.update_document_version("user_1", "DOC_1", new_version=2, new_fingerprint="fp2")
        d1 = self.registry.get_document("user_1", "DOC_1")
        d2 = self.registry.get_document("user_1", "DOC_2")

        self.assertEqual(d1["current_version"], 2)
        self.assertEqual(d2["current_version"], 1)

        # Deleting DOC_1 does not affect DOC_2
        self.registry.delete_document("user_1", "DOC_1")
        self.assertIsNone(self.registry.get_document_by_filename("user_1", "doc1.pdf"))
        self.assertIsNotNone(self.registry.get_document_by_filename("user_1", "doc2.pdf"))

    def test_user_partitioned_version_managers(self):
        # User A and User B can have documents with identical doc_id without colliding on disk
        vm_a = VersionManager(storage_dir=self.storage_dir, user_id="user_A")
        vm_b = VersionManager(storage_dir=self.storage_dir, user_id="user_B")

        clauses_a = [{"clause_id": "1.0", "text": "User A text"}]
        clauses_b = [{"clause_id": "1.0", "text": "User B text"}]

        ver_a = vm_a.register_version("SHARED_DOC_ID", clauses_a, version_num=1)
        ver_b = vm_b.register_version("SHARED_DOC_ID", clauses_b, version_num=1)

        self.assertEqual(ver_a.clauses[0].text, "User A text")
        self.assertEqual(ver_b.clauses[0].text, "User B text")

        # Verify disk directories are separate
        self.assertTrue(os.path.exists(os.path.join(self.storage_dir, "users", "user_A", "SHARED_DOC_ID")))
        self.assertTrue(os.path.exists(os.path.join(self.storage_dir, "users", "user_B", "SHARED_DOC_ID")))

    def test_resolve_user_document_identity(self):
        self.registry.register_document("user_X", "MY_DOC", "my_policy.pdf", "policy")

        # Resolving known filename yields registered identity
        ident = self.registry.resolve_user_document_identity("user_X", filename="my_policy.pdf")
        self.assertEqual(ident.doc_id, "MY_DOC")

        # Another user resolving the same filename without explicit ID raises AmbiguousDocumentIdentityError
        with self.assertRaises(AmbiguousDocumentIdentityError):
            self.registry.resolve_user_document_identity("user_Y", filename="my_policy.pdf", allow_unconfirmed=False)

if __name__ == "__main__":
    unittest.main()
