"""FeedbackExplorer V8 visual planning regression tests (no game engine required)."""

import ast
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / "agents" / "templates" / "ls20_visual_planner.py"
POLICY = ROOT / "agents" / "templates" / "feedback_policy.py"
EXPLORER = ROOT / "agents" / "templates" / "feedback_explorer.py"
DIAGNOSTICS = ROOT / "agents" / "templates" / "feedback_diagnostics_v2.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


planner = load("visual_planner_v8_test", PLANNER)
policy = load("policy_v8_test", POLICY)


def blank():
    return [[5 for _ in range(64)] for _ in range(64)]


def paint_player(g, x=34, y=45):
    for dy in range(5):
        for dx in range(5):
            g[y+dy][x+dx] = 12 if dy < 2 else 9


def paint_goal(g, x=34, y=10):
    pattern = ((1,1,1), (0,0,1), (1,0,1))
    for dy in range(3):
        for dx in range(3):
            g[y+dy+1][x+dx+1] = 9 if pattern[dy][dx] else 5
    return pattern


def paint_hud(g, pattern):
    for y in range(3):
        for x in range(3):
            for sy in range(2):
                for sx in range(2):
                    g[55+y*2+sy][3+x*2+sx] = 9 if pattern[y][x] else 5


def paint_rotation(g, x=19, y=30):
    g[y+1][x+2] = 0
    g[y+2][x+1] = 1
    g[y+2][x+2] = 0
    g[y+2][x+3] = 0
    g[y+3][x+2] = 1


def fixture(*, pose_turns=0, rotation=True):
    g = blank()
    paint_player(g)
    target = paint_goal(g)
    current = target
    for _ in range(pose_turns):
        current = planner._turn_clockwise(current)
    paint_hud(g, current)
    if rotation:
        paint_rotation(g)
    return g


class FeedbackExplorerV8Tests(unittest.TestCase):
    def test_pixel_frame_shape_validation(self):
        self.assertIsNone(planner.visible_grid([]))
        self.assertIsNone(planner.visible_grid([[[1]]]))
        self.assertIsNone(planner.visible_grid([[[0]*64 for _ in range(63)]]))
        self.assertIsNotNone(planner.visible_grid([blank()]))

    def test_detects_unique_observed_player_and_goal(self):
        g = fixture()
        self.assertEqual(planner.locate_player(g), (34,45))
        self.assertEqual(planner.locate_goal(g), (34,10))

    def test_goal_detection_rejects_multiple_candidates(self):
        g = fixture()
        paint_goal(g, 19,20)
        self.assertIsNone(planner.locate_goal(g))

    def test_detects_visible_rotation_switch(self):
        self.assertEqual(planner.locate_rotation_switch(fixture()), (19,30))
        self.assertIsNone(planner.locate_rotation_switch(fixture(rotation=False)))

    def test_pose_match_is_observed_not_assumed(self):
        self.assertEqual(planner.shape_rotations_needed(fixture(pose_turns=0), (34,10)), 0)
        self.assertEqual(planner.shape_rotations_needed(fixture(pose_turns=3), (34,10)), 1)

    def test_visible_goal_action_when_pose_matches(self):
        p = planner.LS20VisualPlanner()
        action = p.propose([fixture(pose_turns=0)], 0, tuple(planner.DIRECTIONS))
        self.assertEqual(action, "ACTION1")
        self.assertEqual(p.summary()["last_reason"], "pose_matches_goal")

    def test_rotation_goal_is_prioritized_over_exit(self):
        g = fixture(pose_turns=3)
        # Wall north of player forces shortest path to rotation tile leftward.
        for yy in range(40,45):
            for xx in range(34,39):
                g[yy][xx] = 4
        p = planner.LS20VisualPlanner()
        action = p.propose([g], 0, tuple(planner.DIRECTIONS))
        self.assertEqual(action, "ACTION3")
        self.assertEqual(p.summary()["last_reason"], "rotation_required")

    def test_conservative_fallback_on_ambiguous_pose(self):
        g = fixture()
        g[55][3] = 3
        p = planner.LS20VisualPlanner()
        self.assertIsNone(p.propose([g], 0, tuple(planner.DIRECTIONS)))
        self.assertEqual(p.summary()["last_reason"], "pose_not_visible")

    def test_conservative_fallback_other_levels(self):
        p = planner.LS20VisualPlanner()
        self.assertIsNone(p.propose([fixture()], 1, tuple(planner.DIRECTIONS)))
        self.assertEqual(p.summary()["last_reason"], "unvalidated_level")

    def test_observed_failed_move_becomes_blocked(self):
        g = fixture(pose_turns=0)
        p = planner.LS20VisualPlanner()
        first = p.propose([g], 0, tuple(planner.DIRECTIONS))
        self.assertEqual(first, "ACTION1")
        other = p.propose([g], 0, tuple(planner.DIRECTIONS))
        self.assertNotEqual(other, first)
        self.assertEqual(p.summary()["blocked_moves"], 1)

    def test_pref_action_keeps_policy_bookkeeping(self):
        p = policy.FeedbackPolicy(actions=("ACTION1","ACTION2"), enable_navigation=True)
        p.observe("S", 0, "NOT_FINISHED")
        self.assertEqual(p.choose("S", 0, preferred_action="ACTION2"), "ACTION2")
        self.assertEqual(p.attempts[("S", "ACTION2")], 1)
        self.assertEqual(p._pending[:2], ("S", "ACTION2"))
        p.observe("T", 0, "NOT_FINISHED")
        self.assertEqual(p.transition_counts[("S", "ACTION2")]["T"], 1)

    def test_preference_cannot_bypass_v5_reverse_protection(self):
        p = policy.FeedbackPolicy(actions=tuple(planner.DIRECTIONS), avoid_immediate_reverse=True)
        p._last_action = "ACTION1"
        p.observe("S", 0, "NOT_FINISHED")
        selected = p.choose("S", 0, preferred_action="ACTION2")
        self.assertNotEqual(selected, "ACTION2")

    def test_legacy_choose_signature_still_works(self):
        p = policy.FeedbackPolicy()
        p.observe("S", 0, "NOT_FINISHED")
        self.assertEqual(p.choose("S", 0), "ACTION1")

    def test_explorer_wires_optional_planner_and_fallback(self):
        tree = ast.parse(EXPLORER.read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "propose"]
        self.assertEqual(len(calls), 1)
        self.assertIn("_ls20_visual_planner", EXPLORER.read_text(encoding="utf-8"))
        self.assertIn("if proposed is not None:", EXPLORER.read_text(encoding="utf-8"))

    def test_legacy_telemetry_preserved_with_new_fields(self):
        source = DIAGNOSTICS.read_text(encoding="utf-8")
        self.assertIn('"policy_memory": self._memory_summary()', source)
        self.assertIn('"navigation": policy_navigation', source)
        self.assertIn('"visible_goal_planning": visible_goal', source)


if __name__ == "__main__":
    unittest.main()
