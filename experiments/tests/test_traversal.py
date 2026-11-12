"""Stage E traversal equivalence checks without external services."""

import unittest

from experiments.traversal import build_networkx, generate_graph, reachable_networkx, reachable_python


class TraversalTests(unittest.TestCase):
    def test_generated_graph_has_valid_edges(self):
        for distribution in ("uniform", "hub_heavy"):
            graph = generate_graph(100, distribution)
            self.assertEqual(len(graph), 100)
            self.assertTrue(all(node not in targets for node, targets in graph.items()))
            self.assertEqual(sum(map(len, graph.values())), 400)

    def test_networkx_matches_python_if_available(self):
        graph = generate_graph(100, "hub_heavy")
        try:
            nx_graph = build_networkx(graph)
        except ImportError:
            self.skipTest("NetworkX is an optional experiment dependency")
        for start in (0, 5, 50):
            for depth in range(1, 6):
                self.assertEqual(reachable_networkx(nx_graph, start, depth), reachable_python(graph, start, depth))


if __name__ == "__main__":
    unittest.main()
