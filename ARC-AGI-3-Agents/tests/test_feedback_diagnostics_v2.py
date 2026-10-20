"""Offline tests of V2 action history and memory reports."""

import importlib.util
from collections import Counter
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / "agents" / "templates"
NAME = "_feedback_v2_test_package"
package = ModuleType(NAME)
package.__path__ = [str(ROOT)]
sys.modules.setdefault(NAME, package)
spec = importlib.util.spec_from_file_location(
    f"{NAME}.feedback_diagnostics_v2", ROOT / "feedback_diagnostics_v2.py"
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
FeedbackDiagnosticsV2 = module.FeedbackDiagnosticsV2


class TestFeedbackDiagnosticsV2(unittest.TestCase):
    def test_empty_v1_compatibility(self):
        result = FeedbackDiagnosticsV2().summary()
        self.assertEqual(result["recorded_actions"], 0)
        self.assertEqual(result["changed_frames"], 0)
        self.assertEqual(result["v2"]["frame_change_rate"], 0)
        self.assertIsNone(result["v2"]["policy_memory"])

    def test_outcomes_stagnation_and_progress(self):
        tracker = FeedbackDiagnosticsV2()
        tracker.record_action("ACTION1", [[[0]]], [[[0]]], 0, 0)
        tracker.record_action("ACTION1", [[[0]]], [[[0]]], 0, 0)
        tracker.record_action("ACTION2", [[[0]]], [[[1]]], 0, 0)
        tracker.record_action("ACTION3", [[[1]]], [[[2]]], 0, 1, "WIN")
        result = tracker.summary()
        v2 = result["v2"]
        self.assertEqual(result["recorded_actions"], 4)
        self.assertEqual(result["levels_gained"], 1)
        self.assertEqual(
            v2["outcomes"], {"progressed": 1, "changed": 1, "unchanged": 2}
        )
        self.assertEqual(v2["longest_unchanged_streak"], 2)
        self.assertEqual(v2["frame_change_rate"], 0.5)
        self.assertEqual(v2["action_effectiveness"]["ACTION3"]["progress_rate"], 1)
        self.assertEqual(v2["recent_actions"][-1]["after_state"], "WIN")
        self.assertNotIn("frame", v2["recent_actions"][-1])

    def test_bounded_history_retains_full_totals(self):
        tracker = FeedbackDiagnosticsV2(max_events=2)
        for _ in range(5):
            tracker.record_action("ACTION1", [[[0]]], [[[0]]], 0, 0)
        result = tracker.summary()
        self.assertEqual(result["recorded_actions"], 5)
        self.assertEqual(result["v2"]["events_retained"], 2)
        self.assertTrue(result["v2"]["history_truncated"])
        self.assertEqual(
            [item["step"] for item in result["v2"]["recent_actions"]], [4, 5]
        )

    def test_policy_memory_scope_and_reward(self):
        policy = SimpleNamespace(
            visits=Counter({"s1": 3, "s2": 1}),
            attempts=Counter({("s1", "ACTION1"): 2, ("s2", "ACTION2"): 1}),
            reward_sum={("s1", "ACTION1"): 6.0, ("s2", "ACTION2"): -2.0},
            _pending=None,
        )
        result = FeedbackDiagnosticsV2(policy=policy).summary()["v2"]["policy_memory"]
        self.assertEqual(result["scope"], "current_run")
        self.assertEqual(result["known_states"], 2)
        self.assertEqual(result["state_observations"], 4)
        self.assertEqual(result["tried_state_action_pairs"], 2)
        self.assertEqual(result["mean_reward_by_action"]["ACTION1"], 3.0)
        self.assertEqual(result["mean_reward_by_action"]["ACTION2"], -2.0)

    def test_invalid_event_limit(self):
        for size in (0, -1, 1001):
            with self.assertRaises(ValueError):
                FeedbackDiagnosticsV2(max_events=size)


if __name__ == "__main__":
    unittest.main()
