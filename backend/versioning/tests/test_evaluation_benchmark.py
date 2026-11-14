"""
test_evaluation_benchmark.py

Unit tests for evaluation benchmarking comparing full rebuild vs incremental update.
"""

import unittest
from backend.versioning.version_manager import VersionManager
from backend.versioning.evaluation_benchmark import IncrementalEvaluator


class TestEvaluationBenchmark(unittest.TestCase):

    def setUp(self):
        self.vm = VersionManager()
        self.evaluator = IncrementalEvaluator()

        # 10 clauses in v1
        self.v1_raw = [
            {"clause_id": f"C_{i}", "text": f"Policy condition {i} regarding claim coverage and settlement."}
            for i in range(1, 11)
        ]
        # v2: 8 unchanged, 1 modified (C_9), 1 added (C_11). C_10 deleted.
        self.v2_raw = [
            {"clause_id": f"C_{i}", "text": f"Policy condition {i} regarding claim coverage and settlement."}
            for i in range(1, 9)
        ]
        self.v2_raw.append({"clause_id": "C_9", "text": "Modified policy condition 9 with shorter 15 days deadline."})
        self.v2_raw.append({"clause_id": "C_11", "text": "Newly added condition 11 for digital breach coverage."})

        self.v1 = self.vm.register_version("DOC_BENCH", self.v1_raw, version_num=1)
        self.v2 = self.vm.register_version("DOC_BENCH", self.v2_raw, version_num=2)

    def test_benchmark_metrics_and_savings(self):
        comparison = self.evaluator.run_comparison(
            doc_id="DOC_BENCH",
            old_version=self.v1,
            new_version=self.v2,
            regulatory_clauses=[{"clause_id": f"R_{i}", "text": f"Reg trigger {i}"} for i in range(5)],
        )

        # Full reconstruction would embed all 10 clauses of v2
        self.assertEqual(comparison.full_clauses_embedded, 10)
        # Incremental update embeds only the 2 affected clauses (C_9 modified, C_11 added)
        self.assertEqual(comparison.incr_clauses_embedded, 2)
        # 8 clauses were unchanged and reused
        self.assertEqual(comparison.incr_unchanged_reused, 8)
        self.assertEqual(comparison.incr_percentage_reused, 80.0)

        # Embedding savings: 80% saved
        self.assertEqual(comparison.embeddings_saved_count, 8)
        self.assertEqual(comparison.percentage_embeddings_saved, 80.0)

        # Speedup factor should be > 1.5x
        self.assertTrue(comparison.speedup_factor > 1.5)

        # Active graph equivalence verification
        self.assertTrue(comparison.active_graph_equivalent)
        self.assertIn("active clauses", comparison.equivalence_notes)


if __name__ == "__main__":
    unittest.main()
