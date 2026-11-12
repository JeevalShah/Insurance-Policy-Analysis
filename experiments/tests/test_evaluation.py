"""Unit tests for the Stage B evaluation utilities."""

import json
from pathlib import Path
import tempfile
import unittest

from experiments.evaluation import (
    LABELS,
    classification_metrics,
    cohen_kappa,
    evaluate_dataset,
    load_gold_pairs,
    load_predictions,
    load_retrieved_pairs,
    retrieval_coverage,
    validate_gold_pair,
)


def pair(pair_id, reg_id, policy_id, label, *, source="retrieved_candidate", a=None, b=None):
    labels = {}
    if a is not None:
        labels["ann_a"] = a
    if b is not None:
        labels["ann_b"] = b
    return {
        "schema_version": "1.0",
        "pair_id": pair_id,
        "regulatory_clause_id": reg_id,
        "policy_clause_id": policy_id,
        "regulatory_text": "synthetic regulatory clause for unit testing",
        "policy_text": "synthetic policy clause for unit testing",
        "pair_source": source,
        "annotator_ids": sorted(labels),
        "annotator_labels": labels,
        "adjudicated_label": label,
        "adjudication_status": "adjudicated",
    }


class EvaluationTests(unittest.TestCase):
    def test_classification_metrics_perfect_predictions(self):
        gold = {"a": "CONFLICT", "b": "NOT_RELATED"}
        result = classification_metrics(gold, gold.copy())
        self.assertEqual(result["accuracy"], 1.0)
        self.assertEqual(result["macro_f1"], 0.4)  # Fixed five-label taxonomy, zero-support labels score zero.
        self.assertEqual(result["per_class"]["CONFLICT"]["f1"], 1.0)
        self.assertEqual(result["confusion_matrix"]["rows_are_gold_columns_are_prediction"]["NOT_RELATED"]["NOT_RELATED"], 1)

    def test_missing_and_unknown_predictions_are_reported(self):
        result = classification_metrics(
            {"a": "COMPLIANT", "b": "NOT_RELATED"},
            {"a": "COMPLIANT", "extra": "CONFLICT"},
        )
        self.assertEqual(result["prediction_coverage"], 0.5)
        self.assertEqual(result["missing_prediction_count"], 1)
        self.assertEqual(result["unknown_prediction_count"], 1)
        self.assertEqual(result["accuracy"], 1.0)

    def test_cohen_kappa_perfect_and_chance_agreement(self):
        perfect = cohen_kappa(["CONFLICT", "NOT_RELATED"], ["CONFLICT", "NOT_RELATED"])
        self.assertEqual(perfect["cohen_kappa"], 1.0)
        chance = cohen_kappa(
            ["CONFLICT", "CONFLICT", "NOT_RELATED", "NOT_RELATED"],
            ["CONFLICT", "NOT_RELATED", "CONFLICT", "NOT_RELATED"],
        )
        self.assertEqual(chance["cohen_kappa"], 0.0)

    def test_inter_annotator_agreement_uses_pre_adjudication_labels(self):
        rows = [
            pair("a", "r1", "p1", "CONFLICT", a="CONFLICT", b="CONFLICT"),
            pair("b", "r2", "p2", "COMPLIANT", a="SUPPORTING", b="COMPLIANT"),
        ]
        report = evaluate_dataset(rows)
        agreement = report["annotator_agreement"]["pairwise_results"][0]
        self.assertEqual(agreement["n_pairs"], 2)
        self.assertEqual(agreement["observed_agreement"], 0.5)

    def test_pairwise_kappa_uses_partial_overlap(self):
        rows = [
            pair("a", "r1", "p1", "CONFLICT", a="CONFLICT", b="CONFLICT"),
            pair("b", "r2", "p2", "COMPLIANT", a="COMPLIANT"),
        ]
        result = evaluate_dataset(rows)["annotator_agreement"]["pairwise_results"][0]
        self.assertEqual(result["n_pairs"], 1)

    def test_metrics_report_does_not_copy_clause_text(self):
        row = pair("a", "r1", "p1", "CONFLICT")
        report = evaluate_dataset([row], predictions={"a": "CONFLICT"})
        rendered = json.dumps(report)
        self.assertNotIn(row["regulatory_text"], rendered)
        self.assertNotIn(row["policy_text"], rendered)

    def test_retrieval_coverage_is_separate_from_classifier_accuracy(self):
        rows = [
            pair("a", "r1", "p1", "CONFLICT"),
            pair("b", "r2", "p2", "NOT_RELATED", source="hard_negative"),
            pair("c", "r3", "p3", "SUPPORTING"),
        ]
        coverage = retrieval_coverage(rows, {("r1", "p1"), ("r3", "p3"), ("r9", "p9")})
        self.assertEqual(coverage["positive_pair_recall"], 1.0)
        self.assertAlmostEqual(coverage["all_gold_pair_recall"], 2 / 3)
        self.assertEqual(coverage["retrieved_unlabeled_candidate_count"], 1)

    def test_pending_pair_does_not_count_as_gold(self):
        row = pair("a", "r1", "p1", "CONFLICT")
        row["adjudicated_label"] = None
        row["adjudication_status"] = "pending"
        validate_gold_pair(row)
        report = evaluate_dataset([row])
        self.assertEqual(report["adjudicated_or_selected_gold_pair_count"], 0)
        self.assertEqual(report["unlabeled_pair_count"], 1)

    def test_invalid_or_duplicate_gold_pairs_are_rejected(self):
        row = pair("a", "r1", "p1", "CONFLICT")
        invalid = dict(row, adjudicated_label="MADE_UP")
        with self.assertRaises(ValueError):
            validate_gold_pair(invalid)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "outputs") as temp_dir:
            path = Path(temp_dir) / "gold.jsonl"
            path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate pair_id"):
                load_gold_pairs(path)

    def test_prediction_and_retrieval_jsonl_loading(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "outputs") as temp_dir:
            pred_path = Path(temp_dir) / "pred.jsonl"
            pred_path.write_text(json.dumps({"pair_id": "a", "predicted_label": "CONFLICT"}) + "\n", encoding="utf-8")
            self.assertEqual(load_predictions(pred_path), {"a": "CONFLICT"})
            retrieved_path = Path(temp_dir) / "retrieved.jsonl"
            retrieved_path.write_text(json.dumps({"regulatory_clause_id": "r1", "policy_clause_id": "p1", "distance": 0.4}) + "\n", encoding="utf-8")
            self.assertEqual(load_retrieved_pairs(retrieved_path), {("r1", "p1")})


if __name__ == "__main__":
    unittest.main()
