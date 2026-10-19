"""Unit tests for FeedbackExplorer diagnostics."""

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "agents"
    / "templates"
    / "feedback_diagnostics.py"
)

spec = importlib.util.spec_from_file_location(
    "feedback_diagnostics", MODULE_PATH
)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)

FeedbackDiagnostics = module.FeedbackDiagnostics


class FeedbackDiagnosticsTests(unittest.TestCase):

    def test_empty_summary(self):
        d = FeedbackDiagnostics()
        self.assertEqual(d.summary()["recorded_actions"], 0)

    def test_changed_and_unchanged_frames(self):
        d = FeedbackDiagnostics()

        d.record_action("ACTION1", [[[0]]], [[[1]]], 0, 0)
        d.record_action("ACTION2", [[[1]]], [[[1]]], 0, 0)

        result = d.summary()
        self.assertEqual(result["changed_frames"], 1)
        self.assertEqual(result["unchanged_frames"], 1)

    def test_action_counts_and_unique_screens(self):
        d = FeedbackDiagnostics()

        d.record_action("ACTION1", [[[0]]], [[[1]]], 0, 0)
        d.record_action("ACTION1", [[[1]]], [[[2]]], 0, 0)

        result = d.summary()
        self.assertEqual(result["recorded_actions"], 2)
        self.assertEqual(result["actions_by_type"]["ACTION1"], 2)
        self.assertEqual(result["unique_screens"], 3)

    def test_level_progress(self):
        d = FeedbackDiagnostics()

        d.record_action("ACTION3", [[[0]]], [[[1]]], 0, 1)

        self.assertEqual(d.summary()["levels_gained"], 1)


if __name__ == "__main__":
    unittest.main()
