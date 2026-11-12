"""Stage C hook tests; no backend services are contacted."""

import unittest

from unittest.mock import MagicMock
from flask import Flask

from experiments.instrumentation import _wrap_phase, _wrap_timed, install_instrumentation


class Recorder:
    def __init__(self):
        self.events = []

    def record(self, stage, event, metrics=None, metadata=None):
        self.events.append((stage, event, metrics))


class InstrumentationTests(unittest.TestCase):
    def test_timed_wrapper_preserves_return_and_records_call(self):
        class Owner:
            def work(self, value):
                return value * 2

        owner, recorder = Owner(), Recorder()
        _wrap_timed(owner, "work", recorder, "fake_stage", "complete")
        self.assertEqual(owner.work(4), 8)
        self.assertEqual(len(recorder.events), 1)
        metrics = recorder.events[0][2]
        self.assertEqual(metrics["call_count"], 1)
        self.assertEqual(metrics["failure_count"], 0)
        self.assertGreaterEqual(metrics["duration_ns"], 0)

    def test_timed_wrapper_records_failure_and_reraises(self):
        class Owner:
            def work(self):
                raise ValueError("expected")

        owner, recorder = Owner(), Recorder()
        _wrap_timed(owner, "work", recorder, "fake_stage", "complete")
        with self.assertRaisesRegex(ValueError, "expected"):
            owner.work()
        self.assertEqual(recorder.events[0][2]["failure_count"], 1)

    def test_phase_wrapper_preserves_result(self):
        class Owner:
            def work(self, value):
                return value

        owner = Owner()
        _wrap_phase(owner, "work", "regulatory")
        self.assertEqual(owner.work("unchanged"), "unchanged")

    def test_install_instrumentation_on_mock_application(self):
        class MockApp:
            def __init__(self):
                self.app = Flask("test_mock_app")
                self.parse_files = MagicMock(return_value=[{"id": "c1", "text": "clause 1"}])
                self.pipeline_service = MagicMock()
                self.store = MagicMock()
                self.store.embedder = MagicMock()
                self.graph_pipeline = MagicMock()
                self.graph_pipeline.embedder = MagicMock()
                self.chat_service = MagicMock()
                self.chat_service.impact_analyzer = MagicMock()
                self.impact_analyzer = MagicMock()
                self.ollama = MagicMock()
                self.llm_client = MagicMock()

        app_obj = MockApp()
        recorder = Recorder()
        install_instrumentation(app_obj, recorder)

        # Check ready event was emitted
        hook_events = [e for e in recorder.events if e[0] == "instrumentation"]
        self.assertEqual(len(hook_events), 2)
        self.assertEqual(hook_events[1][1], "hooks_ready")
        self.assertGreater(hook_events[1][2]["hook_count"], 15)

        # Calling a hooked method records its metrics
        res = app_obj.parse_files(["doc.pdf"])
        self.assertEqual(len(res), 1)
        parse_events = [e for e in recorder.events if e[0] == "document_parsing"]
        self.assertEqual(len(parse_events), 1)
        self.assertEqual(parse_events[0][2]["file_count"], 1)
        self.assertEqual(parse_events[0][2]["clause_count"], 1)


if __name__ == "__main__":
    unittest.main()
