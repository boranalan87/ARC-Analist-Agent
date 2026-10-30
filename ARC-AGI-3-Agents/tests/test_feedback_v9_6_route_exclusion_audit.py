"""V9.6 synthetic-frame audit: NO claim of real LS20 score improvement."""
import unittest
from test_feedback_v9_5_route_recovery import V95RouteRecoveryTests, A, ACTIONS, frame, p
from test_feedback_v9_4_short_cycle_guard import cycle


class V96RouteExclusionAuditTests(unittest.TestCase):
    def trapped(self):
        return V95RouteRecoveryTests().trapped()

    def test_requires_confirmed_observed_cycles(self):
        x = p.LS20VisualPlanner()
        cycle(x, repeats=2)  # only one fully confirmed 4-step loop
        x.propose([frame(A)], 1, ACTIONS)
        self.assertEqual(x.summary()['level2_v96_route_exclusion_audits'], 0)

    def test_records_all_four_switch_adjacent_visible_tiles(self):
        x = self.trapped()
        switch = p.LEVEL_2_ROTATION_SWITCH
        x._v91_waypoints_tried.update(
            (switch[0] + dx, switch[1] + dy)
            for dx, dy in p.DIRECTIONS.values()
        )
        # Verified observed failure remains different from mere attempt history.
        bad = (switch[0] + p.DIRECTIONS['ACTION1'][0],
               switch[1] + p.DIRECTIONS['ACTION1'][1])
        x._v92_confirmed_dead_end_approaches.add(bad)
        x.propose([frame(A)], 1, ACTIONS)
        self.assertFalse(x.v90_request_reset)
        s = x.summary()
        self.assertEqual(s['level2_v96_route_exclusion_audits'], 1)
        outcomes = s['level2_v96_route_exclusion_events'][0]['outcomes']
        self.assertEqual(len(outcomes), 4)
        reasons = {item['from_switch_action']: item['reason'] for item in outcomes}
        self.assertEqual(reasons['ACTION1'], 'observed_failed_entry')
        self.assertEqual(reasons['ACTION3'], 'player_at_waypoint')
        self.assertEqual(reasons['ACTION2'], 'already_tried')
        self.assertEqual(reasons['ACTION4'], 'already_tried')
        self.assertEqual(s['level2_v95_recovery_no_waypoint'], 1)
        self.assertEqual(s['level2_v95_recovery_resets'], 0)

    def test_not_passable_uses_only_visible_terrain(self):
        x = p.LS20VisualPlanner()
        grid = frame(A)
        # Render an impassable tile at the right-hand switch neighbor.
        for dy in range(5):
            for dx in range(5):
                grid[45 + dy][54 + dx] = 4
        x._v96_audit_route_exclusion(grid, A, p.LEVEL_2_ROTATION_SWITCH,
                                    '1234567890abcdef', ACTIONS)
        outcomes = {item['from_switch_action']: item['reason']
                    for item in x.summary()['level2_v96_route_exclusion_events'][0]['outcomes']}
        self.assertEqual(outcomes['ACTION4'], 'not_visibly_passable')

    def test_no_waypoint_audit_has_no_navigation_side_effects(self):
        x = p.LS20VisualPlanner()
        grid = frame(A)
        x._v91_waypoints_tried.add((49, 40))
        x._v92_confirmed_dead_end_approaches.add((49, 50))
        before = (set(x._v91_waypoints_tried),
                  set(x._v92_confirmed_dead_end_approaches),
                  x._v91_dead_end_resets, x.v90_request_reset,
                  x._v91_approach_waypoint)
        x._v96_audit_route_exclusion(grid, A, p.LEVEL_2_ROTATION_SWITCH,
                                    '1234567890abcdef', ACTIONS)
        after = (set(x._v91_waypoints_tried),
                 set(x._v92_confirmed_dead_end_approaches),
                 x._v91_dead_end_resets, x.v90_request_reset,
                 x._v91_approach_waypoint)
        self.assertEqual(before, after)

    def test_audit_bounded_but_total_retained(self):
        x = self.trapped()
        switch = p.LEVEL_2_ROTATION_SWITCH
        x._v91_waypoints_tried.update(
            (switch[0] + dx, switch[1] + dy)
            for dx, dy in p.DIRECTIONS.values()
        )
        for _ in range(10):
            x.propose([frame(A)], 1, ACTIONS)
        self.assertEqual(x.summary()['level2_v96_route_exclusion_audits'], 10)
        self.assertEqual(len(x.summary()['level2_v96_route_exclusion_events']), 4)
        self.assertTrue(all(len(e['outcomes']) == 4
                            for e in x.summary()['level2_v96_route_exclusion_events']))

    def test_recovery_still_works_when_untried_waypoint_exists(self):
        x = self.trapped()
        x.propose([frame(A)], 1, ACTIONS)
        self.assertTrue(x.v90_request_reset)
        self.assertEqual(x.summary()['level2_v95_recovery_resets'], 1)
        self.assertEqual(x.summary()['level2_v96_route_exclusion_audits'], 0)

    def test_other_levels_and_bad_frames_do_not_create_audit(self):
        x = self.trapped()
        self.assertIsNone(x.propose([[[0]]], 1, ACTIONS))
        self.assertIsNone(x.propose([frame(A)], 3, ACTIONS))
        self.assertEqual(x.summary()['level2_v96_route_exclusion_audits'], 0)


if __name__ == '__main__':
    unittest.main()
