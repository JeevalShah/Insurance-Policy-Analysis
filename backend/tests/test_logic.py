import sys
import os
import json
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_ollama

# Inject fake ollama module BEFORE importing anything that does `import ollama`
sys.modules["ollama"] = fake_ollama

import numpy as np
import faiss

import config
from embeddings.embedder import PolicyEmbedder
from retrieval.semanticsearch import SemanticSearch
from reasoning.relationshipclassifier import classify_relationship_batch, NOT_RELATED_LABEL
from reasoning.impact_analysis import (
    generate_reasoning_batch, analyze_impact, analyze_trigger, PerfMetrics
)
from reasoning.dependency_graph import build_dependency_graph


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


def test_normalization():
    print("test_normalization")
    fake_ollama.reset()
    embedder = PolicyEmbedder(model_name="fake")
    clauses = [{"clause_id": "1", "text": "some text"}, {"clause_id": "2", "text": "other text"}]
    vectors, valid = embedder.generate_embeddings(clauses)
    norms = np.linalg.norm(vectors, axis=1)
    _assert(np.allclose(norms, 1.0, atol=1e-5), "policy embeddings are unit-normalized after generate_embeddings")

    qvec = embedder.embed_query("a query")
    qnorm = np.linalg.norm(np.array(qvec))
    _assert(abs(qnorm - 1.0) < 1e-5, "query embedding is unit-normalized")


def test_query_embedding_cache():
    print("test_query_embedding_cache")
    fake_ollama.reset()
    embedder = PolicyEmbedder(model_name="fake")
    embedder.embed_query("repeat me")
    embedder.embed_query("repeat me")
    embedder.embed_query("different")
    _assert(embedder.embed_call_count == 2, f"repeated query text is cached (embed_call_count=2, got {embedder.embed_call_count})")


def test_secure_search_threshold_enforced():
    print("test_secure_search_threshold_enforced")
    fake_ollama.reset()
    embedder = PolicyEmbedder(model_name="fake")
    clauses = [{"clause_id": f"c{i}", "parent_id": None, "text": f"clause {i}"} for i in range(5)]
    vectors, valid = embedder.generate_embeddings(clauses)
    index = embedder.build_index(vectors)

    # very strict threshold -> likely 0 results with random unrelated vectors
    strict_results = embedder.secure_search(index, embedder.embed_query("unrelated query"), valid, k=5, distance_threshold=0.01)
    _assert(len(strict_results) <= 5, "strict threshold does not exceed k")

    # very loose threshold -> should return up to k results
    loose_results = embedder.secure_search(index, embedder.embed_query("unrelated query 2"), valid, k=5, distance_threshold=4.0)
    _assert(len(loose_results) == 5, f"loose threshold (4.0, covers full L2^2 range) returns all k results, got {len(loose_results)}")
    _assert(len(strict_results) <= len(loose_results), "strict threshold never returns more than loose threshold")


def test_classify_batch_happy_path():
    print("test_classify_batch_happy_path")
    fake_ollama.reset()
    candidates = [
        {"clause_id": "2.1", "text": "text a"},
        {"clause_id": "3.4", "text": "text b"},
        {"clause_id": "9.1", "text": "text c"},
    ]
    fake_ollama.CHAT_RESPONSES = [json.dumps([
        {"clause_id": "2.1", "relationship": "CONFLICT"},
        {"clause_id": "3.4", "relationship": "NOT_RELATED"},
        {"clause_id": "9.1", "relationship": "COMPLIANT"},
    ])]
    labels = classify_relationship_batch("trigger text", candidates, model="fake")
    _assert(len(fake_ollama.CHAT_CALL_LOG) == 1, "exactly ONE chat call for 3 candidates (batched)")
    _assert(labels == {"2.1": "CONFLICT", "3.4": "NOT_RELATED", "9.1": "COMPLIANT"}, f"labels correctly parsed: {labels}")


def test_classify_batch_markdown_fence():
    print("test_classify_batch_markdown_fence")
    fake_ollama.reset()
    candidates = [{"clause_id": "1", "text": "t"}]
    fake_ollama.CHAT_RESPONSES = ['```json\n[{"clause_id": "1", "relationship": "REDUNDANT"}]\n```']
    labels = classify_relationship_batch("trigger", candidates, model="fake")
    _assert(labels == {"1": "REDUNDANT"}, "markdown-fenced JSON is parsed correctly")


def test_classify_batch_omitted_candidate_becomes_not_related():
    print("test_classify_batch_omitted_candidate_becomes_not_related")
    fake_ollama.reset()
    candidates = [{"clause_id": "1", "text": "t"}, {"clause_id": "2", "text": "u"}]
    fake_ollama.CHAT_RESPONSES = [json.dumps([{"clause_id": "1", "relationship": "COMPLIANT"}])]
    labels = classify_relationship_batch("trigger", candidates, model="fake")
    _assert(labels["1"] == "COMPLIANT", "present candidate classified normally")
    _assert(labels["2"] == NOT_RELATED_LABEL, "omitted candidate defaults to NOT_RELATED, not invented")


def test_classify_batch_invented_id_ignored():
    print("test_classify_batch_invented_id_ignored")
    fake_ollama.reset()
    candidates = [{"clause_id": "1", "text": "t"}]
    fake_ollama.CHAT_RESPONSES = [json.dumps([
        {"clause_id": "1", "relationship": "COMPLIANT"},
        {"clause_id": "999-INVENTED", "relationship": "CONFLICT"},
    ])]
    labels = classify_relationship_batch("trigger", candidates, model="fake")
    _assert(labels == {"1": "COMPLIANT"}, "invented clause_id from model is dropped, not trusted")


def test_classify_batch_malformed_json_falls_back():
    print("test_classify_batch_malformed_json_falls_back")
    fake_ollama.reset()
    candidates = [{"clause_id": "1", "text": "t1"}, {"clause_id": "2", "text": "t2"}]
    # First call (the batch attempt) returns garbage; then fallback does
    # per-candidate classify_relationship() calls (single-label responses).
    fake_ollama.CHAT_RESPONSES = ["not json at all {{{", "COMPLIANT", "REDUNDANT"]
    labels = classify_relationship_batch("trigger", candidates, model="fake")
    _assert(labels == {"1": "COMPLIANT", "2": "REDUNDANT"}, f"malformed batch JSON falls back to per-candidate calls: {labels}")
    _assert(len(fake_ollama.CHAT_CALL_LOG) == 3, "1 failed batch call + 2 fallback calls = 3 total")


def test_reasoning_batch_gated_zero_calls_when_no_matches():
    print("test_reasoning_batch_gated_zero_calls_when_no_matches")
    fake_ollama.reset()
    result = generate_reasoning_batch("trigger", [], model="fake")
    _assert(result == {}, "empty matched_candidates list -> empty result")
    _assert(len(fake_ollama.CHAT_CALL_LOG) == 0, "ZERO ollama calls made when there are no matched candidates")


def test_reasoning_batch_happy_path():
    print("test_reasoning_batch_happy_path")
    fake_ollama.reset()
    matched = [
        {"clause_id": "2.1", "text": "t", "relationship": "CONFLICT"},
        {"clause_id": "7.2", "text": "u", "relationship": "COMPLIANT"},
    ]
    fake_ollama.CHAT_RESPONSES = [json.dumps([
        {"clause_id": "2.1", "reasoning": "reason A"},
        {"clause_id": "7.2", "reasoning": "reason B"},
    ])]
    result = generate_reasoning_batch("trigger", matched, model="fake")
    _assert(len(fake_ollama.CHAT_CALL_LOG) == 1, "ONE call covers both matched candidates")
    _assert(result == {"2.1": "reason A", "7.2": "reason B"}, f"reasoning correctly mapped: {result}")


def test_end_to_end_call_count_reduction():
    """
    Simulates the exact scenario from the spec: N regulatory triggers, each
    retrieving up to 5 policy candidates, with a mix of matched/unmatched
    labels, and verifies the NEW call count is 1 classification + (<=1
    reasoning) call per trigger -- never 5 classify + 5 reason.
    """
    print("test_end_to_end_call_count_reduction")
    fake_ollama.reset()

    embedder = PolicyEmbedder(model_name="fake")
    policy_clauses = [{"clause_id": f"p{i}", "parent_id": None, "text": f"policy clause {i} about topic {i % 3}"} for i in range(20)]
    vectors, valid = embedder.generate_embeddings(policy_clauses)
    index = embedder.build_index(vectors)
    fake_ollama.reset()  # don't count ingestion-time embed calls in the analysis metrics

    searcher = SemanticSearch(index, valid, embedder=embedder)
    dependency_graph = build_dependency_graph(valid)

    regulation_clauses = [{"clause_id": f"r{i}", "text": f"regulatory trigger {i}"} for i in range(4)]

    # Every batch classification call returns: first 2 candidates matched
    # (different labels), rest NOT_RELATED. Every reasoning call returns
    # reasoning for exactly the matched ones.
    # Respond dynamically based on the actual candidate clause_ids present in
    # each prompt (retrieval order/membership varies per trigger since the
    # fake embeddings are random) -- always mark the first 2 listed
    # candidates as matched, the rest NOT_RELATED, then answer reasoning
    # calls for whichever 2 were actually marked matched.
    _id_re = __import__("re").compile(r"Clause ID:\s*(\S+)")

    def fake_chat_response(messages):
        prompt = messages[-1]["content"]
        ids_in_order = _id_re.findall(prompt)
        if "Relationship:" in prompt:
            # this is a reasoning-batch prompt -- ids_in_order here are the
            # already-matched candidates only
            return json.dumps([{"clause_id": cid, "reasoning": f"because {cid}"} for cid in ids_in_order])
        # classification-batch prompt
        matched, rest = ids_in_order[:2], ids_in_order[2:]
        labels = [{"clause_id": cid, "relationship": "CONFLICT" if i == 0 else "COMPLIANT"} for i, cid in enumerate(matched)]
        labels += [{"clause_id": cid, "relationship": "NOT_RELATED"} for cid in rest]
        return json.dumps(labels)

    fake_ollama.CHAT_RESPONSES = fake_chat_response

    config.ENABLE_TRIGGER_SUMMARIZATION = False  # short triggers anyway, keep it explicit
    config.LLM_MAX_CONCURRENCY = 2

    results = analyze_impact(
        regulation_clauses=regulation_clauses,
        policy_clauses=valid,
        searcher=searcher,
        top_k=5,
        distance_threshold=4.0,  # loose, so retrieval always returns 5 candidates deterministically
        chat_model="fake",
        dependency_graph=dependency_graph,
    )

    _assert(len(results) == 4, "one result per regulatory clause, order preserved")
    for i, r in enumerate(results):
        _assert(r["trigger_id"] == f"r{i}", f"result order matches input order (trigger {i})")
        _assert(len(r["direct"]) == 2, f"exactly 2 matched candidates in 'direct' for {r['trigger_id']}: {r['direct'].keys()}")
        for cid, data in r["direct"].items():
            _assert("reasoning" in data and data["reasoning"], f"reasoning present for {cid}")
            _assert(data["relationship"] in ("CONFLICT", "COMPLIANT"), f"relationship label preserved for {cid}")

    total_chat_calls = len(fake_ollama.CHAT_CALL_LOG)
    expected = 4 * 2  # 1 classify + 1 reason per trigger
    _assert(total_chat_calls == expected,
            f"4 triggers x 5 candidates x 2 old-style calls would be 40; "
            f"new architecture makes {total_chat_calls} calls (expected {expected})")
    print(f"  >>> OLD architecture would have made {4*5*2} chat calls; NEW architecture made {total_chat_calls}")


def test_zero_candidates_zero_calls():
    print("test_zero_candidates_zero_calls")
    fake_ollama.reset()
    embedder = PolicyEmbedder(model_name="fake")
    policy_clauses = [{"clause_id": "p0", "parent_id": None, "text": "policy clause"}]
    vectors, valid = embedder.generate_embeddings(policy_clauses)
    index = embedder.build_index(vectors)
    fake_ollama.reset()
    searcher = SemanticSearch(index, valid, embedder=embedder)
    metrics = PerfMetrics()

    # distance_threshold=0.0 -- essentially nothing survives (float precision aside)
    result = analyze_trigger(
        "r0", "trigger text", "trigger text", searcher, {}, top_k=5,
        distance_threshold=-1.0,  # impossible to satisfy -> guarantees zero candidates
        chat_model="fake", metrics=metrics,
    )
    _assert(result["direct"] == {}, "no candidates survive an impossible threshold")
    _assert(len(fake_ollama.CHAT_CALL_LOG) == 0, "ZERO Ollama calls when there are zero retrieval candidates")


def test_dependency_graph_reused_not_rebuilt():
    print("test_dependency_graph_reused_not_rebuilt (signature check)")
    import inspect
    sig = inspect.signature(analyze_impact)
    _assert("dependency_graph" in sig.parameters, "analyze_impact accepts a prebuilt dependency_graph")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failures = []
    for t in tests:
        try:
            t()
        except Exception as e:
            failures.append((t.__name__, e))
            print(f"  FAIL: {t.__name__}: {e}")
    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)}/{len(tests)} tests FAILED")
        for name, e in failures:
            print(f"  - {name}: {e}")
        sys.exit(1)
    else:
        print(f"All {len(tests)} tests PASSED")