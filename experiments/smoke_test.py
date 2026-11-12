"""Fast smoke test for experiment run metadata and output generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from experiments.infrastructure import ExperimentRun, load_config


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="JSON experiment config; defaults to experiments/configs/default.json")
    parser.add_argument("--probe-services", action="store_true", help="Run read-only Neo4j and Ollama version probes")
    args = parser.parse_args()

    root = _repo_root()
    config = load_config(root, args.config)
    run = ExperimentRun(root, config, probe_services=args.probe_services)
    started = time.perf_counter_ns()
    run.record(
        stage="infrastructure_smoke",
        event="recorder_check",
        metrics={"sample_count": 1, "elapsed_ns": max(1, time.perf_counter_ns() - started)},
        metadata={"backend": "local", "status": "ok", "strategy": "smoke"},
    )
    run.record(
        stage="infrastructure_smoke",
        event="summary_check",
        metrics={"sample_count": 2},
        metadata={"backend": "local", "status": "ok", "strategy": "smoke"},
    )
    try:
        run.record(
            stage="infrastructure_smoke",
            event="privacy_guard_check",
            metrics={"clause_text": "synthetic clause text must never be written"},
        )
    except ValueError:
        pass
    else:
        raise RuntimeError("recorder accepted a text-bearing metric field")
    summary = run.finish()

    expected_files = [run.metadata_path, run.raw_jsonl_path, run.raw_csv_path, run.summary_path]
    missing = [str(path.name) for path in expected_files if not path.is_file()]
    if missing:
        raise RuntimeError("smoke test output missing: " + ", ".join(missing))
    if summary.get("record_count") != 2:
        raise RuntimeError("summary did not count both smoke records")
    sample_stats = summary["stages"]["infrastructure_smoke"]["metrics"]["sample_count"]
    if sample_stats.get("p50") != 1.5:
        raise RuntimeError("summary percentile calculation failed")
    raw_records = [json.loads(line) for line in run.raw_jsonl_path.read_text(encoding="utf-8").splitlines()]
    if len(raw_records) != 2 or raw_records[0]["run_id"] != run.run_id:
        raise RuntimeError("raw JSONL records failed validation")
    if "clause text" in run.raw_jsonl_path.read_text(encoding="utf-8").lower():
        raise RuntimeError("unexpected text content found in raw output")

    print("Experiment infrastructure smoke test passed.")
    print("Run ID:", run.run_id)
    print("Output directory:", run.run_dir)
    print("Records:", summary["record_count"])
    print("Files:", ", ".join(path.name for path in expected_files))
    print("Service probe status:", run.metadata["services"]["neo4j"]["probe_status"], "/", run.metadata["services"]["ollama"]["probe_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
