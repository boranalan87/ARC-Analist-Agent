"""V9.1 synthetic pixel-frame tests. No live game; NO score guarantees."""
import hashlib
import unittest

from test_feedback_v8_5_rotation_state import ACTIONS, GOAL, frame, p


def fp(grid):
    return hashlib.sha256(bytes(v for row in grid for v in row)).hexdigest()[:16]


class V91PreSwitchRouteTests(unittest.TestCase):
    def planner_with_dead_end(self):
        planner = p.LS20VisualPlanner()
        planner.propose([frame((44, 45))], 1, ACTIONS)
        aligned = frame((49, 45), pose=GOAL)
        planner._level2_risky_exits.update((fp(aligned), a) for a in ACTIONS)
        self.assertIsNone(planner.propose([aligned], 1, ACTIONS))
        self.assertTrue(planner.v90_request_reset)
        planner.reset_pending()
        return planner

    def test_before_dead_end_preserves_original_shortest_approach(self):
        planner = p.LS20VisualPlanner()
        self.assertEqual(planner.propose([frame((44, 45))], 1, ACTIONS), 'ACTION4')
        self.assertEqual(planner.summary()['level2_v91_alternative_steps'], 0)

    def test_after_dead_end_routes_via_visible_neighbor_without_switch_entry(self):
        planner = self.planner_with_dead_end()
        action = planner.propose([frame((44, 45))], 1, ACTIONS)
        self.assertIn(action, ACTIONS)
        self.assertNotEqual(action, 'ACTION4')
        self.assertEqual(planner.summary()['level2_v91_dead_end_resets'], 1)
        self.assertEqual(planner.summary()['level2_v91_approaches_selected'], 1)
        self.assertEqual(planner.summary()['last_reason'],
                         'v91_observed_dead_end_alternate_approach')
        self.assertEqual(planner.summary()['level2_v91_distinct_waypoints'], 1)

    def test_approach_reaches_neighbor_then_may_enter_switch(self):
        planner = self.planner_with_dead_end()
        self.assertEqual(planner.propose([frame((44, 45))], 1, ACTIONS), 'ACTION1')
        self.assertEqual(planner.propose([frame((44, 40))], 1, ACTIONS), 'ACTION4')
        self.assertEqual(planner.propose([frame((49, 40))], 1, ACTIONS), 'ACTION2')
        self.assertEqual(planner.summary()['level2_v91_alternative_steps'], 3)

    def test_reset_clears_active_waypoint_but_keeps_run_level_history(self):
        planner = self.planner_with_dead_end()
        planner.propose([frame((44, 45))], 1, ACTIONS)
        self.assertIsNotNone(planner._v91_approach_waypoint)
        planner.reset_pending()
        self.assertIsNone(planner._v91_approach_waypoint)
        self.assertEqual(planner.summary()['level2_v91_distinct_waypoints'], 1)
        self.assertEqual(planner.summary()['level2_v91_dead_end_resets'], 1)

    def test_candidates_never_force_disallowed_step(self):
        planner = self.planner_with_dead_end()
        candidates = ('ACTION2', 'ACTION3', 'ACTION4')
        move = planner.propose([frame((44, 45))], 1, candidates)
        self.assertTrue(move is None or move in candidates)

    def test_waypoint_choice_bounded_to_four_distinct_neighbors(self):
        planner = self.planner_with_dead_end()
        for _ in range(9):
            planner.reset_pending()
            planner.propose([frame((44, 45))], 1, ACTIONS)
        self.assertLessEqual(planner.summary()['level2_v91_distinct_waypoints'], 4)
        self.assertGreaterEqual(planner.summary()['level2_v91_approaches_exhausted'], 1)

    def test_other_levels_and_unknown_frames_do_not_trigger_detour(self):
        planner = self.planner_with_dead_end()
        self.assertIsNone(planner.propose([frame((44,45))], 2, ACTIONS))
        self.assertEqual(planner.summary()['level2_v91_alternative_steps'], 0)
        self.assertIsNone(planner.propose([[[0]]], 1, ACTIONS))
        self.assertEqual(planner.summary()['level2_v91_alternative_steps'], 0)

    def test_telemetry_only_bounded_aggregates(self):
        s = self.planner_with_dead_end().summary()
        self.assertIn('level2_v91_dead_end_resets', s)
        self.assertIn('level2_v91_distinct_waypoints', s)
        self.assertNotIn('_v91_waypoints_tried', s)
        self.assertNotIn('_v90_transitions', s)


if __name__ == '__main__':
    unittest.main()
