"""V8.6 synthetic-frame regression tests; these do NOT certify an ARC score."""
import unittest

from test_feedback_v8_5_rotation_state import ACTIONS, GOAL, frame, p


def aligned_frame(player=(54, 45), block_above=True, block_below=False):
    grid = frame(player=player, pose=GOAL)
    for y in ([40] if block_above else []) + ([50] if block_below else []):
        for dy in range(5):
            for dx in range(5):
                grid[y + dy][54 + dx] = 4
    return grid


class V86AlignedSafeRouteTests(unittest.TestCase):
    def test_bfs_avoids_visible_switch_when_pose_aligned(self):
        grid = aligned_frame()
        old_route = p.shortest_visible_path(
            grid, (54, 45), (14, 40), ACTIONS, set()
        )
        safe_route = p.shortest_visible_path(
            grid, (54, 45), (14, 40), ACTIONS, set(),
            avoid_positions={p.LEVEL_2_ROTATION_SWITCH},
        )
        self.assertEqual(old_route[0], 'ACTION3')  # shortest but re-enters switch
        self.assertEqual(safe_route[0], 'ACTION2')  # safely detour around switch

    def test_planner_selects_safe_detour_from_real_visible_landmarks(self):
        planner = p.LS20VisualPlanner()
        decision = planner.propose([aligned_frame()], 1, ACTIONS)
        self.assertEqual(decision, 'ACTION2')
        self.assertEqual(planner.summary()['level2_aligned_safe_routes'], 1)
        self.assertEqual(planner.summary()['level2_alignment_lost'], 0)

    def test_aligned_agent_may_exit_current_switch_without_reentry(self):
        planner = p.LS20VisualPlanner()
        # The switch must first be validated while not occluded by the player.
        planner.propose([frame((44, 45))], 1, ACTIONS)
        decision = planner.propose([frame((49, 45), pose=GOAL)], 1, ACTIONS)
        self.assertIn(decision, ACTIONS)
        dx, dy = p.DIRECTIONS[decision]
        self.assertNotEqual((49 + dx, 45 + dy), (49, 45))
        self.assertGreater(planner.summary()['level2_aligned_safe_routes'], 0)

    def test_no_safe_route_never_claims_success(self):
        planner = p.LS20VisualPlanner()
        decision = planner.propose(
            [aligned_frame(block_above=True, block_below=True)], 1, ACTIONS
        )
        self.assertIsNone(decision)
        self.assertEqual(planner.summary()['last_reason'],
                         'aligned_safe_goal_route_not_visible')
        self.assertEqual(planner.summary()['level2_aligned_goal_route_blocked'], 1)
        self.assertEqual(planner.summary()['level2_aligned_safe_routes'], 0)

    def test_alignment_loss_is_observed_not_inferred_from_missing_frames(self):
        planner = p.LS20VisualPlanner()
        self.assertEqual(planner.propose([aligned_frame()], 1, ACTIONS), 'ACTION2')
        # A later visible shape is misaligned again, without claiming why.
        planner.propose([frame((44, 45))], 1, ACTIONS)
        self.assertEqual(planner.summary()['level2_alignment_lost'], 1)
        planner.reset_pending()
        self.assertEqual(planner._level2_was_aligned, False)

    def test_other_levels_preserve_unvalidated_fallback(self):
        planner = p.LS20VisualPlanner()
        self.assertIsNone(planner.propose([aligned_frame()], 2, ACTIONS))
        self.assertEqual(planner.summary()['last_reason'], 'unvalidated_level')


if __name__ == '__main__':
    unittest.main()
