"""
test_document_identity.py

Unit tests for document identity extraction, resolution, and validation.
"""

import unittest
from backend.versioning.document_identity import (
    DocumentIdentity,
    DocumentType,
    AmbiguousDocumentIdentityError,
    extract_document_identity_from_text,
    resolve_document_identity,
)


class TestDocumentIdentity(unittest.TestCase):

    def test_explicit_doc_id_resolution(self):
        doc = resolve_document_identity(
            explicit_doc_id="POL_MOTOR_2026",
            doc_type=DocumentType.POLICY
        )
        self.assertEqual(doc.doc_id, "POL_MOTOR_2026")
        self.assertEqual(doc.doc_type, DocumentType.POLICY)
        self.assertEqual(doc.metadata.get("source"), "explicit")

    def test_extract_identity_from_document_header(self):
        sample_text = (
            "DOCUMENT 1\n"
            "Motor Insurance Claims Compliance Policy\n"
            "Document ID: MOTOR_CLAIMS_POLICY_001 Version: 2024 Department: Claims Processing\n"
            "SECTION 1 — Claims Submission\n"
            "1.1 Notice shall be given within 24 hours of loss."
        )
        extracted = extract_document_identity_from_text(sample_text)
        self.assertEqual(extracted, "MOTOR_CLAIMS_POLICY_001")

        doc = resolve_document_identity(
            document_text=sample_text,
            doc_type=DocumentType.POLICY
        )
        self.assertEqual(doc.doc_id, "MOTOR_CLAIMS_POLICY_001")
        self.assertEqual(doc.metadata.get("source"), "extracted_from_text")

    def test_extract_circular_reference(self):
        sample_text = (
            "Master Circular on Health Insurance Business\n"
            "Ref: IRDAI/HLT/CIR/PRO/84/5/2024 Date: 29.05.2024\n"
            "To All General Insurers"
        )
        extracted = extract_document_identity_from_text(sample_text)
        self.assertEqual(extracted, "IRDAI/HLT/CIR/PRO/84/5/2024")

    def test_registry_lookup_by_alias(self):
        registry = {
            "DOC_HEALTH_001": DocumentIdentity(
                doc_id="DOC_HEALTH_001",
                doc_type=DocumentType.REGULATORY,
                aliases=["health_guidelines_2024.pdf", "master_circular_health.docx"]
            )
        }
        # Uploading with filename alias should resolve to existing document identity
        doc = resolve_document_identity(
            filename="health_guidelines_2024.pdf",
            registry=registry
        )
        self.assertEqual(doc.doc_id, "DOC_HEALTH_001")

    def test_ambiguity_rejection_without_explicit_id(self):
        # When filename alone is provided and text has no ID, raise AmbiguousDocumentIdentityError
        with self.assertRaises(AmbiguousDocumentIdentityError):
            resolve_document_identity(
                filename="unidentified_policy.pdf",
                document_text="This is an insurance text with no clear document ID in headers.",
                allow_unconfirmed=False
            )

    def test_allow_unconfirmed_fallback(self):
        doc = resolve_document_identity(
            filename="temp_upload_123.pdf",
            document_text="Plain text with no headers.",
            allow_unconfirmed=True
        )
        self.assertTrue(doc.metadata.get("unconfirmed"))
        self.assertTrue(doc.doc_id.startswith("DOC_temp_upload_123"))


if __name__ == "__main__":
    unittest.main()
