"""Run metadata and privacy-conscious result recording for experiments.

This module is deliberately independent of the production application. It uses
only the Python standard library. Raw records accept numeric metrics and a
small allowlist of short categorical metadata; clause text, prompts, secrets,
and arbitrary string payloads cannot be written through the recorder API.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.+-]{1,80}$")
_SAFE_METRIC_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_FORBIDDEN_METRIC_NAME = re.compile(
    r"(?:text|prompt(?!_tokens?)|content|document|secret|password|api.?key|raw|payload|message|uri|url)",
    re.IGNORECASE,
)
_ALLOWED_METADATA = {
    "backend": {"faiss", "networkx", "neo4j", "python", "ollama", "vllm", "local"},
    "condition": {"cold", "warm", "steady"},
    "distribution": {"uniform", "hub_heavy"},
    "status": {"ok", "error", "skipped", "failed", "not_probed", "started", "completed"},
    "strategy": {
        "sequential", "thread_parallel", "production_batch", "batch_5", "batch_10",
        "batch_20", "smoke", "dictionary_bfs", "networkx", "neo4j_cypher",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _run_command(args: Iterable[str], cwd: Path, timeout: float = 2.0) -> Optional[str]:
    try:
        result = subprocess.run(
            list(args), cwd=str(cwd), capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = (result.stdout or result.stderr).strip()
    return value[:300] if value else None


def _git_metadata(repo_root: Path) -> Dict[str, Any]:
    commit = _run_command(["git", "rev-parse", "HEAD"], repo_root)
    branch = _run_command(["git", "branch", "--show-current"], repo_root)
    status = _run_command(["git", "status", "--porcelain", "--untracked-files=all"], repo_root)
    changed_count = len(status.splitlines()) if status is not None and status else 0
    return {
        "commit": commit,
        "branch": branch or None,
        "working_tree_dirty": bool(status) if status is not None else None,
        "changed_path_count": changed_count if status is not None else None,
    }


def _package_version(distribution: str) -> Optional[str]:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _memory_bytes() -> Optional[int]:
    """Return physical memory when available, without adding a dependency."""
    if os.name == "nt":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
        except (AttributeError, OSError, TypeError):
            return None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * page_size)
    except (AttributeError, OSError, ValueError):
        return None


def _model_defaults(repo_root: Path) -> Dict[str, Optional[str]]:
    """Read only literal defaults for CHAT_MODEL and EMBED_MODEL from config.py."""
    config_path = repo_root / "backend" / "config.py"
    defaults: Dict[str, Optional[str]] = {"CHAT_MODEL": None, "EMBED_MODEL": None}
    try:
        tree = ast.parse(config_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return defaults
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        name = next((item for item in names if item in defaults), None)
        value = node.value
        if name and isinstance(value, ast.Call) and len(value.args) >= 2:
            try:
                default_value = ast.literal_eval(value.args[1])
            except (ValueError, TypeError):
                continue
            if isinstance(default_value, str):
                defaults[name] = default_value
    return defaults


def _safe_neo4j_endpoint(uri: str) -> Optional[Dict[str, Any]]:
    """Expose only scheme/host/port; never retain URI credentials or path."""
    try:
        parsed = urllib.parse.urlsplit(uri)
        return {"scheme": parsed.scheme or None, "host": parsed.hostname, "port": parsed.port}
    except (TypeError, ValueError):
        return None


def _load_backend_dotenv(repo_root: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(repo_root / "backend" / ".env", override=False)


def _probe_neo4j(repo_root: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "driver_version": _package_version("neo4j"),
        "server_version": None,
        "probe_status": "not_configured",
    }
    _load_backend_dotenv(repo_root)
    uri = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
    result["endpoint"] = _safe_neo4j_endpoint(uri)
    username = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        result["probe_status"] = "missing_credentials"
        return result
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(uri, auth=(username, password))
        try:
            database = os.environ.get("NEO4J_DATABASE")
            with driver.session(**({"database": database} if database else {})) as session:
                record = session.run(
                    "CALL dbms.components() YIELD name, versions "
                    "WHERE name = 'Neo4j Kernel' RETURN versions[0] AS version"
                ).single()
                result["server_version"] = record["version"] if record else None
                result["probe_status"] = "ok" if result["server_version"] else "no_version_returned"
        finally:
            driver.close()
    except Exception as exc:  # Do not persist exception text: it may contain connection details.
        result["probe_status"] = "error"
        result["probe_error_type"] = type(exc).__name__
    return result


def _probe_ollama(model_ids: Mapping[str, Optional[str]]) -> Dict[str, Any]:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    result: Dict[str, Any] = {
        "python_package_version": _package_version("ollama"),
        "server_version": None,
        "configured_models": {key.lower(): value for key, value in model_ids.items()},
        "models": {},
        "probe_status": "error",
    }
    try:
        request = urllib.request.Request(host + "/api/version", method="GET")
        with urllib.request.urlopen(request, timeout=2.0) as response:
            version_data = json.loads(response.read().decode("utf-8"))
        result["server_version"] = version_data.get("version")

        request = urllib.request.Request(host + "/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=2.0) as response:
            tags_data = json.loads(response.read().decode("utf-8"))
        tags = tags_data.get("models", [])
        wanted = {value for value in model_ids.values() if value}
        result["models"] = {
            item.get("name"): {
                "digest": item.get("digest"),
                "modified_at": item.get("modified_at"),
                "size_bytes": item.get("size"),
            }
            for item in tags
            if item.get("name") in wanted or item.get("model") in wanted
        }
        result["probe_status"] = "ok"
    except Exception as exc:  # Do not persist exception text or the host URL.
        result["probe_error_type"] = type(exc).__name__
    return result


def capture_environment(repo_root: Path, probe_services: bool = False) -> Dict[str, Any]:
    repo_root = repo_root.resolve()
    if probe_services:
        _load_backend_dotenv(repo_root)
    model_ids = {
        key: os.environ.get(key, default)
        for key, default in _model_defaults(repo_root).items()
    }
    metadata: Dict[str, Any] = {
        "captured_at_utc": utc_now(),
        "git": _git_metadata(repo_root),
        "host": {
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "processor": platform.processor() or None,
            "logical_cpu_count": os.cpu_count(),
            "physical_memory_bytes": _memory_bytes(),
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "packages": {
            "neo4j": _package_version("neo4j"),
            "ollama": _package_version("ollama"),
            "faiss-cpu": _package_version("faiss-cpu"),
            "numpy": _package_version("numpy"),
            "flask": _package_version("flask"),
        },
        "models": {"chat_model_id": model_ids.get("CHAT_MODEL"), "embedding_model_id": model_ids.get("EMBED_MODEL")},
        "services": {
            "probed": bool(probe_services),
            "neo4j": _probe_neo4j(repo_root) if probe_services else {
                "driver_version": _package_version("neo4j"), "server_version": None,
                "probe_status": "not_probed",
            },
            "ollama": _probe_ollama(model_ids) if probe_services else {
                "python_package_version": _package_version("ollama"), "server_version": None,
                "configured_models": {key.lower(): value for key, value in model_ids.items()},
                "models": {}, "probe_status": "not_probed",
            },
        },
    }
    return metadata


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires at least one value")
    position = (len(sorted_values) - 1) * (percentile / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])


def summarize_records(records: Iterable[Mapping[str, Any]], run_id: str) -> Dict[str, Any]:
    stage_counts: Dict[str, int] = defaultdict(int)
    numeric_values: Dict[str, Dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    record_count = 0
    first_timestamp = None
    last_timestamp = None
    for record in records:
        record_count += 1
        stage = record["stage"]
        stage_counts[stage] += 1
        first_timestamp = first_timestamp or record.get("timestamp_utc")
        last_timestamp = record.get("timestamp_utc", last_timestamp)
        for name, value in record.get("metrics", {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_values[stage][name].append(float(value))

    stage_summaries: Dict[str, Any] = {}
    for stage, metrics in sorted(numeric_values.items()):
        stage_summaries[stage] = {
            "record_count": stage_counts[stage],
            "metrics": {},
        }
        for name, values in sorted(metrics.items()):
            ordered = sorted(values)
            stage_summaries[stage]["metrics"][name] = {
                "count": len(ordered),
                "min": min(ordered),
                "mean": sum(ordered) / len(ordered),
                "p50": _percentile(ordered, 50),
                "p95": _percentile(ordered, 95),
                "p99": _percentile(ordered, 99),
                "max": max(ordered),
            }
    for stage, count in stage_counts.items():
        stage_summaries.setdefault(stage, {"record_count": count, "metrics": {}})
    return {
        "run_id": run_id,
        "generated_at_utc": utc_now(),
        "record_count": record_count,
        "first_record_at_utc": first_timestamp,
        "last_record_at_utc": last_timestamp,
        "stages": dict(sorted(stage_summaries.items())),
        "interpretation": "Descriptive statistics only; this file makes no performance-improvement claim.",
    }


class ExperimentRun:
    """One uniquely named experiment run with JSONL, CSV, and summary outputs."""

    def __init__(
        self,
        repo_root: Path,
        config: Mapping[str, Any],
        probe_services: bool = False,
        run_id: Optional[str] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.config = dict(config)
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        if not _SAFE_IDENTIFIER.fullmatch(self.run_id):
            raise ValueError("run_id may contain only safe identifier characters")
        configured_output_root = Path(str(self.config.get("output_root", "experiments/outputs")))
        output_root = (self.repo_root / configured_output_root).resolve()
        if not output_root.is_relative_to(self.repo_root):
            raise ValueError("output_root must resolve to a directory inside the repository")
        self.run_dir = output_root / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.raw_jsonl_path = self.run_dir / "raw.jsonl"
        self.raw_csv_path = self.run_dir / "raw.csv"
        self.metadata_path = self.run_dir / "environment.json"
        self.summary_path = self.run_dir / "summary.json"
        self.csv_enabled = bool(self.config.get("csv_enabled", True))
        probe_services = bool(probe_services or self.config.get("probe_services_by_default", False))
        self._closed = False
        self._record_lock = threading.RLock()
        metadata = capture_environment(self.repo_root, probe_services=probe_services)
        metadata["run_id"] = self.run_id
        metadata["experiment_name"] = self._safe_identifier(
            str(self.config.get("experiment_name", "experiment")), "experiment_name"
        )
        metadata["service_probes_enabled"] = bool(probe_services)
        metadata["run_config"] = {
            "experiment_name": metadata["experiment_name"],
            "csv_enabled": self.csv_enabled,
            "probe_services_by_default": bool(self.config.get("probe_services_by_default", False)),
            "output_root": configured_output_root.as_posix(),
        }
        metadata["config_sha256"] = hashlib.sha256(
            json.dumps(dict(self.config), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.metadata = metadata
        self.metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.raw_jsonl_path.touch(exist_ok=False)

    @staticmethod
    def _safe_identifier(value: str, field: str) -> str:
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError(f"{field} must be a short safe identifier, not free text")
        return value

    def record(
        self,
        stage: str,
        event: str,
        metrics: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self._closed:
            raise RuntimeError("cannot write to a finished experiment run")
        stage = self._safe_identifier(stage, "stage")
        event = self._safe_identifier(event, "event")
        clean_metrics: Dict[str, Any] = {}
        for name, value in (metrics or {}).items():
            if not isinstance(name, str) or not _SAFE_METRIC_NAME.fullmatch(name) or _FORBIDDEN_METRIC_NAME.search(name):
                raise ValueError(f"unsafe metric name rejected: {name!r}")
            if isinstance(value, bool):
                clean_metrics[name] = value
            elif isinstance(value, (int, float)) and math.isfinite(float(value)):
                clean_metrics[name] = value
            else:
                raise ValueError(f"metric {name!r} must be a finite number or boolean")
        clean_metadata: Dict[str, str] = {}
        for name, value in (metadata or {}).items():
            allowed_values = _ALLOWED_METADATA.get(name)
            if allowed_values is None:
                raise ValueError(f"metadata field is not allowlisted: {name!r}")
            if not isinstance(value, str) or value not in allowed_values:
                raise ValueError(f"metadata {name!r} must be one of the documented categorical values")
            clean_metadata[name] = value
        record = {
            "run_id": self.run_id,
            "timestamp_utc": utc_now(),
            "stage": stage,
            "event": event,
            "metrics": clean_metrics,
            "metadata": clean_metadata,
        }
        with self._record_lock:
            if self._closed:
                raise RuntimeError("cannot write to a finished experiment run")
            with self.raw_jsonl_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
        return record

    def finish(self) -> Dict[str, Any]:
        with self._record_lock:
            if self._closed:
                return json.loads(self.summary_path.read_text(encoding="utf-8"))
            with self.raw_jsonl_path.open("r", encoding="utf-8") as stream:
                records = [json.loads(line) for line in stream if line.strip()]
            if self.csv_enabled:
                self._write_csv(records)
            summary = summarize_records(records, self.run_id)
            self.summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._closed = True
            return summary

    def _write_csv(self, records: list[Dict[str, Any]]) -> None:
        metric_names = sorted({name for record in records for name in record["metrics"]})
        metadata_names = sorted({name for record in records for name in record["metadata"]})
        fields = ["run_id", "timestamp_utc", "stage", "event"]
        fields.extend("metric." + name for name in metric_names)
        fields.extend("metadata." + name for name in metadata_names)
        with self.raw_csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for record in records:
                row = {key: record.get(key) for key in ("run_id", "timestamp_utc", "stage", "event")}
                row.update({"metric." + name: value for name, value in record["metrics"].items()})
                row.update({"metadata." + name: value for name, value in record["metadata"].items()})
                writer.writerow(row)

    def __enter__(self) -> "ExperimentRun":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not self._closed:
            self.finish()


def load_config(repo_root: Path, config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or (Path(repo_root) / "experiments" / "configs" / "default.json")
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("experiment config must be a JSON object")
    return config
