"""V8.3 LS20 level-2 planning tests using SYNTHETIC rendered pixels.

These tests verify guarded action suggestions and fallbacks. They do not
prove that a real ARC game level can be completed.
"""

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANNER_PATH = ROOT / "agents" / "templates" / "ls20_visual_planner.py"


def load_planner():
    spec = importlib.util.spec_from_file_location("ls20_planner_v83_tests", PLANNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load LS20 visual planner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


planner = load_planner()
ACTIONS = ("ACTION1", "ACTION2", "ACTION3", "ACTION4")
SHAPE = ((1, 1, 1), (0, 0, 1), (1, 0, 1))


def level2_frame(*, rotation_turns=0, switch=True, goal=(14, 40)):
    """Construct an explicit synthetic frame with V8.3 level-2 landmarks."""
    grid = [[5] * 64 for _ in range(64)]

    # Player: two 12-colored rows, followed by three 9-colored rows.
    for dy in range(5):
        for dx in range(5):
            grid[40 + dy][29 + dx] = 12 if dy < 2 else 9

    # Goal symbol: visible 3x3 shape in a 5x5 pad.
    gx, gy = goal
    for dy in range(3):
        for dx in range(3):
            grid[gy + 1 + dy][gx + 1 + dx] = 9 if SHAPE[dy][dx] else 5

    # Optional rotation switch (exact rendered 0/1 pattern).
    if switch:
        sx, sy = 49, 45
        grid[sy + 1][sx + 2] = 0
        grid[sy + 2][sx + 1] = 1
        grid[sy + 2][sx + 2] = 0
        grid[sy + 2][sx + 3] = 0
        grid[sy + 3][sx + 2] = 1

    # Bottom-left HUD displays the player's 3x3 pose at 2x scale.
    pose = SHAPE
    for _ in range(rotation_turns):
        pose = planner._turn_clockwise(pose)
    for dy in range(3):
        for dx in range(3):
            for sy in range(2):
                for sx in range(2):
                    grid[55 + dy * 2 + sy][3 + dx * 2 + sx] = (
                        9 if pose[dy][dx] else 5
                    )
    return grid


class FeedbackExplorerLevel2V83Tests(unittest.TestCase):
    def test_detects_level2_visible_landmarks(self):
        grid = level2_frame()
        self.assertEqual(planner.locate_player(grid), (29, 40))
        self.assertEqual(planner.locate_goal(grid), (14, 40))
        self.assertEqual(planner.locate_rotation_switch(grid), (49, 45))

    def test_level2_pose_match_proposes_goal_route(self):
        visual = planner.LS20VisualPlanner()
        action = visual.propose([level2_frame()], 1, ACTIONS)
        self.assertEqual(action, "ACTION3")
        self.assertEqual(visual.summary()["last_reason"], "pose_matches_goal")
        self.assertEqual(visual.summary()["level2_proposed_actions"], 1)

    def test_level2_pose_mismatch_proposes_switch_route(self):
        visual = planner.LS20VisualPlanner()
        action = visual.propose([level2_frame(rotation_turns=3)], 1, ACTIONS)
        self.assertIn(action, ACTIONS)
        self.assertEqual(visual.summary()["last_reason"], "rotation_required")
        self.assertEqual(visual.summary()["level2_proposed_actions"], 1)

    def test_missing_switch_falls_back(self):
        visual = planner.LS20VisualPlanner()
        self.assertIsNone(visual.propose([level2_frame(switch=False)], 1, ACTIONS))
        self.assertEqual(visual.summary()["last_reason"], "unvalidated_level")
        self.assertEqual(visual.summary()["level2_fallbacks"], 1)

    def test_wrong_goal_location_falls_back(self):
        visual = planner.LS20VisualPlanner()
        self.assertIsNone(
            visual.propose([level2_frame(goal=(19, 40))], 1, ACTIONS)
        )
        self.assertEqual(visual.summary()["last_reason"], "unvalidated_level")

    def test_nonintegral_pixel_fails_closed(self):
        grid = level2_frame()
        grid[0][0] = 5.0
        visual = planner.LS20VisualPlanner()
        self.assertIsNone(visual.propose([grid], 1, ACTIONS))
        self.assertEqual(visual.summary()["last_reason"], "invalid_frame")

    def test_unsupported_higher_level_falls_back(self):
        visual = planner.LS20VisualPlanner()
        self.assertIsNone(visual.propose([level2_frame()], 2, ACTIONS))
        self.assertEqual(visual.summary()["last_reason"], "unvalidated_level")

    def test_reset_clears_temporary_blocked_moves(self):
        grid = level2_frame()
        visual = planner.LS20VisualPlanner()
        self.assertEqual(visual.propose([grid], 1, ACTIONS), "ACTION3")
        visual.propose([grid], 1, ACTIONS)
        self.assertEqual(visual.summary()["blocked_moves"], 1)
        visual.reset_pending()
        self.assertEqual(visual.propose([grid], 1, ACTIONS), "ACTION3")


if __name__ == "__main__":
    unittest.main()
