"""Run bounded traversal comparisons; no benchmark runs are implicit."""

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import statistics
import time
import tracemalloc

from .infrastructure import ExperimentRun, load_config
from .traversal import build_networkx, generate_graph, reachable_networkx, reachable_python


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction)))]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 1000, 10000])
    parser.add_argument("--max-nodes", type=int, default=10000, help="hard cap for this invocation; 1,000,000 requires explicitly setting this cap")
    parser.add_argument("--depths", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--smoke", action="store_true", help="small in-memory equivalence check only")
    parser.add_argument("--execute", action="store_true", help="run the selected traversal benchmark")
    parser.add_argument("--neo4j", action="store_true", help="include Neo4j; requires a dedicated disposable database")
    parser.add_argument("--database", help="dedicated disposable Neo4j database name")
    parser.add_argument("--acknowledge-disposable-database", action="store_true")
    args = parser.parse_args(argv)
    if args.smoke:
        adjacency = generate_graph(100, "uniform")
        expected = reachable_python(adjacency, 0, 3)
        try:
            graph = build_networkx(adjacency)
            if reachable_networkx(graph, 0, 3) != expected:
                raise RuntimeError("NetworkX result differs from Python BFS")
            print("Traversal smoke passed: Python and NetworkX results match (100 nodes, depth 3).")
        except ImportError:
            print("Traversal smoke passed for Python BFS; NetworkX is not installed and was skipped.")
        return
    if not args.execute:
        parser.error("No benchmark was run. Use --smoke for a quick check or --execute for measurements.")
    if any(n < 1 or n > args.max_nodes for n in args.sizes):
        parser.error("every selected size must be positive and no greater than --max-nodes")
    if args.repetitions < 1 or any(depth < 1 or depth > 5 for depth in args.depths):
        parser.error("repetitions must be positive and depths must be between 1 and 5")
    if args.neo4j:
        if not (args.database and args.acknowledge_disposable_database):
            parser.error("Neo4j requires --database <dedicated-db> and --acknowledge-disposable-database")
        app_db = os.environ.get("NEO4J_DATABASE", "neo4j")
        if args.database.casefold() == app_db.casefold():
            parser.error("refusing the configured application database; choose a separate disposable database")
        if not all(os.environ.get(name) for name in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")):
            parser.error("set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD for the dedicated server")
        try:
            from neo4j import GraphDatabase
        except ImportError:
            parser.error("Neo4j Python driver is unavailable; install the project's existing driver in its venv")

    root = Path(__file__).resolve().parents[1]
    run = ExperimentRun(root, load_config(root))
    methods = ["dictionary_bfs"]
    try:
        import networkx  # noqa: F401
        methods.append("networkx")
    except ImportError:
        pass
    driver = None
    if args.neo4j:
        driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]))
        methods.append("neo4j_cypher")
    (run.run_dir / "traversal_config.json").write_text(json.dumps({
        "sizes": args.sizes, "depths": args.depths, "repetitions": args.repetitions,
        "methods": methods, "distributions": ["uniform", "hub_heavy"],
        "neo4j_database": args.database if args.neo4j else None,
        "neo4j_cold_cache_claimed": False,
    }, indent=2), encoding="utf-8")

    memory_peak = 0
    try:
        for size in args.sizes:
            for distribution in ("uniform", "hub_heavy"):
                tracemalloc.start()
                end_to_end_start = time.perf_counter_ns()
                adjacency = generate_graph(size, distribution)
                edge_count = sum(map(len, adjacency.values()))
                nx_graph = build_networkx(adjacency) if "networkx" in methods else None
                if nx_graph is not None:
                    memory_peak = max(memory_peak, tracemalloc.get_traced_memory()[1])
                tracemalloc.stop()
                start = 0
                for depth in args.depths:
                    expected = reachable_python(adjacency, start, depth)
                    for method in ("dictionary_bfs", "networkx"):
                        if method == "networkx" and nx_graph is None:
                            continue
                        fn = (lambda: reachable_python(adjacency, start, depth)) if method == "dictionary_bfs" else (lambda: reachable_networkx(nx_graph, start, depth))
                        actual = fn()
                        if actual != expected:
                            raise RuntimeError(f"equivalence failed: {method}, {size}, {distribution}, depth={depth}")
                        fn()  # warmup
                        durations = []
                        for _ in range(args.repetitions):
                            t0 = time.perf_counter_ns(); fn(); durations.append(time.perf_counter_ns() - t0)
                        run.record("graph_traversal", "measurements", {
                            "node_count": size, "edge_count": edge_count, "depth": depth,
                            "reachable_node_count": len(expected), "repetition_count": len(durations),
                            "p50_ns": percentile(durations, .50), "p95_ns": percentile(durations, .95),
                            "p99_ns": percentile(durations, .99), "mean_ns": statistics.mean(durations),
                            "peak_traced_memory_bytes": memory_peak,
                        }, {"backend": "python" if method == "dictionary_bfs" else "networkx", "condition": "warm", "distribution": distribution, "strategy": method})
                    if driver is not None:
                        neo4j_traversal(driver, args.database, run.run_id, adjacency, start, depth, size, distribution, edge_count, expected, args.repetitions, run)
                elapsed = time.perf_counter_ns() - end_to_end_start
                run.record("graph_construction", "complete", {"wall_duration_ns": elapsed, "node_count": size,
                            "edge_count": edge_count, "peak_traced_memory_bytes": memory_peak},
                           {"backend": "python", "distribution": distribution})
        summary = run.finish()
        print("Run ID:", run.run_id)
        print("Output directory:", run.run_dir)
        print("Methods:", ", ".join(methods))
        print("Peak traced memory bytes:", memory_peak)
        return summary
    finally:
        if driver is not None:
            driver.close()


def neo4j_traversal(driver, database, run_id, adjacency, start, depth, size, distribution, edge_count, expected, repetitions, run):
    """Create and remove only nodes tagged by this run in the named test DB."""
    with driver.session(database=database) as session:
        session.run("UNWIND $ids AS id CREATE (:ExperimentTraversalNode {run_id:$run, id:id})", ids=list(adjacency), run=run_id).consume()
        rows = [{"source": source, "target": target} for source, targets in adjacency.items() for target in targets]
        for offset in range(0, len(rows), 5000):
            session.run("UNWIND $rows AS row MATCH (a:ExperimentTraversalNode {run_id:$run,id:row.source}) MATCH (b:ExperimentTraversalNode {run_id:$run,id:row.target}) CREATE (a)-[:BENCHMARK_EDGE {run_id:$run}]->(b)", rows=rows[offset:offset+5000], run=run_id).consume()
        query = "MATCH (s:ExperimentTraversalNode {run_id:$run,id:$start})-[*1.." + str(depth) + "]->(n:ExperimentTraversalNode {run_id:$run}) WHERE n.id <> $start RETURN DISTINCT n.id AS id"
        def fetch():
            result = session.run(query, run=run_id, start=start)
            ids = {record["id"] for record in result}
            summary = result.consume()
            server_ns = int((summary.result_available_after or 0) + (summary.result_consumed_after or 0)) * 1_000_000
            return ids, server_ns
        actual, server_ns = fetch()
        if actual != expected:
            raise RuntimeError(f"equivalence failed: neo4j_cypher, {size}, {distribution}, depth={depth}")
        fetch()
        client_ns, server_durations = [], []
        for _ in range(repetitions):
            t0 = time.perf_counter_ns(); ids, server_duration = fetch(); client_ns.append(time.perf_counter_ns() - t0); server_durations.append(server_duration)
            if ids != expected:
                raise RuntimeError("Neo4j result changed during repeated traversal")
        run.record("graph_traversal", "measurements", {
            "node_count": size, "edge_count": edge_count, "depth": depth,
            "reachable_node_count": len(expected), "repetition_count": repetitions,
            "p50_ns": percentile(client_ns, .50), "p95_ns": percentile(client_ns, .95), "p99_ns": percentile(client_ns, .99),
            "mean_ns": statistics.mean(client_ns), "neo4j_server_duration_ns": statistics.mean(server_durations),
            "neo4j_result_available_consumed_ns": server_ns,
        }, {"backend": "neo4j", "condition": "warm", "distribution": distribution, "strategy": "neo4j_cypher"})
        # Scoped cleanup only: no unlabeled or application nodes are matched.
        session.run("MATCH (n:ExperimentTraversalNode {run_id:$run}) DETACH DELETE n", run=run_id).consume()


if __name__ == "__main__":
    main()
