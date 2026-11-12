"""Equivalent bounded graph traversals and deterministic graph generators."""

from collections import deque


def generate_graph(size, distribution="uniform", degree=4):
    if size < 1 or distribution not in {"uniform", "hub_heavy"}:
        raise ValueError("size must be positive and distribution must be uniform or hub_heavy")
    degree = max(1, min(degree, size - 1 if size > 1 else 1))
    adjacency = {}
    hubs = list(range(min(max(2, size // 100), size)))
    for node in range(size):
        targets = set()
        offset = 1
        while len(targets) < degree:
            if distribution == "uniform" or offset == 1:
                target = (node + offset) % size
            else:
                target = hubs[(node + offset) % len(hubs)]
                if target == node or target in targets:
                    target = (node + offset) % size
            if target != node:
                targets.add(target)
            offset += 1
            if offset > size * 2:
                break
        adjacency[node] = targets
    return adjacency


def reachable_python(adjacency, start, max_depth):
    if max_depth < 1:
        return set()
    seen = {start}
    found = set()
    queue = deque([(start, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for neighbor in adjacency.get(node, ()):
            if neighbor not in seen:
                seen.add(neighbor)
                found.add(neighbor)
                queue.append((neighbor, depth + 1))
    return found


def reachable_networkx(graph, start, max_depth):
    import networkx as nx
    if max_depth < 1:
        return set()
    distances = nx.single_source_shortest_path_length(graph, start, cutoff=max_depth)
    return set(distances) - {start}


def build_networkx(adjacency):
    import networkx as nx
    graph = nx.DiGraph()
    graph.add_nodes_from(adjacency)
    graph.add_edges_from((source, target) for source, targets in adjacency.items() for target in targets)
    return graph
