"""Standard-library metrics for gold-pair classification and retrieval."""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


LABELS: Tuple[str, ...] = (
    "CONFLICT",
    "COMPLIANT",
    "SUPPORTING",
    "REDUNDANT",
    "NOT_RELATED",
)
POSITIVE_LABELS = tuple(label for label in LABELS if label != "NOT_RELATED")
PAIR_SOURCES = {"retrieved_candidate", "hard_negative", "random_negative", "other"}
ADJUDICATION_STATUSES = {"pending", "adjudicated"}


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: each JSONL item must be an object")
            rows.append(row)
    return rows


def _require_nonempty_string(row: Mapping[str, Any], key: str, where: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: {key} must be a non-empty string")
    return value


def validate_gold_pair(row: Mapping[str, Any], where: str = "gold pair") -> None:
    required = {
        "schema_version", "pair_id", "regulatory_clause_id", "policy_clause_id",
        "regulatory_text", "policy_text", "pair_source", "annotator_labels",
        "adjudicated_label", "adjudication_status",
    }
    missing = required - set(row)
    if missing:
        raise ValueError(f"{where}: missing required fields: {', '.join(sorted(missing))}")
    extra = set(row) - (required | {"annotator_ids", "retrieval"})
    if extra:
        raise ValueError(f"{where}: unsupported fields: {', '.join(sorted(extra))}")
    if row["schema_version"] != "1.0":
        raise ValueError(f"{where}: unsupported schema_version {row['schema_version']!r}")
    for key in ("pair_id", "regulatory_clause_id", "policy_clause_id", "regulatory_text", "policy_text"):
        _require_nonempty_string(row, key, where)
    if not isinstance(row["pair_source"], str) or row["pair_source"] not in PAIR_SOURCES:
        raise ValueError(f"{where}: pair_source must be one of {sorted(PAIR_SOURCES)}")

    annotator_labels = row["annotator_labels"]
    if not isinstance(annotator_labels, dict):
        raise ValueError(f"{where}: annotator_labels must be an object")
    for annotator_id, label in annotator_labels.items():
        if not isinstance(annotator_id, str) or not annotator_id.strip():
            raise ValueError(f"{where}: annotator IDs must be non-empty strings")
        if label not in LABELS:
            raise ValueError(f"{where}: invalid label {label!r} for annotator {annotator_id!r}")

    annotator_ids = row.get("annotator_ids")
    if annotator_ids is not None:
        if not isinstance(annotator_ids, list) or any(not isinstance(item, str) or not item.strip() for item in annotator_ids):
            raise ValueError(f"{where}: annotator_ids must be an array of non-empty strings")
        if len(set(annotator_ids)) != len(annotator_ids):
            raise ValueError(f"{where}: annotator_ids must be unique")
        if set(annotator_ids) != set(annotator_labels):
            raise ValueError(f"{where}: annotator_ids must match keys in annotator_labels")

    status = row["adjudication_status"]
    if not isinstance(status, str) or status not in ADJUDICATION_STATUSES:
        raise ValueError(f"{where}: adjudication_status must be pending or adjudicated")
    adjudicated_label = row["adjudicated_label"]
    if status == "adjudicated":
        if adjudicated_label not in LABELS:
            raise ValueError(f"{where}: adjudicated records require a valid adjudicated_label")
    elif adjudicated_label is not None:
        raise ValueError(f"{where}: pending records must have adjudicated_label=null")

    retrieval = row.get("retrieval")
    if retrieval is not None:
        if not isinstance(retrieval, dict):
            raise ValueError(f"{where}: retrieval must be an object")
        extra_retrieval_fields = set(retrieval) - {"retrieved", "retrieval_rank", "faiss_distance"}
        if extra_retrieval_fields:
            raise ValueError(f"{where}: unsupported retrieval fields: {', '.join(sorted(extra_retrieval_fields))}")
        retrieved = retrieval.get("retrieved")
        if retrieved is not None and not isinstance(retrieved, bool):
            raise ValueError(f"{where}: retrieval.retrieved must be boolean or null")
        rank = retrieval.get("retrieval_rank")
        if rank is not None and (isinstance(rank, bool) or not isinstance(rank, int) or rank < 1):
            raise ValueError(f"{where}: retrieval.retrieval_rank must be a positive integer or null")
        distance = retrieval.get("faiss_distance")
        if distance is not None and (
            isinstance(distance, bool) or not isinstance(distance, (int, float))
            or not math.isfinite(float(distance)) or distance < 0
        ):
            raise ValueError(f"{where}: retrieval.faiss_distance must be a non-negative number or null")


def load_gold_pairs(path: Path) -> List[Dict[str, Any]]:
    pairs = read_jsonl(path)
    seen_pair_ids = set()
    seen_clause_pairs = set()
    for index, row in enumerate(pairs, start=1):
        where = f"{path}:record {index}"
        validate_gold_pair(row, where)
        pair_id = row["pair_id"]
        if pair_id in seen_pair_ids:
            raise ValueError(f"{where}: duplicate pair_id {pair_id!r}")
        seen_pair_ids.add(pair_id)
        key = (row["regulatory_clause_id"], row["policy_clause_id"])
        if key in seen_clause_pairs:
            raise ValueError(f"{where}: duplicate regulatory-policy clause pair {key!r}")
        seen_clause_pairs.add(key)
    return pairs


def select_gold_labels(
    pairs: Iterable[Mapping[str, Any]],
    label_source: str = "adjudicated",
    annotator_id: Optional[str] = None,
) -> Tuple[Dict[str, str], int]:
    if label_source not in {"adjudicated", "annotator"}:
        raise ValueError("label_source must be 'adjudicated' or 'annotator'")
    if label_source == "annotator" and not annotator_id:
        raise ValueError("annotator_id is required when label_source='annotator'")
    selected: Dict[str, str] = {}
    unlabeled = 0
    for pair in pairs:
        label = None
        if label_source == "adjudicated":
            if pair.get("adjudication_status") == "adjudicated":
                label = pair.get("adjudicated_label")
        else:
            label = (pair.get("annotator_labels") or {}).get(annotator_id)
        if label in LABELS:
            selected[str(pair["pair_id"])] = label
        else:
            unlabeled += 1
    return selected, unlabeled


def load_predictions(path: Path) -> Dict[str, str]:
    records = read_jsonl(path)
    predictions: Dict[str, str] = {}
    for index, row in enumerate(records, start=1):
        where = f"{path}:record {index}"
        pair_id = _require_nonempty_string(row, "pair_id", where)
        label = row.get("predicted_label")
        if label not in LABELS:
            raise ValueError(f"{where}: predicted_label must be one of {LABELS}")
        if pair_id in predictions:
            raise ValueError(f"{where}: duplicate prediction for pair_id {pair_id!r}")
        predictions[pair_id] = label
    return predictions


def classification_metrics(gold: Mapping[str, str], predictions: Mapping[str, str]) -> Dict[str, Any]:
    if not gold:
        raise ValueError("no labeled gold pairs selected")
    for pair_id, label in gold.items():
        if label not in LABELS:
            raise ValueError(f"invalid gold label {label!r} for {pair_id!r}")
    for pair_id, label in predictions.items():
        if label not in LABELS:
            raise ValueError(f"invalid predicted label {label!r} for {pair_id!r}")

    predicted_gold_ids = set(gold).intersection(predictions)
    if not predicted_gold_ids:
        raise ValueError("no predictions match the selected gold pair IDs")
    matrix = {actual: {predicted: 0 for predicted in LABELS} for actual in LABELS}
    for pair_id in predicted_gold_ids:
        matrix[gold[pair_id]][predictions[pair_id]] += 1

    per_class: Dict[str, Any] = {}
    total = len(predicted_gold_ids)
    correct = sum(matrix[label][label] for label in LABELS)
    support_total = sum(sum(matrix[label].values()) for label in LABELS)
    weighted_f1_numerator = 0.0
    f1_values = []
    for label in LABELS:
        tp = matrix[label][label]
        support = sum(matrix[label].values())
        predicted_count = sum(matrix[actual][label] for actual in LABELS)
        precision = tp / predicted_count if predicted_count else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
            "predicted_count": predicted_count,
        }
        f1_values.append(f1)
        weighted_f1_numerator += f1 * support

    return {
        "gold_pair_count": len(gold),
        "predicted_gold_pair_count": len(predicted_gold_ids),
        "prediction_coverage": len(predicted_gold_ids) / len(gold),
        "missing_prediction_count": len(set(gold) - predicted_gold_ids),
        "unknown_prediction_count": len(set(predictions) - set(gold)),
        "evaluated_pair_count": total,
        "accuracy": correct / total,
        "per_class": per_class,
        "macro_f1": sum(f1_values) / len(LABELS),
        "weighted_f1": weighted_f1_numerator / support_total if support_total else 0.0,
        "confusion_matrix": {
            "labels": list(LABELS),
            "rows_are_gold_columns_are_prediction": matrix,
        },
    }


def cohen_kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> Dict[str, Any]:
    if len(labels_a) != len(labels_b):
        raise ValueError("annotator label arrays must have equal length")
    if not labels_a:
        raise ValueError("Cohen's kappa requires at least one paired annotation")
    if any(label not in LABELS for label in list(labels_a) + list(labels_b)):
        raise ValueError("annotator labels must use the five-label taxonomy")
    n = len(labels_a)
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / n
    counts_a = {label: labels_a.count(label) for label in LABELS}
    counts_b = {label: labels_b.count(label) for label in LABELS}
    expected = sum(counts_a[label] * counts_b[label] for label in LABELS) / (n * n)
    kappa = (observed - expected) / (1.0 - expected) if expected < 1.0 else None
    return {
        "n_pairs": n,
        "observed_agreement": observed,
        "expected_agreement": expected,
        "cohen_kappa": kappa,
        "undefined_reason": "expected_agreement_is_one" if kappa is None else None,
    }


def inter_annotator_agreement(
    pairs: Iterable[Mapping[str, Any]],
    annotator_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    pair_list = list(pairs)
    available = set().union(*[
        set((pair.get("annotator_labels") or {}).keys()) for pair in pair_list
    ]) if pair_list else set()
    if annotator_ids:
        if len(annotator_ids) != 2 or annotator_ids[0] == annotator_ids[1]:
            raise ValueError("specify exactly two distinct annotator IDs")
        pairs_to_score = [(annotator_ids[0], annotator_ids[1])]
    else:
        common_ids = sorted(available)
        pairs_to_score = list(itertools.combinations(common_ids, 2))
    results = []
    for left, right in pairs_to_score:
        if left not in available or right not in available:
            raise ValueError(f"annotators {left!r} and {right!r} do not both label any common dataset records")
        left_labels, right_labels = [], []
        for pair in pair_list:
            labels = pair.get("annotator_labels") or {}
            if left in labels and right in labels:
                left_labels.append(labels[left])
                right_labels.append(labels[right])
        if not left_labels:
            raise ValueError(f"annotators {left!r} and {right!r} have no jointly labeled pairs")
        results.append({
            "annotator_a": left,
            "annotator_b": right,
            **cohen_kappa(left_labels, right_labels),
        })
    return {
        "annotated_pair_count": len(pair_list),
        "common_annotator_ids": sorted(available),
        "pairwise_results": results,
        "status": "computed" if results else "not_available_two_common_annotators_required",
    }


def _pair_key(regulatory_id: Any, policy_id: Any, where: str) -> Tuple[str, str]:
    if not isinstance(regulatory_id, (str, int)) or not str(regulatory_id).strip():
        raise ValueError(f"{where}: regulatory_clause_id must be a non-empty ID")
    if not isinstance(policy_id, (str, int)) or not str(policy_id).strip():
        raise ValueError(f"{where}: policy_clause_id must be a non-empty ID")
    return str(regulatory_id), str(policy_id)


def load_retrieved_pairs(path: Path) -> set[Tuple[str, str]]:
    records = read_jsonl(path)
    found = set()
    for index, row in enumerate(records, start=1):
        where = f"{path}:record {index}"
        found.add(_pair_key(row.get("regulatory_clause_id"), row.get("policy_clause_id"), where))
    return found


def retrieval_coverage(
    pairs: Iterable[Mapping[str, Any]],
    retrieved_pair_keys: Iterable[Tuple[str, str]],
    label_source: str = "adjudicated",
    annotator_id: Optional[str] = None,
) -> Dict[str, Any]:
    pair_list = list(pairs)
    labels_by_id, unlabeled_count = select_gold_labels(pair_list, label_source, annotator_id)
    labels_by_key = {
        (str(pair["regulatory_clause_id"]), str(pair["policy_clause_id"])): labels_by_id[str(pair["pair_id"])]
        for pair in pair_list
        if str(pair["pair_id"]) in labels_by_id
    }
    retrieved = set(retrieved_pair_keys)
    gold_keys = set(labels_by_key)
    seen = retrieved.intersection(gold_keys)
    positive_keys = {key for key, label in labels_by_key.items() if label in POSITIVE_LABELS}
    retrieved_positive = positive_keys.intersection(retrieved)
    per_label = {}
    for label in LABELS:
        label_keys = {key for key, value in labels_by_key.items() if value == label}
        per_label[label] = {
            "gold_pair_count": len(label_keys),
            "retrieved_gold_pair_count": len(label_keys.intersection(retrieved)),
            "retrieval_recall": len(label_keys.intersection(retrieved)) / len(label_keys) if label_keys else None,
        }
    return {
        "label_source": label_source,
        "labeled_gold_pair_count": len(labels_by_key),
        "unlabeled_gold_pair_count": unlabeled_count,
        "gold_positive_pair_count": len(positive_keys),
        "retrieved_candidate_count": len(retrieved),
        "retrieved_gold_pair_count": len(seen),
        "retrieved_unlabeled_candidate_count": len(retrieved - gold_keys),
        "all_gold_pair_recall": len(seen) / len(gold_keys) if gold_keys else None,
        "positive_pair_recall": len(retrieved_positive) / len(positive_keys) if positive_keys else None,
        "per_label_retrieval_recall": per_label,
        "interpretation": "Candidate coverage is measured separately from classifier metrics; unannotated retrieved pairs are not assigned relevance labels.",
    }


def evaluate_dataset(
    pairs: Sequence[Mapping[str, Any]],
    predictions: Optional[Mapping[str, str]] = None,
    retrieved_pair_keys: Optional[Iterable[Tuple[str, str]]] = None,
    label_source: str = "adjudicated",
    annotator_id: Optional[str] = None,
) -> Dict[str, Any]:
    gold, unlabeled_count = select_gold_labels(pairs, label_source, annotator_id)
    output: Dict[str, Any] = {
        "taxonomy": list(LABELS),
        "label_source": label_source,
        "adjudicated_or_selected_gold_pair_count": len(gold),
        "unlabeled_pair_count": unlabeled_count,
        "annotator_agreement": inter_annotator_agreement(pairs),
        "classification": classification_metrics(gold, predictions) if predictions is not None else None,
        "retrieval_coverage": retrieval_coverage(
            pairs, retrieved_pair_keys, label_source, annotator_id
        ) if retrieved_pair_keys is not None else None,
        "privacy": "Evaluation output contains IDs and aggregate metrics only; clause texts are not copied to the report.",
    }
    return output
