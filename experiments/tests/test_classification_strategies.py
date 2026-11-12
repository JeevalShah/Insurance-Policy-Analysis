"""Stage D tests use a fake classifier and a temporary SQLite cache."""

import tempfile
import unittest
from pathlib import Path

from experiments.classification_strategies import ClassificationCache, run_strategy


def pair(pid="p1", rid="r1", polid="x1", reg="reg text", policy="policy text"):
    return {"pair_id": pid, "regulatory_clause_id": rid, "policy_clause_id": polid,
            "regulatory_text": reg, "policy_text": policy}


class ClassificationStrategyTests(unittest.TestCase):
    def test_all_strategies_cover_same_pairs_with_fake_client(self):
        pairs = [pair("p1", "r1"), pair("p2", "r1", "x2"), pair("p3", "r2", "x3")]
        def fake(batch):
            return [{"pair_id": item["pair_id"], "predicted_label": "SUPPORTING"} for item in batch]
        expected = {item["pair_id"] for item in pairs}
        for strategy in ("sequential", "thread_parallel", "production_batch", "batch_5", "batch_10", "batch_20"):
            predictions, metrics = run_strategy(pairs, strategy, fake, workers=2)
            self.assertEqual(set(predictions), expected, strategy)
            self.assertEqual(metrics["error_count"], 0)

    def test_cache_hits_and_content_changes_invalidate_only_matching_pair(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "outputs") as folder:
            cache = ClassificationCache(Path(folder) / "cache.sqlite3")
            pairs = [pair("p1", "r1", "x1"), pair("p2", "r1", "x2", policy="other policy")]
            calls = []
            def fake(batch):
                calls.extend(item["pair_id"] for item in batch)
                return [{"pair_id": item["pair_id"], "predicted_label": "COMPLIANT"} for item in batch]
            run_strategy(pairs, "sequential", fake, cache=cache, model_version="model-a")
            self.assertEqual(len(calls), 2)
            unchanged, metrics = run_strategy(pairs, "sequential", fake, cache=cache, model_version="model-a")
            self.assertEqual(metrics["cache_hit_count"], 2)
            self.assertEqual(len(calls), 2)
            changed = [pairs[0], pair("p2", "r1", "x2", policy="edited policy")]
            run_strategy(changed, "sequential", fake, cache=cache, model_version="model-a")
            self.assertEqual(calls[-1], "p2")
            self.assertEqual(unchanged["p1"], "COMPLIANT")


if __name__ == "__main__":
    unittest.main()
