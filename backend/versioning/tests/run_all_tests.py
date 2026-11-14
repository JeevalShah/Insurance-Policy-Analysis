"""
run_all_tests.py

Test runner for Stage 1 Version-Aware Incremental Knowledge Graph Maintenance.
Executes all unit tests in backend/versioning/tests and prints a structured summary.
"""

import os
import sys
import unittest

# Ensure project root is in sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def run_stage1_tests():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    suite = unittest.defaultTestLoader.discover(
        start_dir=test_dir,
        pattern="test_*.py",
        top_level_dir=_PROJECT_ROOT
    )

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print("SENTRA ENGINE - VERSIONING TEST SUITE SUMMARY")
    print("=" * 60)
    print(f"Total Tests Run   : {result.testsRun}")
    print(f"Failures          : {len(result.failures)}")
    print(f"Errors            : {len(result.errors)}")
    print(f"Skipped           : {len(result.skipped)}")
    print(f"Success           : {result.wasSuccessful()}")
    print("=" * 60)

    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    run_stage1_tests()
