"""
test_synthetic_scenarios.py

End-to-end unit tests simulating realistic insurance policy updates using synthetic clause data.
Covers real-world insurance regulatory amendments, renumbered sections, added endorsements,
and deleted legacy clauses.
"""

import unittest
from backend.versioning.change_detector import ChangeDetector
from backend.versioning.change_manifest import ChangeType


class TestSyntheticInsuranceScenarios(unittest.TestCase):

    def setUp(self):
        self.detector = ChangeDetector()

    def test_meridian_policy_annual_revision(self):
        """
        Simulates an annual policy renewal (v2026 -> v2027):
        - Clause 1.1: Preamble & Scope (UNCHANGED)
        - Clause 2.1: Turnaround Time (MODIFIED: 30 days -> 15 business days)
        - Clause 2.2: Proof of Loss (UNCHANGED)
        - Clause 3.1: Telegraphic notice (DELETED: obsolete method)
        - Clause 3.2 -> Clause 3.1: Electronic submission (RENUMBERED MODIFIED)
        - Clause 4.1: Cyber Extortion Endorsement (ADDED)
        """
        v2026_clauses = [
            {
                "clause_id": "1.1",
                "section": "1. PREAMBLE",
                "text": "This Policy constitutes the entire contract between Meridian Insurance Company and the Insured Policyholder."
            },
            {
                "clause_id": "2.1",
                "section": "2. CLAIMS SETTLEMENT",
                "text": "The Insurer shall settle all verified claims within thirty (30) calendar days from receipt of all survey reports."
            },
            {
                "clause_id": "2.2",
                "section": "2. CLAIMS SETTLEMENT",
                "text": "Proof of loss must be certified by an IRDAI-licensed independent surveyor for all claims exceeding INR 50,000."
            },
            {
                "clause_id": "3.1",
                "section": "3. NOTICES",
                "text": "Immediate notice of loss may be transmitted by telegraphic dispatch or facsimile machine to the zonal branch office."
            },
            {
                "clause_id": "3.2",
                "section": "3. NOTICES",
                "text": "Notice of claim may also be tendered through the customer support online web portal within 48 hours."
            },
        ]

        v2027_clauses = [
            {
                "clause_id": "1.1",
                "section": "1. PREAMBLE",
                "text": "This Policy constitutes the entire contract between Meridian Insurance Company and the Insured Policyholder."
            },
            {
                "clause_id": "2.1",
                "section": "2. CLAIMS SETTLEMENT",
                "text": "The Insurer shall settle all verified claims within fifteen (15) business days from receipt of all survey reports."
            },
            {
                "clause_id": "2.2",
                "section": "2. CLAIMS SETTLEMENT",
                "text": "Proof of loss must be certified by an IRDAI-licensed independent surveyor for all claims exceeding INR 50,000."
            },
            {
                "clause_id": "3.1",
                "section": "3. NOTICES",
                "text": "Notice of claim must be tendered through the customer support digital web portal or mobile app within 48 hours."
            },
            {
                "clause_id": "4.1",
                "section": "4. CYBER EXTORTION",
                "text": "Coverage is extended to ransomware extortion demands subject to prior written consent of the Insurer's incident response team."
            },
        ]

        result = self.detector.compare_raw_clauses(
            doc_id="MERIDIAN_RULEBOOK",
            old_raw_clauses=v2026_clauses,
            new_raw_clauses=v2027_clauses,
            old_version_num=2026,
            new_version_num=2027,
            doc_type="policy"
        )
        manifest = result.manifest

        # Verify classifications
        self.assertIn("1.1", manifest.unchanged)
        self.assertIn("2.2", manifest.unchanged)
        self.assertEqual(len(manifest.unchanged), 2)

        # 2.1 is modified (in-place)
        self.assertIn("2.1", manifest.modified)
        # 3.1 in new is modified/renumbered from old 3.2
        self.assertIn("3.1", manifest.modified)

        # 3.1 in old (telegraph) is deleted
        self.assertIn("3.1", manifest.deleted)

        # 4.1 is newly added
        self.assertIn("4.1", manifest.added)

        self.assertEqual(manifest.summary["added_count"], 1)
        self.assertEqual(manifest.summary["deleted_count"], 1)
        self.assertEqual(manifest.summary["unchanged_count"], 2)
        self.assertEqual(manifest.summary["modified_count"], 2)

    def test_identical_document_upload_zero_diff(self):
        """
        Uploading the same document without changes must detect 100% UNCHANGED.
        """
        clauses = [
            {"clause_id": "1.1", "text": "Clause one text."},
            {"clause_id": "1.2", "text": "Clause two text."},
            {"clause_id": "1.3", "text": "Clause three text."},
        ]
        result = self.detector.compare_raw_clauses(
            doc_id="DOC_IDENTICAL",
            old_raw_clauses=clauses,
            new_raw_clauses=clauses,
            old_version_num=1,
            new_version_num=2,
        )
        manifest = result.manifest

        self.assertEqual(len(manifest.unchanged), 3)
        self.assertEqual(len(manifest.modified), 0)
        self.assertEqual(len(manifest.added), 0)
        self.assertEqual(len(manifest.deleted), 0)
        self.assertFalse(manifest.requires_human_review)
        self.assertEqual(manifest.content_fingerprint_old, manifest.content_fingerprint_new)

    def test_regulatory_circular_amendment(self):
        """
        Simulates regulatory amendment where a mandatory health waiting period is amended:
        - 10 total clauses: 8 unchanged, 1 modified, 1 added.
        - Verify 80% unchanged clause reuse rate.
        """
        old_reg = [
            {"clause_id": f"Reg_{i}", "text": f"Standard regulatory provision {i} regarding statutory compliance."}
            for i in range(1, 10)
        ]
        old_reg.append({
            "clause_id": "Reg_10",
            "text": "Waiting period for pre-existing disease coverage shall not exceed 36 months."
        })

        new_reg = [
            {"clause_id": f"Reg_{i}", "text": f"Standard regulatory provision {i} regarding statutory compliance."}
            for i in range(1, 10)
        ]
        new_reg.append({
            "clause_id": "Reg_10",
            "text": "Waiting period for pre-existing disease coverage shall not exceed 24 months."
        })
        new_reg.append({
            "clause_id": "Reg_11",
            "text": "Insurers must provide cashless claim processing within 1 hour of hospital submission."
        })

        result = self.detector.compare_raw_clauses(
            doc_id="IRDAI_HEALTH_CIRCULAR",
            old_raw_clauses=old_reg,
            new_raw_clauses=new_reg,
            old_version_num=1,
            new_version_num=2,
            doc_type="regulatory"
        )
        manifest = result.manifest

        self.assertEqual(len(manifest.unchanged), 9)
        self.assertEqual(manifest.modified, ["Reg_10"])
        self.assertEqual(manifest.added, ["Reg_11"])
        self.assertEqual(manifest.deleted, [])

        reuse_percentage = (len(manifest.unchanged) / len(old_reg)) * 100.0
        self.assertEqual(reuse_percentage, 90.0)


if __name__ == "__main__":
    unittest.main()
