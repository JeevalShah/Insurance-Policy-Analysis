import time
import logging
from services.graph_ingestion import IngestionReport
import config

logger = logging.getLogger("Benchmarker")

def run_benchmark(report: IngestionReport, total_reg_clauses: int, top_k_setting: int):
    """
    Compares current pipeline performance metrics against the legacy prototype baseline.
    """
    print("\n" + "="*50)
    print("🚀 PIPELINE BENCHMARK REPORT")
    print("="*50)
    
    # 1. LLM Call Efficiency
    # Legacy logic: 1 classify call + 1 reason call PER CANDIDATE per trigger
    legacy_calls_expected = total_reg_clauses * top_k_setting * 2
    actual_calls = report.llm_calls_made
    reduction = ((legacy_calls_expected - actual_calls) / legacy_calls_expected) * 100 if legacy_calls_expected else 0
    
    print(f"\n🧠 LLM Inference Optimization:")
    print(f"  - Legacy Expected Calls : {legacy_calls_expected}")
    print(f"  - Current Actual Calls  : {actual_calls}")
    print(f"  - Improvement           : {reduction:.1f}% reduction in LLM overhead")

    # 2. FAISS Retrieval & Guardrails
    print(f"\n🔍 Semantic Retrieval (FAISS):")
    print(f"  - Candidate Pairs Found : {report.candidate_pairs_found}")
    print(f"  - L2 Distance Guardrail : {config.SEARCH_DISTANCE_THRESHOLD}")
    if report.candidate_pairs_found < (total_reg_clauses * top_k_setting):
        print("  - Status: STRICT FILTERING ACTIVE (Low-confidence matches successfully dropped)")
    else:
        print("  - Status: MAX CANDIDATES RETURNED (Consider tightening SEARCH_DISTANCE_THRESHOLD)")

    # 3. Graph Dependency Scaling
    print(f"\n🕸️  Graph Complexity:")
    print(f"  - Policy Nodes          : {report.policy_clauses_written}")
    print(f"  - Dependency Edges      : {report.dependency_edges_written}")
    print(f"  - Compliance Edges      : {report.compliance_edges_written}")
    
    # 4. Processing Time
    print(f"\n⏱️  Execution Time:")
    for stage in report.stages:
        print(f"  - {stage.name.ljust(20)}: {stage.elapsed_s:.2f}s")
    print(f"  - Total Ingestion Time  : {report.total_elapsed_s:.2f}s")
    print("="*50 + "\n")

# To hook this up, simply import and call `run_benchmark(session.ingestion_report, len(session.regulation_clauses), config.SEARCH_TOP_K)` at the end of your `/api/upload` route in app.py.