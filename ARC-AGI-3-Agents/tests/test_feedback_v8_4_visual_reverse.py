"""V8.4 unit tests for opt-in visual reverse routing (SYNTHETIC frames).

No claim is made about completing LS20 or improving the real ARC score.
"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "agents" / "templates"


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, TEMPLATES / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {filename}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


policy_mod = load_module("feedback_policy_v84_tests", "feedback_policy.py")
planner_mod = load_module("ls20_planner_v84_tests", "ls20_visual_planner.py")
ACTIONS = ("ACTION1", "ACTION2", "ACTION3", "ACTION4")
SHAPE = ((1, 1, 1), (0, 0, 1), (1, 0, 1))


def synthetic_level2_frame():
    """Minimal synthetic, rendered-looking frame (not live game evidence)."""
    grid = [[5] * 64 for _ in range(64)]
    # Player at (29,40); goal to its left at (14,40).
    for dy in range(5):
        for dx in range(5):
            grid[40 + dy][29 + dx] = 12 if dy < 2 else 9
    for dy in range(3):
        for dx in range(3):
            grid[41 + dy][15 + dx] = 9 if SHAPE[dy][dx] else 5
    # Level-2 rotation switch at (49,45).
    grid[46][51] = 0
    grid[47][50] = 1
    grid[47][51] = 0
    grid[47][52] = 0
    grid[48][51] = 1
    # HUD pose matches the target, so left is the visible goal route.
    for dy in range(3):
        for dx in range(3):
            for sy in range(2):
                for sx in range(2):
                    grid[55 + 2 * dy + sy][3 + 2 * dx + sx] = (
                        9 if SHAPE[dy][dx] else 5
                    )
    return grid


class VisualReverseV84Tests(unittest.TestCase):
    def test_default_reverse_heuristic_is_unchanged(self):
        policy = policy_mod.FeedbackPolicy(actions=ACTIONS, avoid_immediate_reverse=True)
        policy._last_action = "ACTION4"
        action = policy.choose("s", 1, preferred_action="ACTION3")
        self.assertNotEqual(action, "ACTION3")

    def test_explicit_visual_reverse_override_selects_left(self):
        policy = policy_mod.FeedbackPolicy(actions=ACTIONS, avoid_immediate_reverse=True)
        policy._last_action = "ACTION4"
        self.assertNotIn("ACTION3", policy._candidate_actions())
        selected = policy.choose("s", 1, preferred_action="ACTION3", allow_preferred_reverse=True)
        self.assertEqual(selected, "ACTION3")
        self.assertEqual(policy.attempts[("s", "ACTION3")], 1)

    def test_unrecognized_action_is_never_enabled(self):
        policy = policy_mod.FeedbackPolicy(actions=ACTIONS, avoid_immediate_reverse=True)
        policy._last_action = "ACTION4"
        self.assertIn(policy.choose("s", 1, preferred_action="ACTION5", allow_preferred_reverse=True), ACTIONS)

    def test_planner_can_recommend_backtracking_on_level2(self):
        planner = planner_mod.LS20VisualPlanner()
        policy = policy_mod.FeedbackPolicy(actions=ACTIONS, avoid_immediate_reverse=True)
        policy._last_action = "ACTION4"  # ACTION3 is blocked by V5 heuristic
        proposed = planner.propose([synthetic_level2_frame()], 1, policy.actions)
        self.assertEqual(proposed, "ACTION3")
        selected = policy.choose("s", 1, preferred_action=proposed, allow_preferred_reverse=True)
        planner.record_choice(proposed, selected, reverse_override=True)
        result = planner.summary()
        self.assertEqual(result["preferred_actions_applied"], 1)
        self.assertEqual(result["preferred_actions_rejected"], 0)
        self.assertEqual(result["level2_reverse_filter_overrides"], 1)

    def test_planner_reports_unaccepted_preference_separately(self):
        planner = planner_mod.LS20VisualPlanner()
        planner.record_choice("ACTION3", "ACTION4", reverse_override=False)
        result = planner.summary()
        self.assertEqual(result["preferred_actions_applied"], 0)
        self.assertEqual(result["preferred_actions_rejected"], 1)
        self.assertEqual(result["level2_reverse_filter_overrides"], 0)

    def test_unvalidated_level_never_proposes_visual_move(self):
        planner = planner_mod.LS20VisualPlanner()
        self.assertIsNone(planner.propose([synthetic_level2_frame()], 2, ACTIONS))
        self.assertEqual(planner.summary()["last_reason"], "unvalidated_level")


if __name__ == "__main__":
    unittest.main()
