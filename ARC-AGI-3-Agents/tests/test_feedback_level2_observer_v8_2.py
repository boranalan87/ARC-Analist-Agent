"""V8.2 phase-1 read-only level-2 observation regression tests.

These synthetic fixtures test contracts only; they are NOT evidence of success
on actual LS20 level-2 pixels or of any improvement in game score.
"""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

# Load the dependency-free planner without importing agents/__init__.py,
# which requires the full optional ARC/game/LLM dependency stack.
ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "agents" / "templates"
PACKAGE = "_feedback_v82_observer_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(TEMPLATES)]
sys.modules[PACKAGE] = package
spec = importlib.util.spec_from_file_location(
    f"{PACKAGE}.ls20_level2_observer", TEMPLATES / "ls20_level2_observer.py"
)
assert spec is not None and spec.loader is not None
observer_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = observer_module
spec.loader.exec_module(observer_module)
inspect_visible_level2 = observer_module.inspect_visible_level2


def blank():
    return [[5 for _ in range(64)] for _ in range(64)]


def draw_player(grid, x=34, y=45):
    for dy in range(5):
        for dx in range(5):
            grid[y + dy][x + dx] = 12 if dy < 2 else 9


def draw_goal(grid, x=34, y=10):
    pattern = ((1, 1, 1), (0, 0, 1), (1, 0, 1))
    for dy in range(3):
        for dx in range(3):
            grid[y + dy + 1][x + dx + 1] = 9 if pattern[dy][dx] else 5
    return pattern


def draw_hud(grid, pattern):
    for y in range(3):
        for x in range(3):
            for sy in range(2):
                for sx in range(2):
                    grid[55 + y * 2 + sy][3 + x * 2 + sx] = (
                        9 if pattern[y][x] else 5
                    )


def example_frame():
    grid = blank()
    draw_player(grid)
    pattern = draw_goal(grid)
    draw_hud(grid, pattern)
    return grid


class Level2ObserverV82Tests(unittest.TestCase):
    def test_requires_level_2(self):
        value = inspect_visible_level2([example_frame()], level=0)
        self.assertFalse(value["validated"])
        self.assertEqual(value["reason"], "unvalidated_level")

    def test_frame_shape_must_be_valid(self):
        value = inspect_visible_level2([[[5]]], level=1)
        self.assertFalse(value["validated"])
        self.assertEqual(value["reason"], "invalid_frame")

    def test_observed_route_is_only_a_hint(self):
        value = inspect_visible_level2([example_frame()], level=1)
        self.assertTrue(value["validated"])
        self.assertEqual(value["reason"], "visible_route_to_goal")
        self.assertEqual(value["suggested_action"], "ACTION1")
        self.assertEqual(value["route_length"], 7)
        self.assertEqual(value["turns_needed"], 0)

    def test_ambiguous_goal_fails_closed(self):
        grid = example_frame()
        draw_goal(grid, 19, 20)
        value = inspect_visible_level2([grid], level=1)
        self.assertFalse(value["validated"])
        self.assertEqual(value["reason"], "player_or_goal_not_visible")
        self.assertIsNone(value["suggested_action"])

    def test_invalid_hud_fails_closed(self):
        grid = example_frame()
        grid[55][3] = 3
        value = inspect_visible_level2([grid], level=1)
        self.assertFalse(value["validated"])
        self.assertEqual(value["reason"], "pose_not_visible")

    def test_candidate_restriction_is_observed(self):
        value = inspect_visible_level2([example_frame()], level=1,
                                       candidates=("ACTION3", "ACTION4"))
        self.assertTrue(value["validated"])
        self.assertIn(value["suggested_action"], ("ACTION3", "ACTION4"))

    def test_empty_candidates_fail_closed(self):
        value = inspect_visible_level2([example_frame()], level=1,
                                       candidates=("ACTION5",))
        self.assertFalse(value["validated"])
        self.assertEqual(value["reason"], "no_supported_actions")


if __name__ == "__main__":
    unittest.main()
