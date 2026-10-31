"""V9.7 synthetic tests; not a real LS20 game result."""
import unittest
import test_feedback_v9_5_route_recovery as v95
from test_feedback_v9_4_short_cycle_guard import A, ACTIONS, frame, p


class V97BoundedRetryTests(unittest.TestCase):
    def trapped(self, enabled=True):
        x = v95.V95RouteRecoveryTests().trapped()
        x.enable_v97_bounded_retry = enabled
        switch = p.LEVEL_2_ROTATION_SWITCH
        x._v91_waypoints_tried.update(
            (switch[0] + dx, switch[1] + dy)
            for dx, dy in p.DIRECTIONS.values()
        )
        x._v92_confirmed_dead_end_approaches.add((49, 40))
        return x

    def test_disabled_keeps_v96_behavior(self):
        x = self.trapped(enabled=False)
        x.propose([frame(A)], 1, ACTIONS)
        self.assertFalse(x.v90_request_reset)
        self.assertEqual(x.level2_v97_retry_reset_requests, 0)

    def test_tried_but_not_verified_bad_can_be_retried(self):
        x = self.trapped()
        x.propose([frame(A)], 1, ACTIONS)
        self.assertTrue(x.v90_request_reset)
        self.assertEqual(x.level2_v97_retry_reset_requests, 1)
        self.assertIn(x._v97_retry_waypoint, ((49, 50), (54, 45)))
        self.assertNotIn(
            x._v97_retry_waypoint,
            x._v92_confirmed_dead_end_approaches,
        )

    def test_reset_preserves_only_reserved_retry(self):
        x = self.trapped()
        x.propose([frame(A)], 1, ACTIONS)
        target = x._v97_retry_waypoint
        x.reset_pending()
        self.assertEqual(x._v97_retry_waypoint, target)
        move = x.propose([frame(A)], 1, ACTIONS)
        self.assertIn(move, ACTIONS)
        self.assertEqual(x.level2_v97_retry_approaches_selected, 1)
        self.assertIsNone(x._v97_retry_waypoint)

    def test_all_verified_bad_never_requests_retry(self):
        x = self.trapped()
        switch = p.LEVEL_2_ROTATION_SWITCH
        x._v92_confirmed_dead_end_approaches.update(
            (switch[0] + dx, switch[1] + dy)
            for dx, dy in p.DIRECTIONS.values()
        )
        x.propose([frame(A)], 1, ACTIONS)
        self.assertFalse(x.v90_request_reset)
        self.assertEqual(x.level2_v97_retry_reset_requests, 0)

    def test_no_second_retry_for_same_observed_state(self):
        x = self.trapped()
        x.propose([frame(A)], 1, ACTIONS)
        x.reset_pending()
        x.propose([frame(A)], 1, ACTIONS)
        self.assertFalse(x.v90_request_reset)
        self.assertEqual(x.level2_v97_retry_reset_requests, 1)


if __name__ == "__main__":
    unittest.main()
