"""V9.2 isolated synthetic-frame tests; NOT evidence of better game score."""
import hashlib
import unittest

from test_feedback_v8_5_rotation_state import ACTIONS, GOAL, frame, p
from test_feedback_v8_8_switch_transition import observed


def fp(grid):
    return hashlib.sha256(bytes(v for row in grid for v in row)).hexdigest()[:16]


def observed_bad_entry():
    planner = p.LS20VisualPlanner()
    start = frame((44, 45))
    switch = frame((49, 45), pose=GOAL)
    planner.propose([start], 1, ACTIONS)
    planner.record_frame_transition(
        observed(start), observed(switch), 'ACTION4', step_index=1
    )
    planner._level2_risky_exits.update((fp(switch), a) for a in ACTIONS)
    return planner, switch


class V92ObservedApproachTests(unittest.TestCase):
    def test_requires_an_observed_nominal_entry_not_a_guess(self):
        planner = p.LS20VisualPlanner()
        planner.propose([frame((44, 45))], 1, ACTIONS)
        self.assertEqual(planner.summary()['level2_v92_observed_entries'], 0)

    def test_real_entry_is_counted_only_with_validated_visible_frames(self):
        planner, _ = observed_bad_entry()
        self.assertEqual(planner.summary()['level2_v92_observed_entries'], 1)

    def test_dead_end_counts_entry_only_for_exact_rendered_switch_frame(self):
        planner, switch = observed_bad_entry()
        self.assertIsNone(planner.propose([switch], 1, ACTIONS))
        self.assertTrue(planner.v90_request_reset)
        s = planner.summary()
        self.assertEqual(s['level2_v92_verified_bad_approaches'], 1)
        self.assertIn((44, 45), planner._v92_confirmed_dead_end_approaches)
        self.assertNotIn('_v92_last_observed_entry', s)

    def test_bad_entry_is_skipped_after_reset_when_alternatives_exist(self):
        planner, switch = observed_bad_entry()
        planner.propose([switch], 1, ACTIONS)
        planner.reset_pending()
        planner._v91_waypoints_tried.update({(49, 40), (49, 50)})
        action = planner.propose([frame((44, 45))], 1, ACTIONS)
        self.assertIn(action, ACTIONS)
        self.assertEqual(planner._v91_approach_waypoint, (54, 45))
        self.assertGreaterEqual(planner.summary()['level2_v92_approaches_skipped'], 1)

    def test_proposed_route_without_actual_transition_cannot_disqualify_approach(self):
        planner = p.LS20VisualPlanner()
        planner.propose([frame((44, 45))], 1, ACTIONS)
        switch = frame((49, 45), pose=GOAL)
        planner._level2_risky_exits.update((fp(switch), action) for action in ACTIONS)
        planner.propose([switch], 1, ACTIONS)
        self.assertEqual(planner.summary()['level2_v92_verified_bad_approaches'], 0)

    def test_no_inference_from_non_nominal_move_or_unknown_level(self):
        planner = p.LS20VisualPlanner()
        planner.record_frame_transition(
            observed(frame((44, 45))),
            observed(frame((49, 45), pose=GOAL)),
            'ACTION1', step_index=1
        )
        planner.record_frame_transition(
            observed(frame((44, 45)), level=0),
            observed(frame((49, 45), pose=GOAL), level=0),
            'ACTION4', step_index=2
        )
        self.assertEqual(planner.summary()['level2_v92_observed_entries'], 0)

    def test_reset_keeps_observed_bad_approaches_not_stale_pending_entry(self):
        planner, switch = observed_bad_entry()
        planner.propose([switch], 1, ACTIONS)
        planner.reset_pending()
        self.assertIsNone(planner._v92_last_observed_entry)
        self.assertEqual(len(planner._v92_confirmed_dead_end_approaches), 1)

    def test_bad_frames_and_other_levels_are_safe(self):
        planner = p.LS20VisualPlanner()
        planner.record_frame_transition(
            observed([[0]]), observed(frame((49, 45), pose=GOAL)),
            'ACTION4', step_index=1
        )
        self.assertEqual(planner.summary()['level2_v92_observed_entries'], 0)
        self.assertIsNone(planner.propose([frame((44,45))], 3, ACTIONS))


if __name__ == '__main__':
    unittest.main()
