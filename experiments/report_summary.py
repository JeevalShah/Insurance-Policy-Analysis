"""Formats and exports benchmark summaries into Markdown, LaTeX, and text for paper writing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def find_latest_run_dir(outputs_dir: Path) -> Path | None:
    if not outputs_dir.is_dir():
        return None
    runs = [d for d in outputs_dir.iterdir() if d.is_dir() and (d / "raw.jsonl").is_file()]
    if not runs:
        return None
    return max(runs, key=lambda d: d.stat().st_mtime)


def build_markdown_table(stages: dict) -> str:
    lines = [
        "| Pipeline Stage | Calls / Records | Median (p50) | Mean | 95th %ile (p95) | Max |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for stage, data in sorted(stages.items()):
        metrics = data.get("metrics", {})
        dur_field = next((k for k in ["duration_ns", "wall_duration_ns", "task_duration_ns"] if k in metrics), None)
        if dur_field:
            d = metrics[dur_field]
            count = d.get("count", 0)
            p50 = format_duration(d.get("p50", 0))
            mean = format_duration(d.get("mean", 0))
            p95 = format_duration(d.get("p95", 0))
            d_max = format_duration(d.get("max", 0))
            lines.append(f"| `{stage}` | {count} | {p50} | {mean} | {p95} | {d_max} |")
        else:
            lines.append(f"| `{stage}` | {data.get('record_count', 0)} | — | — | — | — |")
    return "\n".join(lines)


def build_latex_table(stages: dict, caption: str = "Pipeline Stage Latency Breakdown") -> str:
    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{{caption}}}",
        "\\label{tab:pipeline_latency}",
        "\\begin{tabular}{lrrrrr}",
        "\\toprule",
        "\\textbf{Pipeline Stage} & \\textbf{Count} & \\textbf{p50} & \\textbf{Mean} & \\textbf{p95} & \\textbf{Max} \\\\",
        "\\midrule",
    ]
    for stage, data in sorted(stages.items()):
        metrics = data.get("metrics", {})
        dur_field = next((k for k in ["duration_ns", "wall_duration_ns", "task_duration_ns"] if k in metrics), None)
        escaped_stage = stage.replace("_", "\\_")
        if dur_field:
            d = metrics[dur_field]
            count = d.get("count", 0)
            p50 = format_duration(d.get("p50", 0))
            mean = format_duration(d.get("mean", 0))
            p95 = format_duration(d.get("p95", 0))
            d_max = format_duration(d.get("max", 0))
            lines.append(f"{escaped_stage} & {count} & {p50} & {mean} & {p95} & {d_max} \\\\")
    lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ])
    return "\n".join(lines)


def format_duration(nanoseconds: float) -> str:
    if nanoseconds < 1_000:
        return f"{nanoseconds:.0f} ns"
    if nanoseconds < 1_000_000:
        return f"{nanoseconds / 1_000:.2f} us"
    if nanoseconds < 1_000_000_000:
        return f"{nanoseconds / 1_000_000:.2f} ms"
    return f"{nanoseconds / 1_000_000_000:.2f} s"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="Run directory ID or path under experiments/outputs/")
    parser.add_argument("--export", action="store_true", default=True, help="Save .md and .tex tables into the run directory")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    outputs_dir = root / "experiments" / "outputs"

    if args.run_id:
        candidate = Path(args.run_id)
        if candidate.is_dir():
            run_dir = candidate
        else:
            run_dir = outputs_dir / args.run_id
    else:
        run_dir = find_latest_run_dir(outputs_dir)

    if not run_dir or not run_dir.is_dir():
        print("No experiment run directory found under experiments/outputs/", file=sys.stderr)
        return 1

    summary_file = run_dir / "summary.json"
    env_file = run_dir / "environment.json"

    if not summary_file.is_file():
        # Generate summary if missing
        raw_file = run_dir / "raw.jsonl"
        if raw_file.is_file():
            from .infrastructure import summarize_records
            records = [json.loads(line) for line in raw_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            summary_data = summarize_records(records, run_dir.name)
            summary_file.write_text(json.dumps(summary_data, indent=2) + "\n", encoding="utf-8")
        else:
            print(f"Neither summary.json nor raw.jsonl found in {run_dir}", file=sys.stderr)
            return 1

    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    env = json.loads(env_file.read_text(encoding="utf-8")) if env_file.is_file() else {}

    print("=" * 70)
    print(f"EXPERIMENT RUN REPORT: {run_dir.name}")
    print("=" * 70)
    print(f"Directory:    {run_dir}")
    print(f"Captured:     {env.get('captured_at_utc', 'unknown')}")
    host = env.get("host", {})
    print(f"Platform:     {host.get('os', '')} {host.get('os_release', '')} ({host.get('architecture', '')}, {host.get('logical_cpu_count', '')} CPUs)")
    models = env.get("models", {})
    print(f"Models:       Chat={models.get('chat_model_id')}, Embeddings={models.get('embedding_model_id')}")
    print(f"Total events: {summary.get('record_count', 0)}")
    print("-" * 70)

    stages = summary.get("stages", {})
    md_table = build_markdown_table(stages)
    tex_table = build_latex_table(stages)

    print("\n" + md_table + "\n")

    # Token usage if available
    llm_stage = stages.get("llm_classification_request", {})
    llm_metrics = llm_stage.get("metrics", {})
    if "prompt_tokens" in llm_metrics and "completion_tokens" in llm_metrics:
        pt = llm_metrics["prompt_tokens"]
        ct = llm_metrics["completion_tokens"]
        p_total = pt["mean"] * pt["count"]
        c_total = ct["mean"] * ct["count"]
        print("-" * 70)
        print("TOKEN UTILIZATION SUMMARY:")
        print(f"• Prompt tokens:     {p_total:.0f} total (mean: {pt['mean']:.1f}/call)")
        print(f"• Completion tokens: {c_total:.0f} total (mean: {ct['mean']:.1f}/call)")
        print(f"• Total tokens:      {p_total + c_total:.0f}")
        print("-" * 70)

    if args.export:
        (run_dir / "report_table.md").write_text(md_table + "\n", encoding="utf-8")
        (run_dir / "report_table.tex").write_text(tex_table + "\n", encoding="utf-8")
        print(f"Saved LaTeX table to:    {run_dir / 'report_table.tex'}")
        print(f"Saved Markdown table to: {run_dir / 'report_table.md'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
