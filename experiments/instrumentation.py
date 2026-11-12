"""Opt-in timing hooks for the existing Flask/FAISS/Neo4j application."""

from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
import logging
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_phase: ContextVar[Optional[str]] = ContextVar("experiment_phase", default=None)
_llm_trace: ContextVar[Optional[Dict[str, int]]] = ContextVar("experiment_llm_trace", default=None)
_ollama_usage: ContextVar[Optional[Dict[str, int]]] = ContextVar("experiment_ollama_usage", default=None)


def _emit(run, stage: str, event: str, metrics: Dict[str, Any]) -> None:
    try:
        run.record(stage, event, metrics)
    except Exception:
        # Measurement must not break an upload, analysis, or chat request.
        logger.exception("Could not write experiment timing record for %s", stage)


def _wrap_timed(owner: Any, method_name: str, run, stage: str, event: str,
                extra_metrics: Optional[Callable[[tuple, dict, Any], Dict[str, Any]]] = None) -> Callable:
    original = getattr(owner, method_name)

    @wraps(original)
    def wrapped(*args, **kwargs):
        started = time.perf_counter_ns()
        failure = 0
        result = None
        try:
            result = original(*args, **kwargs)
            return result
        except Exception:
            failure = 1
            raise
        finally:
            metrics: Dict[str, Any] = {
                "duration_ns": time.perf_counter_ns() - started,
                "failure_count": failure,
                "call_count": 1,
            }
            if extra_metrics:
                try:
                    metrics.update(extra_metrics(args, kwargs, result))
                except Exception:
                    logger.exception("Could not derive safe timing fields for %s", stage)
            _emit(run, stage, event, metrics)

    setattr(owner, method_name, wrapped)
    return original


def _wrap_phase(owner: Any, method_name: str, phase: str) -> Callable:
    original = getattr(owner, method_name)

    @wraps(original)
    def wrapped(*args, **kwargs):
        token = _phase.set(phase)
        try:
            return original(*args, **kwargs)
        finally:
            _phase.reset(token)

    setattr(owner, method_name, wrapped)
    return original


def _count_first_arg(args: tuple, _kwargs: dict, _result: Any) -> Dict[str, Any]:
    return {"item_count": len(args[0]) if args and hasattr(args[0], "__len__") else 0}


def _upload_counts(args: tuple, kwargs: dict, _result: Any) -> Dict[str, Any]:
    reg = kwargs.get("reg_docs", args[1] if len(args) > 1 else [])
    policy = kwargs.get("policy_docs", args[2] if len(args) > 2 else [])
    return {"regulatory_clause_count": len(reg), "policy_clause_count": len(policy)}


def _parse_counts(args: tuple, _kwargs: dict, result: Any) -> Dict[str, Any]:
    files = args[0] if args else []
    return {"file_count": len(files), "clause_count": len(result) if result is not None else 0}


def _search_counts(_args: tuple, _kwargs: dict, result: Any) -> Dict[str, Any]:
    return {"candidate_count": len(result) if result is not None else 0}


def _vector_count(args: tuple, _kwargs: dict, result: Any) -> Dict[str, Any]:
    try:
        vectors = args[0]
        return {"vector_count": int(vectors.shape[0])}
    except Exception:
        try:
            return {"vector_count": len(result[0])}
        except Exception:
            return {"vector_count": 0}


def _install_ollama_usage_hook(ollama_module) -> None:
    if getattr(ollama_module, "_sentra_experiment_usage_hook", False):
        return
    original_chat = ollama_module.chat

    @wraps(original_chat)
    def tracked_chat(*args, **kwargs):
        token = _ollama_usage.set(None)
        try:
            response = original_chat(*args, **kwargs)
            def read_count(name):
                value = response.get(name) if isinstance(response, dict) else getattr(response, name, None)
                return int(value) if isinstance(value, (int, float)) and value >= 0 else None
            usage = {
                key: value for key, value in {
                    "prompt_tokens": read_count("prompt_eval_count"),
                    "completion_tokens": read_count("eval_count"),
                    "ollama_total_duration_ns": read_count("total_duration"),
                }.items() if value is not None
            }
            _ollama_usage.set(usage)
            return response
        finally:
            # Keep usage available to LocalOllamaClient.predict until it returns.
            if _ollama_usage.get() is None:
                _ollama_usage.reset(token)

    ollama_module.chat = tracked_chat
    ollama_module._sentra_experiment_usage_hook = True


def install_instrumentation(application, run) -> None:
    """Patch the already-constructed app objects for an opt-in benchmark run."""
    from flask import g

    run.record("instrumentation", "installed", {"hook_count": 0})
    hooks = 0

    original_parse = application.parse_files

    @wraps(original_parse)
    def timed_parse(files):
        started = time.perf_counter_ns()
        failure = 0
        result = None
        try:
            result = original_parse(files)
            return result
        except Exception:
            failure = 1
            raise
        finally:
            _emit(run, "document_parsing", "parse_complete", {
                "duration_ns": time.perf_counter_ns() - started,
                "file_count": len(files),
                "clause_count": len(result) if result is not None else 0,
                "failure_count": failure,
            })

    application.parse_files = timed_parse
    hooks += 1

    @application.app.before_request
    def experiment_request_start():
        g.experiment_request_start_ns = time.perf_counter_ns()

    @application.app.after_request
    def experiment_request_finish(response):
        started = getattr(g, "experiment_request_start_ns", None)
        if started is not None:
            status = "ok" if response.status_code < 400 else "error"
            _emit(run, "api_request", "request_complete", {
                "wall_duration_ns": time.perf_counter_ns() - started,
                "http_status": int(response.status_code),
            })
        return response

    _wrap_timed(application.pipeline_service, "process_upload", run,
                "upload_pipeline_wall", "upload_complete", _upload_counts)
    hooks += 1
    _wrap_timed(application.store, "initialize_store", run,
                "upload_vector_store_init", "init_complete", _count_first_arg)
    hooks += 1
    _wrap_timed(application.store.embedder, "embed_documents", run,
                "upload_embedding", "embedding_complete", _count_first_arg)
    hooks += 1

    pipeline = application.graph_pipeline
    _wrap_timed(pipeline.embedder, "generate_embeddings", run,
                "policy_embedding", "embedding_complete", _count_first_arg)
    _wrap_timed(pipeline.embedder, "build_index", run,
                "faiss_index_build", "index_complete", _vector_count)
    _wrap_timed(pipeline.embedder, "secure_search", run,
                "faiss_search", "search_complete", _search_counts)
    hooks += 3

    original_retrieve = pipeline._retrieve_candidates

    @wraps(original_retrieve)
    def timed_retrieve(*args, **kwargs):
        token = _phase.set("regulatory")
        try:
            return original_retrieve(*args, **kwargs)
        finally:
            _phase.reset(token)

    pipeline._retrieve_candidates = timed_retrieve

    # Replace the unscoped embed_query hook with a context-sensitive one so
    # upload embedding is not double-counted as regulatory/chat query embedding.
    original_embed_query = application.store.embedder.embed_query
    pipeline.embedder.embed_query = original_embed_query

    @wraps(original_embed_query)
    def timed_query_embedding(*args, **kwargs):
        phase = _phase.get()
        if phase not in {"regulatory", "chat"}:
            return original_embed_query(*args, **kwargs)
        started = time.perf_counter_ns()
        failure = 0
        try:
            return original_embed_query(*args, **kwargs)
        except Exception:
            failure = 1
            raise
        finally:
            _emit(run, phase + "_query_embedding", "embedding_complete", {
                "duration_ns": time.perf_counter_ns() - started,
                "failure_count": failure,
                "call_count": 1,
            })

    pipeline.embedder.embed_query = timed_query_embedding

    _wrap_timed(pipeline, "_write_regulatory_nodes", run,
                "neo4j_node_write_stage", "regulatory_nodes_complete")
    _wrap_timed(pipeline, "_write_policy_nodes", run,
                "neo4j_node_write_stage", "policy_nodes_complete")
    _wrap_timed(pipeline, "_write_dependency_edges", run,
                "neo4j_dependency_edge_write_stage", "dependency_edges_complete")
    _wrap_timed(pipeline, "_clear_session_nodes", run,
                "neo4j_session_clear", "clear_complete")
    hooks += 4
    pipeline.experiment_recorder = run

    original_process_batch = pipeline._process_batch

    @wraps(original_process_batch)
    def timed_process_batch(*args, **kwargs):
        trace = {"calls": 0, "failures": 0}
        trace_token = _llm_trace.set(trace)
        phase_token = _phase.set("classification")
        started = time.perf_counter_ns()
        failure = 0
        data = args[1] if len(args) > 1 else kwargs.get("data", {})
        try:
            return original_process_batch(*args, **kwargs)
        except Exception:
            failure = 1
            raise
        finally:
            candidates = data.get("candidates", []) if isinstance(data, dict) else []
            _emit(run, "llm_classification_task", "batch_complete", {
                "task_duration_ns": time.perf_counter_ns() - started,
                "candidate_count": len(candidates),
                "llm_request_count": trace["calls"],
                "retry_count": max(0, trace["calls"] - 1),
                "failure_count": max(failure, trace["failures"]),
            })
            _phase.reset(phase_token)
            _llm_trace.reset(trace_token)

    pipeline._process_batch = timed_process_batch
    hooks += 1

    chat = application.chat_service
    _wrap_phase(pipeline, "_classify_and_write_compliance_edges", "regulatory")
    _wrap_phase(chat, "_get_vector_context", "chat")
    _wrap_timed(chat, "_get_vector_context", run,
                "chat_vector_retrieval", "retrieval_complete", _search_counts)
    _wrap_timed(chat, "_get_graph_context", run,
                "chat_graph_retrieval", "graph_retrieval_complete", _search_counts)
    original_chat_response = chat.generate_response

    @wraps(original_chat_response)
    def timed_chat_response(*args, **kwargs):
        trace = {"calls": 0, "failures": 0}
        trace_token = _llm_trace.set(trace)
        phase_token = _phase.set("chat")
        started = time.perf_counter_ns()
        failure = 0
        try:
            return original_chat_response(*args, **kwargs)
        except Exception:
            failure = 1
            raise
        finally:
            _emit(run, "chat_response_wall", "response_complete", {
                "wall_duration_ns": time.perf_counter_ns() - started,
                "llm_request_count": trace["calls"],
                "failure_count": max(failure, trace["failures"]),
            })
            _phase.reset(phase_token)
            _llm_trace.reset(trace_token)

    chat.generate_response = timed_chat_response
    hooks += 3

    analyzers = [application.impact_analyzer, chat.impact_analyzer]
    for analyzer in analyzers:
        _wrap_timed(analyzer, "_get_direct_impacts", run,
                    "neo4j_direct_read", "query_complete", _search_counts)
        _wrap_timed(analyzer, "_get_indirect_impacts", run,
                    "neo4j_multi_hop_read", "query_complete", _search_counts)
    hooks += 4

    _install_ollama_usage_hook(application.ollama)
    client = application.llm_client
    original_predict = client.predict

    @wraps(original_predict)
    def timed_predict(*args, **kwargs):
        trace = _llm_trace.get()
        phase = _phase.get()
        if trace is not None:
            trace["calls"] += 1
            attempt = trace["calls"]
        else:
            attempt = 1
        _ollama_usage.set(None)
        started = time.perf_counter_ns()
        failure = 0
        try:
            return original_predict(*args, **kwargs)
        except Exception:
            failure = 1
            if trace is not None:
                trace["failures"] += 1
            raise
        finally:
            usage = _ollama_usage.get() or {}
            metrics: Dict[str, Any] = {
                "duration_ns": time.perf_counter_ns() - started,
                "request_count": 1,
                "retry_count": int(attempt > 1),
                "failure_count": failure,
            }
            metrics.update(usage)
            stage = "llm_classification_request" if phase == "classification" else "chat_final_llm_response"
            _emit(run, stage, "request_complete", metrics)

    client.predict = timed_predict
    hooks += 2
    _emit(run, "instrumentation", "hooks_ready", {"hook_count": hooks})
