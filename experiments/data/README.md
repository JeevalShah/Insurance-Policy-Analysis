# Gold pair dataset

`gold_pairs.schema.json` defines one JSON object per line for the hand-labeled
regulatory-policy pair dataset. No gold labels are included in this repository.
Create `gold_pairs.jsonl` only after annotators label and adjudicate real pairs.
The examples in `annotation_guide.md` are synthetic teaching examples; they are
not verified labels and must not be copied into evaluation data.

## Record fields

- `schema_version`: currently `1.0`.
- `pair_id`: stable, unique evaluation ID; do not use clause text as an ID.
- `regulatory_clause_id`, `policy_clause_id`: source IDs from the corpus.
- `regulatory_text`, `policy_text`: the exact clause text shown to annotators.
- `pair_source`: `retrieved_candidate`, `hard_negative`, `random_negative`, or
  `other`. This describes how the pair entered the annotation pool; it does not
  determine the label.
- `annotator_ids` and `annotator_labels`: optional independent annotations,
  keyed by annotator ID. A label is never filled by the tooling.
- `adjudicated_label`: one of the five taxonomy labels, or `null` until a human
  adjudicator resolves the pair.
- `adjudication_status`: `pending` until adjudicated; then `adjudicated`.
- `retrieval`: optional per-run retrieval fields. Prefer a separate retrieved
  pair output when comparing retrieval configurations, since retrieval status
  can change between runs.

The evaluation utility scores only records with an adjudicated label by
default. It can instead score one named annotator's labels for diagnostic use.
Unadjudicated records are excluded from accuracy and reported as unlabeled.

## Suggested annotation procedure

1. Freeze the taxonomy and annotation guide before labeling.
2. Present each pair to two annotators independently, without model output or
   the other annotator's label.
3. Have annotators assign exactly one label and mark genuinely ambiguous pairs
   for adjudication; do not silently omit them.
4. Compute Cohen's kappa on pairs with both independent labels before
   adjudication.
5. Adjudicate disagreements and save the resolved `adjudicated_label`.
6. Freeze the dataset and its version before running classifier comparisons.

This file contains the format and process only. It does not contain or imply
human-verified labels.
