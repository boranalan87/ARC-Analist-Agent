"""FeedbackExplorer V6 regression tests without an ARC game engine.

Run from ARC-AGI-3-Agents:
python -m unittest discover -s tests -p "test_feedback_*.py" -v
"""

import ast
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "agents" / "templates" / "feedback_policy.py"
EXPLORER_PATH = ROOT / "agents" / "templates" / "feedback_explorer.py"

spec = importlib.util.spec_from_file_location("feedback_policy_v6_test", POLICY_PATH)
assert spec is not None and spec.loader is not None
policy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy_module)
observation_key = policy_module.observation_key
FeedbackPolicy = policy_module.FeedbackPolicy


def screen() -> list[list[int]]:
    return [[0 for _ in range(64)] for _ in range(64)]


def key(grid: list[list[int]], *, mask: bool = True, level: int = 0, state: str = "NOT_FINISHED") -> str:
    return observation_key([grid], level, state, mask_ls20_step_counter=mask)


class FeedbackExplorerV6Tests(unittest.TestCase):
    def test_only_step_counter_changes_are_ignored(self):
        first, second = screen(), screen()
        first[61][13] = 1
        second[61][13] = 2
        first[62][55] = 3
        second[62][55] = 4
        self.assertEqual(key(first), key(second))

    def test_default_fingerprint_still_includes_hud(self):
        first, second = screen(), screen()
        second[61][20] = 9
        self.assertNotEqual(key(first, mask=False), key(second, mask=False))
        self.assertNotEqual(
            observation_key([first], 0, "NOT_FINISHED"),
            observation_key([second], 0, "NOT_FINISHED"),
        )

    def test_gameplay_changes_remain_visible(self):
        first, second = screen(), screen()
        second[25][35] = 7
        self.assertNotEqual(key(first), key(second))

    def test_life_indicator_remains_visible(self):
        first, second = screen(), screen()
        second[61][56] = 7
        self.assertNotEqual(key(first), key(second))

    def test_other_bottom_hud_pixels_remain_visible(self):
        first, second = screen(), screen()
        second[63][20] = 1
        self.assertNotEqual(key(first), key(second))

    def test_level_progress_and_game_state_are_not_masked(self):
        grid = screen()
        self.assertNotEqual(key(grid, level=0), key(grid, level=1))
        self.assertNotEqual(key(grid, state="NOT_FINISHED"), key(grid, state="WIN"))

    def test_non_ls20_shape_keeps_original_behavior(self):
        first = [[0, 0], [0, 0]]
        second = [[0, 0], [0, 1]]
        self.assertEqual(
            key(first),
            observation_key([first], 0, "NOT_FINISHED"),
        )
        self.assertNotEqual(key(first), key(second))

    def test_masked_noop_gets_negative_reward(self):
        first, second = screen(), screen()
        first[61][17] = 1
        second[61][17] = 2
        fingerprint = key(first)
        self.assertEqual(fingerprint, key(second))
        policy = FeedbackPolicy(actions=("ACTION1", "ACTION2"))
        policy.observe(fingerprint, 0, "NOT_FINISHED")
        action = policy.choose(fingerprint, 0)
        policy.observe(key(second), 0, "NOT_FINISHED")
        self.assertEqual(policy.reward_sum[(fingerprint, action)], -2.0)

    def test_explorer_calls_use_mask_in_both_paths(self):
        tree = ast.parse(EXPLORER_PATH.read_text(encoding="utf-8"))
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "observation_key"
        ]
        self.assertEqual(len(calls), 2)
        for call in calls:
            keywords = {keyword.arg for keyword in call.keywords}
            self.assertIn("mask_ls20_step_counter", keywords)

    def test_explorer_flag_is_conditional_on_ls20(self):
        tree = ast.parse(EXPLORER_PATH.read_text(encoding="utf-8"))
        agent = next(
            item for item in tree.body
            if isinstance(item, ast.ClassDef) and item.name == "FeedbackExplorer"
        )
        init = next(
            item for item in agent.body
            if isinstance(item, ast.FunctionDef) and item.name == "__init__"
        )
        assignments = [
            node for node in ast.walk(init)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Attribute) and target.attr == "_mask_ls20_step_counter" for target in node.targets)
        ]
        self.assertEqual(len(assignments), 1)
        condition = assignments[0].value
        self.assertIsInstance(condition, ast.Compare)
        self.assertEqual(condition.comparators[0].value, "ls20-9607627b")


if __name__ == "__main__":
    unittest.main()
