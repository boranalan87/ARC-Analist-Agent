"""V9.5 stage 2: synthetic observations, NOT verified LS20 gameplay."""
import unittest
from test_feedback_v9_4_short_cycle_guard import A, ACTIONS, cycle, frame, p
from test_feedback_v8_8_switch_transition import observed


class V95RouteRecoveryTests(unittest.TestCase):
    def trapped(self, repeats=3):
        planner = p.LS20VisualPlanner()
        cycle(planner, repeats)
        # A confirmed repeated action remains; other actions were blocked.
        for action in ACTIONS:
            if action != 'ACTION4':
                planner._blocked.add((A, action))
        return planner

    def test_witnessed_repetition_requests_one_bounded_reset(self):
        planner = self.trapped()
        self.assertIsNone(planner.propose([frame(A)], 1, ACTIONS))
        self.assertTrue(planner.v90_request_reset)
        info = planner.summary()
        self.assertEqual(info['level2_v95_recovery_resets'], 1)
        self.assertEqual(info['last_reason'], 'v95_observed_short_cycle_no_route_recovery')
        self.assertEqual(info['level2_v91_dead_end_resets'], 1)

    def test_one_confirmed_cycle_is_not_enough(self):
        planner = self.trapped(repeats=2)
        planner.propose([frame(A)], 1, ACTIONS)
        self.assertFalse(planner.v90_request_reset)
        self.assertEqual(planner.summary()['level2_v95_recovery_resets'], 0)

    def test_repeated_proposals_cannot_fabricate_new_cycle_evidence(self):
        planner = self.trapped(repeats=2)
        for _ in range(12):
            planner.propose([frame(A)], 1, ACTIONS)
        self.assertEqual(planner.summary()['level2_v95_recovery_resets'], 0)

    def test_same_visible_state_is_reset_at_most_once(self):
        planner = self.trapped()
        planner.propose([frame(A)], 1, ACTIONS)
        planner.reset_pending()
        for action in ACTIONS:
            if action != 'ACTION4':
                planner._blocked.add((A, action))
        planner.propose([frame(A)], 1, ACTIONS)
        self.assertFalse(planner.v90_request_reset)
        self.assertEqual(planner.summary()['level2_v95_recovery_resets'], 1)
        self.assertGreaterEqual(planner.summary()['level2_v95_recovery_repeat_suppressed'], 1)

    def test_no_untried_approach_means_no_reset(self):
        planner = self.trapped()
        switch = p.LEVEL_2_ROTATION_SWITCH
        planner._v91_waypoints_tried.update(
            (switch[0] + dx, switch[1] + dy)
            for dx, dy in p.DIRECTIONS.values()
        )
        planner.propose([frame(A)], 1, ACTIONS)
        self.assertFalse(planner.v90_request_reset)
        self.assertEqual(planner.summary()['level2_v95_recovery_no_waypoint'], 1)

    def test_aligned_visible_pose_cannot_trigger_recovery(self):
        planner = self.trapped()
        aligned = tuple(tuple(bool(v) for v in row) for row in (
            (1, 1, 1), (0, 0, 1), (1, 0, 1)))
        planner.propose([frame(A, pose=aligned)], 1, ACTIONS)
        self.assertFalse(planner.v90_request_reset)
        self.assertEqual(planner.summary()['level2_v95_recovery_resets'], 0)

    def test_level_change_clears_cycle_threshold(self):
        planner = self.trapped()
        planner.record_frame_transition(observed(frame(A)),
            observed(frame(A), level=2), 'ACTION1', step_index=7)
        self.assertFalse(planner._v95_confirmed_short_cycles_by_fp)
        self.assertEqual(planner.summary()['level2_v95_recovery_resets'], 0)

    def test_reset_can_activate_visible_alternate_waypoint_planner(self):
        planner = self.trapped()
        planner.propose([frame(A)], 1, ACTIONS)
        planner.reset_pending()  # mimics policy reset cleanup
        candidate = planner.propose([frame(A)], 1, ACTIONS)
        self.assertIn(candidate, ACTIONS)
        self.assertGreaterEqual(planner.summary()['level2_v91_approaches_selected'], 1)
        self.assertFalse(planner.v90_request_reset)


if __name__ == '__main__':
    unittest.main()
