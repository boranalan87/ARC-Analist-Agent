"""V9.8 synthetic tests: no real-game score is asserted."""
import unittest
from unittest.mock import patch

import test_feedback_v9_5_route_recovery as v95
from test_feedback_v9_4_short_cycle_guard import A, ACTIONS, frame, p


class V98ShortestRetryTests(unittest.TestCase):
    def trapped(self, enabled):
        planner = v95.V95RouteRecoveryTests().trapped()
        planner.enable_v97_bounded_retry = True
        planner.enable_v98_shortest_retry = enabled
        switch = p.LEVEL_2_ROTATION_SWITCH
        planner._v91_waypoints_tried.update(
            (switch[0] + dx, switch[1] + dy)
            for dx, dy in p.DIRECTIONS.values()
        )
        planner._v92_confirmed_dead_end_approaches.add((49, 40))
        return planner

    def distances(self, grid, start, goal, *args, **kwargs):
        if goal == (49, 50):
            return ["ACTION2"] * 11
        if goal == (54, 45):
            return ["ACTION4"] * 2
        return None

    def test_default_opt_in_is_off(self):
        planner = p.LS20VisualPlanner()
        self.assertFalse(planner.enable_v98_shortest_retry)
        self.assertEqual(planner.level2_v98_shortest_retry_selected, 0)

    def test_disabled_preserves_v97_first_reachable(self):
        planner = self.trapped(False)
        with patch.object(p, 'shortest_visible_path', side_effect=self.distances):
            planner.propose([frame(A)], 1, ACTIONS)
        self.assertTrue(planner.v90_request_reset)
        self.assertEqual(planner._v97_retry_waypoint, (49, 50))
        self.assertEqual(planner.level2_v98_retry_candidates_examined, 0)

    def test_enabled_uses_shortest_current_visible_route(self):
        planner = self.trapped(True)
        with patch.object(p, 'shortest_visible_path', side_effect=self.distances):
            planner.propose([frame(A)], 1, ACTIONS)
        self.assertTrue(planner.v90_request_reset)
        self.assertEqual(planner._v97_retry_waypoint, (54, 45))
        self.assertEqual(planner.level2_v98_retry_candidates_examined, 2)
        self.assertEqual(planner.level2_v98_shortest_retry_selected, 1)
        self.assertEqual(planner.summary()['level2_v98_shortest_retry_selected'], 1)

    def test_verified_bad_approaches_are_never_selected(self):
        planner = self.trapped(True)
        planner._v92_confirmed_dead_end_approaches.update(((49, 50), (54, 45)))
        with patch.object(p, 'shortest_visible_path', side_effect=self.distances):
            planner.propose([frame(A)], 1, ACTIONS)
        self.assertFalse(planner.v90_request_reset)
        self.assertEqual(planner.level2_v98_shortest_retry_selected, 0)

    def test_one_loop_is_insufficient_even_with_opt_in(self):
        planner = v95.V95RouteRecoveryTests().trapped(repeats=2)
        planner.enable_v97_bounded_retry = True
        planner.enable_v98_shortest_retry = True
        with patch.object(p, 'shortest_visible_path', side_effect=self.distances):
            planner.propose([frame(A)], 1, ACTIONS)
        self.assertFalse(planner.v90_request_reset)
        self.assertEqual(planner.level2_v98_shortest_retry_selected, 0)


if __name__ == '__main__':
    unittest.main()
