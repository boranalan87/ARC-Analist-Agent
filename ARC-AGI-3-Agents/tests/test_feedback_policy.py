"""Fast offline tests: `python -m unittest discover -s tests -p test_feedback_policy.py`."""

import importlib.util
from pathlib import Path
import unittest

# Load the dependency-free policy without importing arc_agi or arcengine.
PATH = Path(__file__).resolve().parents[1] / "agents" / "templates" / "feedback_policy.py"
spec = importlib.util.spec_from_file_location("feedback_policy", PATH)
policy_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(policy_module)
FeedbackPolicy = policy_module.FeedbackPolicy
observation_key = policy_module.observation_key


class FeedbackPolicyTests(unittest.TestCase):
    def test_same_frame_has_stable_fingerprint(self):
        a = observation_key([[[0, 1], [2, 3]]], 0, "IN_PROGRESS")
        b = observation_key([[[0, 1], [2, 3]]], 0, "IN_PROGRESS")
        c = observation_key([[[0, 1], [2, 4]]], 0, "IN_PROGRESS")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_explores_other_actions_after_noop(self):
        p = FeedbackPolicy(actions=("ACTION1", "ACTION2", "ACTION3"))
        p.observe("screen-a", 0, "IN_PROGRESS")
        self.assertEqual(p.choose("screen-a", 0), "ACTION1")
        p.observe("screen-a", 0, "IN_PROGRESS")
        self.assertEqual(p.choose("screen-a", 0), "ACTION2")
        self.assertEqual(p.reward_sum[("screen-a", "ACTION1")], -2)
        p.observe("screen-a", 0, "IN_PROGRESS")
        self.assertEqual(p.choose("screen-a", 0), "ACTION3")

    def test_rewards_progress(self):
        p = FeedbackPolicy(actions=("ACTION1", "ACTION2"))
        p.observe("a", 0, "IN_PROGRESS")
        p.choose("a", 0)
        p.observe("b", 1, "IN_PROGRESS")
        self.assertGreaterEqual(p.reward_sum[("a", "ACTION1")], 20)

    def test_chooses_successful_path_after_exploring(self):
        p = FeedbackPolicy(actions=("ACTION1", "ACTION2"))
        p.observe("a", 0, "IN_PROGRESS")
        self.assertEqual(p.choose("a", 0), "ACTION1")
        p.observe("b", 0, "IN_PROGRESS")
        p.observe("a", 0, "IN_PROGRESS")
        self.assertEqual(p.choose("a", 0), "ACTION2")
        p.observe("a", 0, "IN_PROGRESS")
        # Back at a: action 1 caused a changed frame; action 2 was a no-op.
        self.assertEqual(p.choose("a", 0), "ACTION1")

    def test_pending_reset_does_not_penalize_previous_action(self):
        p = FeedbackPolicy(actions=("ACTION1", "ACTION2"))
        p.observe("a", 0, "IN_PROGRESS")
        p.choose("a", 0)
        p.clear_pending()
        p.observe("a", 0, "IN_PROGRESS")
        self.assertEqual(p.reward_sum.get(("a", "ACTION1"), 0), 0)


if __name__ == "__main__":
    unittest.main()
