# Annotation guide: regulatory-policy relationships

## Purpose and unit of annotation

Label the substantive relationship of one **policy clause** to one
**regulatory clause**. Judge the obligations, scope, parties, conditions,
deadlines, limits, and exceptions stated in the pair. Do not infer a
relationship solely because both clauses use similar words or concern the same
general topic.

Use one label from the system's five-label taxonomy:

| Label | Use when |
|---|---|
| `CONFLICT` | The policy requirement is incompatible with the regulatory requirement in scope, amount, timing, eligibility, or another material obligation. Prefer this label when both cannot be satisfied together. |
| `COMPLIANT` | The policy clause itself satisfies the material requirement expressed by the regulatory clause, including its applicable scope and conditions. |
| `SUPPORTING` | The policy clause adds a compatible control that helps implement or evidence the regulatory requirement but does not, by itself, establish that the requirement is fully met. |
| `REDUNDANT` | The policy clause repeats the same substantive obligation without adding a distinct control or material requirement. |
| `NOT_RELATED` | There is no meaningful compliance relationship between the specific obligations in the pair, even if the wording or broad subject area overlaps. |

These labels are nominal categories; there is no numeric order between them.

## Decision order

1. Identify the exact obligation in each clause, including the responsible
   party, scope, trigger, time limit, amount, and exceptions.
2. If the two obligations cannot both be met, choose `CONFLICT`.
3. If the policy clause merely restates the same obligation without adding an
   implementation detail or distinct control, choose `REDUNDANT`.
4. Otherwise, if the policy clause operationally fulfills the regulatory
   obligation, choose `COMPLIANT`.
5. If it does not fulfill the requirement by itself but adds a compatible
   implementation or monitoring control, choose `SUPPORTING`.
6. If no substantive compliance link remains, choose `NOT_RELATED`.

If the wording is incomplete, internally inconsistent, or dependent on
unprovided context, flag it for adjudication rather than guessing. Do not
upgrade a merely related topic to `SUPPORTING`.

## Synthetic examples for guidance only

The examples below are invented to explain the taxonomy. They are **not gold
labels**, are not based on a legal review, and must not be copied into the
evaluation dataset.

### Conflict

- Regulation: “The insurer shall acknowledge a complete claim within three
  calendar days.”
- Policy: “The insurer will acknowledge a complete claim within seven calendar
  days.”
- Illustrative label: `CONFLICT` — the policy permits a later deadline for the
  same trigger and obligation.

### Compliant

- Regulation: “The insurer shall acknowledge a complete claim within three
  calendar days.”
- Policy: “A complete claim will be acknowledged within two calendar days of
  receipt.”
- Illustrative label: `COMPLIANT` — the policy meets the stated deadline for
  the same trigger.

### Supporting

- Regulation: “The insurer shall maintain a process for tracking claim
  acknowledgements.”
- Policy: “Claims staff receive quarterly training on recording and escalating
  acknowledgement failures.”
- Illustrative label: `SUPPORTING` — training helps the process operate, but the
  policy text alone does not establish that a tracking process exists.

### Redundant

- Regulation: “The insurer shall retain a record of each claim acknowledgement
  for five years.”
- Policy: “Each claim acknowledgement shall be retained for five years.”
- Illustrative label: `REDUNDANT` — the policy repeats the same retention
  obligation without adding a distinct control.

### Not related / hard negative

- Regulation: “The insurer shall report solvency information to the
  regulator.”
- Policy: “Marketing materials shall use the approved brand colours.”
- Illustrative label: `NOT_RELATED` — the clauses have no substantive
  compliance relationship. Similar terms or document proximity alone would
  not change the label.

## Independent annotation and adjudication

- Annotators should work independently and should not see model predictions,
  retrieval distance, or each other's labels while making the initial
  judgment.
- Record one exact taxonomy label per annotator in `annotator_labels`.
- Use the same frozen pair text for both annotators.
- Compute inter-annotator agreement before adjudication. Cohen's kappa is
  computed on pairs for which both annotators supplied labels.
- An adjudicator resolves disagreements using the guide and records the final
  value in `adjudicated_label`, changing `adjudication_status` to
  `adjudicated`.
- Preserve disagreements in `annotator_labels`; do not overwrite them with the
  adjudicated answer.

## Sampling and retrieval coverage

Include both retrieved candidates and hard negatives. A hard negative should
be plausibly similar in topic or wording but have no substantive relationship;
its final label still comes from human annotation. Keep the sampling source in
`pair_source`.

Measure retrieval coverage separately from classification quality. For each
frozen retrieval run, export the regulatory-policy ID pairs that FAISS
returned. Compare those IDs with the adjudicated gold pairs to measure what
fraction of gold positive pairs were made available to the classifier. Do not
count a missing candidate as an LLM classification error.
