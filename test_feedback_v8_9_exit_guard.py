"""V8.9 synthetic tests: visible-frame guard experiment, NOT real ARC game progress."""
import hashlib
import unittest

from test_feedback_v8_5_rotation_state import ACTIONS, GOAL, frame, p
from test_feedback_v8_8_switch_transition import observed


def fp(grid):
    return hashlib.sha256(bytes(v for row in grid for v in row)).hexdigest()[:16]


class V89VisibleExitGuardTests(unittest.TestCase):
    def _validated_aligned(self):
        planner = p.LS20VisualPlanner()
        # The unique switch must be visible before cursor occludes its glyph.
        planner.propose([frame((44, 45), pose=GOAL)], 1, ACTIONS)
        return planner

    def test_historical_evidence_is_only_3_exact_frame_hashes(self):
        self.assertEqual(p.V88_OBSERVED_RISKY_EXIT_FPS, frozenset({
            'e58c8a39094e9e8f', '70c046c20de8d462',
            '869a0f09dcb2c63c',
        }))
        self.assertTrue(all(len(x) == 16 for x in p.V88_OBSERVED_RISKY_EXIT_FPS))

    def test_exact_frame_risk_avoids_observed_bad_action(self):
        planner = self._validated_aligned()
        current = frame((49, 45), pose=GOAL)
        planner._level2_risky_exits.add((fp(current), 'ACTION1'))
        alternative = planner.propose([current], 1, ACTIONS)
        self.assertIn(alternative, ACTIONS)
        self.assertNotEqual(alternative, 'ACTION1')
        report = planner.summary()
        self.assertEqual(report['level2_exit_guard_activations'], 1)
        self.assertEqual(report['level2_exit_guard_alternatives'], 1)
        self.assertIn(report['last_reason'], {
            'v89_observed_exit_risk_safe_route',
            'v89_observed_exit_risk_exploration',
        })

    def test_unmatched_visible_frame_does_not_activate_guard(self):
        planner = self._validated_aligned()
        current = frame((49, 45), pose=GOAL)
        self.assertNotIn((fp(current), 'ACTION1'), planner._level2_risky_exits)
        self.assertIn(planner.propose([current], 1, ACTIONS), ACTIONS)
        self.assertEqual(planner.summary()['level2_exit_guard_activations'], 0)

    def test_newly_observed_alignment_loss_marks_only_that_frame_action(self):
        planner = self._validated_aligned()
        before = frame((49, 45), pose=GOAL)
        planner.record_frame_transition(
            observed(before), observed(frame((29, 40))), 'ACTION1', step_index=35)
        self.assertIn((fp(before), 'ACTION1'), planner._level2_risky_exits)
        self.assertEqual(planner.level2_exit_guard_new_risks, 1)
        self.assertNotEqual(planner.propose([before], 1, ACTIONS), 'ACTION1')
        self.assertEqual(planner.summary()['level2_switch_exit_transitions_total'], 1)

    def test_newly_observed_gameover_marks_risk_even_on_nominal_move(self):
        planner = self._validated_aligned()
        before = frame((49, 45), pose=GOAL)
        planner.record_frame_transition(
            observed(before), observed(frame((49, 40), pose=GOAL), state='GAME_OVER'),
            'ACTION1', step_index=79)
        self.assertIn((fp(before), 'ACTION1'), planner._level2_risky_exits)
        self.assertNotEqual(planner.propose([before], 1, ACTIONS), 'ACTION1')

    def test_reset_retains_observed_risk_but_clears_temporary_route(self):
        planner = self._validated_aligned()
        before = frame((49, 45), pose=GOAL)
        planner._level2_risky_exits.add((fp(before), 'ACTION1'))
        planner.reset_pending()
        self.assertIn((fp(before), 'ACTION1'), planner._level2_risky_exits)
        self.assertIsNone(planner._switch_plan)
        self.assertEqual(planner.summary()['level2_exit_guard_activations'], 0)

    def test_invalid_or_unvalidated_level_keeps_fail_closed(self):
        planner = p.LS20VisualPlanner()
        self.assertIsNone(planner.propose([frame((49,45), pose=GOAL)], 1, ACTIONS))
        self.assertEqual(planner.summary()['last_reason'], 'unvalidated_level')
        self.assertIsNone(planner.propose([[[0]]], 1, ACTIONS))
        self.assertEqual(planner.summary()['last_reason'], 'invalid_frame')
        self.assertIsNone(planner.propose([frame()], 3, ACTIONS))
        self.assertEqual(planner.summary()['last_reason'], 'unvalidated_level')
        self.assertEqual(planner.summary()['level2_exit_guard_activations'], 0)


if __name__ == '__main__':
    unittest.main()
