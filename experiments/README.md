# Experimental evaluation infrastructure

This package is isolated from the production application and uses only the
Python standard library. It creates one directory per run under
`experiments/outputs/` containing:

- `environment.json`: UTC capture time, git commit/branch/dirty state, host
  hardware, Python and installed package versions, configured model IDs, and
  optional Neo4j/Ollama server and model digests.
- `raw.jsonl`: append-only event records with numeric measurements and short,
  allowlisted categorical metadata.
- `raw.csv`: flattened version of the raw records.
- `summary.json`: record counts and descriptive statistics (min/mean/p50/p95/
  p99/max) for numeric metrics, grouped by stage.

The recorder rejects arbitrary string payloads and metric names containing
text, prompt, document, content, or secret-related terms. Do not add uploaded
clause text, prompts, or model-generated explanations to run metadata. Model
IDs and digests are retained to make inference runs reproducible.

## Smoke test

Run from the repository root:

```powershell
python -m experiments.smoke_test
```

The smoke test creates two synthetic timing/record-count events and verifies
that all four output files can be read. It does not import the backend app,
upload documents, call Ollama, or write to Neo4j.

To also capture service versions, installed Ollama model digests, and the
Neo4j server version, use the optional read-only probes:

```powershell
python -m experiments.smoke_test --probe-services
```

The Neo4j probe executes only `CALL dbms.components()` and a read-only
version query. The Ollama probe calls `/api/version` and `/api/tags`; neither
probe sends prompts or changes service data. Credentials and endpoint URLs
are never written to metadata. If a service is unavailable or credentials
are missing, the metadata records a status and exception type without the
exception message.

## Run output

The default config is `experiments/configs/default.json`. Each invocation
uses a UTC timestamp plus a random suffix as its run ID. To record an event
from a future experiment:

```python
run.record(
    stage="faiss_search",
    event="query_complete",
    metrics={"duration_ns": 125000, "candidate_count": 4},
    metadata={"backend": "faiss", "condition": "warm"},
)
```

Metrics must be finite numbers or booleans. Metadata values must be short
identifiers from the approved categories. Arbitrary strings are rejected to
reduce the chance of writing clause text into raw performance logs.

Generated run folders are git-ignored. No experimental results are checked
in by default.

## Stage B: gold-pair evaluation

Read `data/annotation_guide.md` and `data/README.md` before creating any gold
records. The schema is `data/gold_pairs.schema.json`. No human-labeled data is
provided or synthesized by this package. The annotation guide's example pairs
are illustrative only.

Gold input is JSONL with the clause text and independent human labels. Example
shape (the values shown here are placeholders, not a labeled example):

```json
{"schema_version":"1.0","pair_id":"PAIR_ID","regulatory_clause_id":"REG_ID","policy_clause_id":"POLICY_ID","regulatory_text":"PASTE THE SOURCE CLAUSE","policy_text":"PASTE THE SOURCE CLAUSE","pair_source":"retrieved_candidate","annotator_ids":[],"annotator_labels":{},"adjudicated_label":null,"adjudication_status":"pending"}
```

After two annotators independently label the pairs and a human adjudicator
fills `adjudicated_label` and sets `adjudication_status` to `adjudicated`, run:

```powershell
python -m experiments.evaluate_classification --gold experiments/data/gold_pairs.jsonl
```

To score model predictions, provide JSONL records containing `pair_id` and
`predicted_label`:

```powershell
python -m experiments.evaluate_classification --gold experiments/data/gold_pairs.jsonl --predictions path/to/predictions.jsonl --output experiments/outputs/classification_report.json
```

To measure retrieval coverage separately, provide a JSONL file whose records
contain `regulatory_clause_id` and `policy_clause_id` for each retrieved pair:

```powershell
python -m experiments.evaluate_classification --gold experiments/data/gold_pairs.jsonl --predictions path/to/predictions.jsonl --retrieved-pairs path/to/retrieved_pairs.jsonl --output experiments/outputs/classification_report.json
```

The report includes prediction coverage and missing prediction counts,
accuracy, per-class precision/recall/F1/support, macro F1, weighted F1, a
five-class confusion matrix, pairwise Cohen's kappa for annotators with
overlapping labels, and retrieval recall. It contains aggregate metrics and
IDs only; it does not copy clause text. Unadjudicated pairs are excluded from
the default classification evaluation. Use `--label-source annotator
--annotator-id ann_a` only for a diagnostic score against one annotator's
labels; it is not the adjudicated benchmark result.

## Stage C: Pipeline latency instrumentation

To run the Flask backend with opt-in latency and token tracking hooks installed:

```powershell
python -m experiments.instrumented_app [--probe-services] [--port 5000]
```

When started through `instrumented_app`, timing hooks capture:
- Document parsing (`parse_files`)
- Ingestion pipeline wall-time and vector store initialization
- FAISS policy embedding and candidate retrieval search durations
- Neo4j node and edge writes with server consumed timings
- LLM classification requests and token counts via Ollama
- RAG chat vector and graph retrieval plus final generation wall-time

All records are written to `experiments/outputs/<run_id>/`.
When running normally via `python backend/app.py`, instrumentation is completely disabled with zero performance impact.

## Stage D: Classification strategies & caching

To evaluate different inference batching strategies on gold pairs:

```powershell
python -m experiments.classification_strategies --pairs path/to/gold_pairs.jsonl --execute [--strategy production_batch] [--cache]
```

Available strategies:
- `sequential`: 1 pair per LLM call, executed sequentially
- `thread_parallel`: 1 pair per LLM call, distributed across worker threads
- `production_batch`: batching policy candidates grouped per regulatory clause (mirrors production ingestion)
- `batch_5`, `batch_10`, `batch_20`: fixed-size pair batches

Notes:
- The `--execute` flag is strictly required to confirm generative LLM calls.
- The `--cache` flag enables the isolated SQLite experiment cache keyed on SHA-256 of regulatory text, policy text, model ID, prompt version, and taxonomy version.

## Stage E: Bounded graph traversal benchmarks

To verify traversal equivalence in-memory (no Neo4j or external services needed):

```powershell
python -m experiments.traversal_benchmark --smoke
```

To run in-memory traversal benchmarks (Python BFS and NetworkX):

```powershell
python -m experiments.traversal_benchmark --execute --sizes 100 1000 --depths 1 2 3
```

To include Neo4j, a dedicated disposable database must be provided to prevent touching production data:

```powershell
python -m experiments.traversal_benchmark --execute --neo4j --database <disposable_test_db> --acknowledge-disposable-database
```

## Running unit tests

Run all experiment suite unit tests:

```powershell
python -m unittest discover -s experiments/tests
```
