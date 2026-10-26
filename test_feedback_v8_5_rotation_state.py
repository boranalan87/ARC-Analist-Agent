"""V8.5 isolated tests with SYNTHETIC pixel frames, not a real ARC score."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
# Works both at repo root (upgrade input) and ARC-AGI-3-Agents/tests (installed).
TEMPLATES = (ROOT / 'ARC-AGI-3-Agents' / 'agents' / 'templates'
             if (ROOT / 'ARC-AGI-3-Agents').exists()
             else ROOT.parent / 'agents' / 'templates')


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, TEMPLATES / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p = load('ls20_planner_v85_tests', 'ls20_visual_planner.py')
ACTIONS = ('ACTION1', 'ACTION2', 'ACTION3', 'ACTION4')
GOAL = ((1, 1, 1), (0, 0, 1), (1, 0, 1))


def frame(player=(44, 45), pose=None):
    """Minimal 64x64 synthetic pixels with observable landmarks."""
    pose = pose or p._turn_clockwise(tuple(tuple(bool(v) for v in r) for r in GOAL))
    g = [[5] * 64 for _ in range(64)]
    for dy in range(3):
        for dx in range(3):
            g[41 + dy][15 + dx] = 9 if GOAL[dy][dx] else 5
            for sy in range(2):
                for sx in range(2):
                    g[55 + 2*dy + sy][3 + 2*dx + sx] = 9 if pose[dy][dx] else 5
    # Switch at (49,45), may be occluded by player.
    g[46][51] = 0
    g[47][50] = 1
    g[47][51] = 0
    g[47][52] = 0
    g[48][51] = 1
    x, y = player
    for dy in range(5):
        for dx in range(5):
            g[y+dy][x+dx] = 12 if dy < 2 else 9
    return g


class V85RotationStateTests(unittest.TestCase):
    def test_unknown_switch_under_player_never_validates_without_prior_evidence(self):
        planner = p.LS20VisualPlanner()
        self.assertIsNone(planner.propose([frame((49,45))], 1, ACTIONS))
        self.assertEqual(planner.summary()['last_reason'], 'unvalidated_level')

    def test_validated_switch_occlusion_and_return_path(self):
        planner = p.LS20VisualPlanner()
        proposed = planner.propose([frame((44,45))], 1, ACTIONS)
        self.assertEqual(proposed, 'ACTION4')  # move onto visible switch
        exit_move = planner.propose([frame((49,45))], 1, ACTIONS)
        self.assertIn(exit_move, ACTIONS)
        self.assertEqual(planner.level2_switch_contacts, 1)
        dx, dy = p.DIRECTIONS[exit_move]
        exit_pos = (49+dx, 45+dy)
        return_move = planner.propose([frame(exit_pos)], 1, ACTIONS)
        self.assertEqual(p.DIRECTIONS[return_move], (-dx, -dy))
        self.assertGreater(planner.level2_switch_returns_proposed, 0)
        # Re-entering and visibly matching the goal is recorded as observed
        # pose change. It does NOT claim game win.
        aligned_pose = tuple(tuple(bool(v) for v in row) for row in GOAL)
        planner.propose([frame((49,45), pose=aligned_pose)], 1, ACTIONS)
        summary = planner.summary()
        self.assertEqual(summary['level2_pose_changes_observed'], 1)
        self.assertGreaterEqual(summary['level2_goal_routes_after_alignment'], 1)

    def test_stalled_switch_cycle_is_counted_and_bounded(self):
        planner = p.LS20VisualPlanner()
        planner.propose([frame((44,45))], 1, ACTIONS)  # validate landmarks
        exit_move = planner.propose([frame((49,45))], 1, ACTIONS)
        for i in range(3):
            self.assertIn(exit_move, ACTIONS)
            dx, dy = p.DIRECTIONS[exit_move]
            leave = (49+dx,45+dy)
            return_move = planner.propose([frame(leave)], 1, ACTIONS)
            self.assertEqual(p.DIRECTIONS[return_move], (-dx,-dy))
            # V8.5 immediately tries a different exit upon an unconfirmed return;
            # on the third failed cycle it must stop forcing actions.
            exit_move = planner.propose([frame((49,45))], 1, ACTIONS)
        self.assertIsNone(exit_move)
        summary = planner.summary()
        self.assertGreaterEqual(summary['level2_switch_cycles_stalled'], 3)
        self.assertGreaterEqual(summary['level2_switch_retry_exhausted'], 1)
        self.assertEqual(summary['level2_pose_changes_observed'], 0)

    def test_level_transition_clears_switch_phase(self):
        planner = p.LS20VisualPlanner()
        planner.propose([frame((44,45))], 1, ACTIONS)
        planner.propose([frame((49,45))], 1, ACTIONS)
        self.assertIsNotNone(planner._switch_plan)
        self.assertIsNone(planner.propose([frame((44,45))], 2, ACTIONS))
        self.assertIsNone(planner._switch_plan)
        self.assertEqual(planner.summary()['last_reason'], 'unvalidated_level')


if __name__ == '__main__':
    unittest.main()
