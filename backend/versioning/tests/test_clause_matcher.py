"""
test_clause_matcher.py

Unit tests for hybrid clause matching across old and new document versions.
Verifies exact matches, in-place modifications, renumbering, splitting, merging,
and ambiguous match detection.
"""

import unittest
from backend.versioning.version_manager import VersionManager
from backend.versioning.clause_matcher import (
    ClauseMatcher,
    MatchType,
    MatchConfidence,
    compute_text_similarity,
)


class TestClauseMatcher(unittest.TestCase):

    def setUp(self):
        self.vm = VersionManager()
        self.matcher = ClauseMatcher()

    def test_exact_unchanged_matching(self):
        old_raw = [
            {"clause_id": "1.1", "text": "The insured must submit notice within 30 days of the loss."},
            {"clause_id": "1.2", "text": "Claims shall be settled within 15 working days."},
        ]
        new_raw = [
            {"clause_id": "1.1", "text": "The insured must submit notice within 30 days of the loss."},
            {"clause_id": "1.2", "text": "Claims shall be settled within 15 working days."},
        ]
        v1 = self.vm.register_version("DOC_1", old_raw, version_num=1)
        v2 = self.vm.register_version("DOC_1", new_raw, version_num=2)

        result = self.matcher.match(v1.clauses, v2.clauses)
        matches = result["matches"]

        self.assertEqual(len(matches), 2)
        for m in matches:
            self.assertEqual(m.match_type, MatchType.EXACT_UNCHANGED)
            self.assertEqual(m.confidence, MatchConfidence.CERTAIN)
            self.assertEqual(m.similarity_score, 1.0)

    def test_in_place_modification(self):
        old_raw = [
            {"clause_id": "2.1", "text": "The insurer shall settle claims within 30 calendar days of documentation."},
        ]
        new_raw = [
            {"clause_id": "2.1", "text": "The insurer shall settle claims within 15 business days of documentation."},
        ]
        v1 = self.vm.register_version("DOC_MOD", old_raw, version_num=1)
        v2 = self.vm.register_version("DOC_MOD", new_raw, version_num=2)

        result = self.matcher.match(v1.clauses, v2.clauses)
        matches = result["matches"]

        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual(m.match_type, MatchType.IN_PLACE_MODIFIED)
        self.assertTrue(m.similarity_score >= 0.70)
        self.assertEqual(m.old_clause.clause_id, "2.1")
        self.assertEqual(m.new_clause.clause_id, "2.1")

    def test_renumbered_clause_identical_content(self):
        old_raw = [
            {"clause_id": "1.2", "text": "Pre-authorization is mandatory for cashless hospitalization at network hospitals."},
        ]
        new_raw = [
            {"clause_id": "1.3", "text": "Pre-authorization is mandatory for cashless hospitalization at network hospitals."},
        ]
        v1 = self.vm.register_version("DOC_RENUM", old_raw, version_num=1)
        v2 = self.vm.register_version("DOC_RENUM", new_raw, version_num=2)

        result = self.matcher.match(v1.clauses, v2.clauses)
        matches = result["matches"]

        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual(m.match_type, MatchType.RENUMBERED_UNCHANGED)
        self.assertEqual(m.old_clause.clause_id, "1.2")
        self.assertEqual(m.new_clause.clause_id, "1.3")
        self.assertEqual(m.similarity_score, 1.0)

    def test_renumbered_clause_modified_content(self):
        old_raw = [
            {"clause_id": "3.1", "text": "The waiting period for pre-existing diseases shall be 36 consecutive months of coverage."},
        ]
        new_raw = [
            {"clause_id": "3.2", "text": "The waiting period for pre-existing diseases shall be reduced to 24 consecutive months of coverage."},
        ]
        v1 = self.vm.register_version("DOC_RENUM_MOD", old_raw, version_num=1)
        v2 = self.vm.register_version("DOC_RENUM_MOD", new_raw, version_num=2)

        result = self.matcher.match(v1.clauses, v2.clauses)
        matches = result["matches"]

        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual(m.match_type, MatchType.RENUMBERED_MODIFIED)
        self.assertEqual(m.old_clause.clause_id, "3.1")
        self.assertEqual(m.new_clause.clause_id, "3.2")
        self.assertTrue(m.similarity_score >= 0.75)

    def test_clause_splitting_detection(self):
        old_raw = [
            {
                "clause_id": "4.1",
                "text": "The customer must notify the insurer within 48 hours of admission. All original hospital bills and medical discharge summaries must be submitted within 15 days."
            }
        ]
        new_raw = [
            {
                "clause_id": "4.1",
                "text": "The customer must notify the insurer within 48 hours of admission."
            },
            {
                "clause_id": "4.2",
                "text": "All original hospital bills and medical discharge summaries must be submitted within 15 days."
            }
        ]
        v1 = self.vm.register_version("DOC_SPLIT", old_raw, version_num=1)
        v2 = self.vm.register_version("DOC_SPLIT", new_raw, version_num=2)

        result = self.matcher.match(v1.clauses, v2.clauses)
        splits = result["splits"]

        self.assertEqual(len(splits), 1)
        s = splits[0]
        self.assertEqual(s["old_clause"].clause_id, "4.1")
        target_ids = [c.clause_id for c in s["target_new_clauses"]]
        self.assertEqual(target_ids, ["4.1", "4.2"])

    def test_clause_merging_detection(self):
        old_raw = [
            {
                "clause_id": "5.1",
                "text": "Vehicles exceeding 10 years of age are subject to 20 percent higher deductible."
            },
            {
                "clause_id": "5.2",
                "text": "Commercial carriage vehicles are subject to an additional compulsory deductible of 5000 INR."
            }
        ]
        new_raw = [
            {
                "clause_id": "5.1",
                "text": "Vehicles exceeding 10 years of age are subject to 20 percent higher deductible. Commercial carriage vehicles are subject to an additional compulsory deductible of 5000 INR."
            }
        ]
        v1 = self.vm.register_version("DOC_MERGE", old_raw, version_num=1)
        v2 = self.vm.register_version("DOC_MERGE", new_raw, version_num=2)

        result = self.matcher.match(v1.clauses, v2.clauses)
        merges = result["merges"]

        self.assertEqual(len(merges), 1)
        m = merges[0]
        source_ids = [c.clause_id for c in m["source_old_clauses"]]
        self.assertEqual(source_ids, ["5.1", "5.2"])
        self.assertEqual(m["target_new_clause"].clause_id, "5.1")

    def test_ambiguous_match_flagged(self):
        # Two old clauses with very similar text (e.g. standard boilerplates differing by only 1 word)
        old_raw = [
            {"clause_id": "9.1", "text": "Annual premium payments may be made through electronic bank transfer, net banking, or debit card."},
            {"clause_id": "9.2", "text": "Monthly premium payments may be made through electronic bank transfer, net banking, or debit card."},
        ]
        # New clause rephrased without the frequency word
        new_raw = [
            {"clause_id": "10.1", "text": "Premium payments may be made through electronic bank transfer, net banking, or debit card."},
        ]
        v1 = self.vm.register_version("DOC_AMB", old_raw, version_num=1)
        v2 = self.vm.register_version("DOC_AMB", new_raw, version_num=2)

        result = self.matcher.match(v1.clauses, v2.clauses)
        ambiguous = result["ambiguous"]

        self.assertEqual(len(ambiguous), 1)
        amb = ambiguous[0]
        self.assertEqual(amb.match_type, MatchType.AMBIGUOUS)
        self.assertEqual(amb.confidence, MatchConfidence.AMBIGUOUS)
        self.assertTrue(len(amb.candidate_matches) >= 2)


if __name__ == "__main__":
    unittest.main()
