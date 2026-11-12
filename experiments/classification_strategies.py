"""Isolated LLM strategy and content-aware cache benchmarks (Stage D)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Callable, Iterable
from urllib.request import Request, urlopen

from .infrastructure import ExperimentRun, load_config
from .evaluation import load_gold_pairs

LABELS = ("CONFLICT", "COMPLIANT", "SUPPORTING", "REDUNDANT", "NOT_RELATED")
PROMPT_VERSION = "relationship-classification-v1"
TAXONOMY_VERSION = "five-label-v1"


class ClassificationCache:
    """SQLite cache for experiments only; production code never reads it."""

    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS predictions (cache_key TEXT PRIMARY KEY, label TEXT NOT NULL, created_ns INTEGER NOT NULL)")

    @staticmethod
    def key(reg_text, policy_text, model_version, prompt_version=PROMPT_VERSION, taxonomy_version=TAXONOMY_VERSION):
        fields = [reg_text, policy_text, model_version, prompt_version, taxonomy_version]
        return hashlib.sha256(json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

    def get(self, key):
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT label FROM predictions WHERE cache_key=?", (key,)).fetchone()
            return row[0] if row else None

    def put(self, key, label):
        if label not in LABELS:
            raise ValueError("unsupported classification label")
        with contextlib.closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute("INSERT OR REPLACE INTO predictions VALUES (?, ?, ?)", (key, label, time.time_ns()))

    def close(self):
        """Clean close hook for resource management."""
        pass


def build_prompt(pairs):
    payload = [{"pair_id": str(p["pair_id"]), "regulatory_text": p["regulatory_text"], "policy_text": p["policy_text"]} for p in pairs]
    return ("Classify each regulatory/policy clause relationship. Labels: " + ", ".join(LABELS) +
            ". Return only a JSON array of objects with pair_id and predicted_label. " +
            "Use COMPLIANT when the policy meets the requirement, SUPPORTING for a compatible added control, " +
            "CONFLICT when requirements cannot both be satisfied, REDUNDANT for the same obligation, " +
            "and NOT_RELATED when there is no meaningful compliance relationship. Pairs: " +
            json.dumps(payload, ensure_ascii=False))


class OllamaClient:
    def __init__(self, model, endpoint=None, timeout=180):
        self.model = model
        self.endpoint = (endpoint or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/") + "/api/chat"
        self.timeout = timeout
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def classify(self, pairs):
        body = json.dumps({"model": self.model, "stream": False, "format": "json", "messages": [
            {"role": "user", "content": build_prompt(pairs)}]}).encode("utf-8")
        req = Request(self.endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        self.call_count += 1
        with urlopen(req, timeout=self.timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        self.prompt_tokens += int(result.get("prompt_eval_count") or 0)
        self.completion_tokens += int(result.get("eval_count") or 0)
        content = result.get("message", {}).get("content", "")
        parsed = json.loads(content)
        return parsed if isinstance(parsed, list) else [parsed]


def run_strategy(pairs, strategy, classify: Callable, workers=4, batch_size=None,
                 cache: ClassificationCache | None = None, model_version="unknown"):
    """Run one fixed input set and return ID-only predictions plus counters."""
    started = time.perf_counter_ns()
    predictions = {}
    pending = []
    for pair in pairs:
        key = cache.key(pair["regulatory_text"], pair["policy_text"], model_version) if cache else None
        cached = cache.get(key) if cache else None
        if cached:
            predictions[str(pair["pair_id"])] = cached
        else:
            pending.append(pair)
    tasks = []
    if strategy in {"sequential", "thread_parallel"}:
        tasks = [[p] for p in pending]
    elif strategy == "production_batch":
        grouped = {}
        for pair in pending:
            grouped.setdefault(pair["regulatory_clause_id"], []).append(pair)
        tasks = list(grouped.values())
    elif strategy in {"batch_5", "batch_10", "batch_20"}:
        size = batch_size or int(strategy.split("_")[1])
        tasks = [pending[i:i + size] for i in range(0, len(pending), size)]
    else:
        raise ValueError("unknown strategy: " + strategy)

    def call(task):
        for attempt in range(2):
            try:
                return classify(task), attempt
            except Exception:
                if attempt:
                    raise

    results = []
    errors = 0
    retries = 0
    if strategy == "thread_parallel":
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [pool.submit(call, task) for task in tasks]
            for future in as_completed(futures):
                try:
                    values, used_retry = future.result()
                    retries += used_retry
                    results.extend(values)
                except Exception:
                    errors += 1
    else:
        for task in tasks:
            try:
                values, used_retry = call(task)
                retries += used_retry
                results.extend(values)
            except Exception:
                errors += 1
    for value in results:
        if isinstance(value, dict) and value.get("pair_id") and value.get("predicted_label") in LABELS:
            predictions[str(value["pair_id"])] = value["predicted_label"]
            if cache:
                pair = next((p for p in pending if str(p["pair_id"]) == str(value["pair_id"])), None)
                if pair is not None:
                    cache.put(cache.key(pair["regulatory_text"], pair["policy_text"], model_version), value["predicted_label"])
    elapsed = time.perf_counter_ns() - started
    return predictions, {"wall_duration_ns": elapsed, "pair_count": len(pairs),
                         "task_count": len(tasks), "returned_prediction_count": len(predictions),
                         "cache_hit_count": len(pairs) - len(pending), "retry_count": retries,
                         "error_count": errors, "pairs_per_second": (len(pairs) * 1e9 / elapsed if elapsed else 0.0)}


def load_pairs(path):
    rows = load_gold_pairs(path)
    return [{key: row[key] for key in ("pair_id", "regulatory_clause_id", "policy_clause_id", "regulatory_text", "policy_text")} for row in rows]


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", required=True, help="Gold-pair JSONL in the documented input schema")
    parser.add_argument("--strategy", choices=("sequential", "thread_parallel", "production_batch", "batch_5", "batch_10", "batch_20"), action="append")
    parser.add_argument("--model", default=os.environ.get("CHAT_MODEL", "llama3.1"))
    parser.add_argument("--endpoint", help="Ollama base URL; defaults to OLLAMA_HOST")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cache", action="store_true", help="use the isolated experiment cache for repeated measured inputs")
    parser.add_argument("--execute", action="store_true", help="Actually call the configured Ollama model")
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("LLM calls are opt-in; add --execute after confirming the model and input set")
    pairs = load_pairs(args.pairs)
    if not pairs:
        parser.error("input contains no pairs")
    client = OllamaClient(args.model, args.endpoint)
    cache = ClassificationCache(Path(__file__).parent / "outputs" / "classification_cache.sqlite3") if args.cache else None
    strategies = args.strategy or ["sequential", "thread_parallel", "production_batch", "batch_5", "batch_10", "batch_20"]
    root = Path(__file__).resolve().parents[1]
    run = ExperimentRun(root, load_config(root))
    output = run.run_dir / "predictions"
    output.mkdir(exist_ok=True)
    (run.run_dir / "classification_config.json").write_text(json.dumps({
        "strategy_list": strategies, "model": args.model, "prompt_version": PROMPT_VERSION,
        "taxonomy_version": TAXONOMY_VERSION, "pair_count": len(pairs), "accuracy": None,
        "accuracy_status": "not_computed_without_adjudicated_labels"}, indent=2), encoding="utf-8")
    for strategy in strategies:
        before_calls = client.call_count
        before_prompt, before_completion = client.prompt_tokens, client.completion_tokens
        predictions, metrics = run_strategy(pairs, strategy, client.classify, workers=args.workers,
                                            cache=cache, model_version=args.model)
        metrics.update({"llm_request_count": client.call_count - before_calls,
                        "prompt_tokens": client.prompt_tokens - before_prompt,
                        "completion_tokens": client.completion_tokens - before_completion})
        run.record("classification_strategy", "strategy_complete", metrics, {"strategy": strategy, "backend": "ollama"})
        with (output / (strategy + ".jsonl")).open("w", encoding="utf-8") as stream:
            for pair_id, label in sorted(predictions.items()):
                stream.write(json.dumps({"pair_id": pair_id, "predicted_label": label}) + "\n")
    summary = run.finish()
    print("Run ID:", run.run_id)
    print("Output directory:", run.run_dir)
    print("Accuracy: not computed (no adjudicated labels supplied)")
    return summary


if __name__ == "__main__":
    main()
