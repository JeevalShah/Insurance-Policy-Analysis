"""Evaluate predictions, annotator agreement, and candidate retrieval coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from experiments.evaluation import (
    evaluate_dataset,
    load_gold_pairs,
    load_predictions,
    load_retrieved_pairs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True, help="Hand-annotated gold JSONL file")
    parser.add_argument("--predictions", type=Path, help="JSONL with pair_id and predicted_label")
    parser.add_argument("--retrieved-pairs", type=Path, help="JSONL with regulatory_clause_id and policy_clause_id")
    parser.add_argument("--output", type=Path, help="Optional path for aggregate report JSON")
    parser.add_argument("--label-source", choices=("adjudicated", "annotator"), default="adjudicated")
    parser.add_argument("--annotator-id", help="Required with --label-source annotator")
    args = parser.parse_args()

    try:
        pairs = load_gold_pairs(args.gold)
        predictions = load_predictions(args.predictions) if args.predictions else None
        retrieved = load_retrieved_pairs(args.retrieved_pairs) if args.retrieved_pairs else None
        report = evaluate_dataset(
            pairs,
            predictions=predictions,
            retrieved_pair_keys=retrieved,
            label_source=args.label_source,
            annotator_id=args.annotator_id,
        )
        rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
