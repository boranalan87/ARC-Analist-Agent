"""V9.0 isolated synthetic tests. NEVER claim real ARC-game improvement."""
import hashlib
import unittest

from test_feedback_v8_5_rotation_state import ACTIONS, GOAL, frame, p
from test_feedback_v8_8_switch_transition import observed


def fp(grid):
    return hashlib.sha256(bytes(x for row in grid for x in row)).hexdigest()[:16]


class V90ObservedTransitionLearningTests(unittest.TestCase):
    def aligned_planner(self):
        planner = p.LS20VisualPlanner()
        planner.propose([frame((44, 45))], 1, ACTIONS)
        return planner

    def test_historical_references_are_supported_by_real_observations(self):
        self.assertEqual(p.V90_FAILED_EXIT_ACTIONS['e58c8a39094e9e8f'],
                         frozenset(ACTIONS))
        self.assertEqual(p.V90_FAILED_EXIT_ACTIONS['70c046c20de8d462'],
                         frozenset(('ACTION1', 'ACTION3', 'ACTION4')))
        self.assertEqual(p.V90_FAILED_EXIT_ACTIONS['869a0f09dcb2c63c'],
                         frozenset(('ACTION1', 'ACTION3', 'ACTION4')))

    def test_non_switch_level2_action_is_learned_from_actual_frames(self):
        planner = self.aligned_planner()
        start = frame((44, 45))
        finish = frame((49, 45), pose=GOAL)
        planner.record_frame_transition(observed(start), observed(finish),
                                        'ACTION4', step_index=1)
        model = planner._v90_transitions[(fp(start), 'ACTION4')]
        self.assertEqual(model['after_fp'], fp(finish))
        self.assertEqual(model['attempts'], 1)
        self.assertEqual(model['hazards'], 0)
        self.assertEqual(planner.summary()['level2_transition_samples'], 1)
        # Old V8.8 collector must still only log ALIGNED SWITCH exits.
        self.assertEqual(planner.summary()['level2_switch_exit_transitions_total'], 0)

    def test_aligned_switch_alignment_loss_is_a_genuine_hazard(self):
        planner = self.aligned_planner()
        before = frame((49, 45), pose=GOAL)
        after = frame((29, 40))
        planner.record_frame_transition(observed(before), observed(after),
                                        'ACTION2', step_index=35)
        self.assertEqual(planner.summary()['level2_transition_hazard_samples'], 1)
        self.assertIn((fp(before), 'ACTION2'), planner._level2_risky_exits)
        self.assertEqual(planner.summary()['level2_switch_exit_transitions_total'], 1)

    def test_game_over_is_learned_even_on_nominal_direction(self):
        planner = self.aligned_planner()
        before = frame((49, 45), pose=GOAL)
        after = frame((44, 45), pose=GOAL)
        planner.record_frame_transition(observed(before),
                                        observed(after, state='GAME_OVER'),
                                        'ACTION3', step_index=79)
        self.assertEqual(planner.summary()['level2_transition_hazard_samples'], 1)
        self.assertIn((fp(before), 'ACTION3'), planner._level2_risky_exits)

    def test_verified_full_bad_switch_requests_reset_instead_of_bad_move(self):
        planner = self.aligned_planner()
        current = frame((49, 45), pose=GOAL)
        planner._level2_risky_exits.update((fp(current), a) for a in ACTIONS)
        self.assertIsNone(planner.propose([current], 1, ACTIONS))
        self.assertTrue(planner.v90_request_reset)
        self.assertEqual(planner.summary()['level2_transition_forced_resets'], 1)
        self.assertEqual(planner.summary()['last_reason'],
                         'v90_all_switch_exits_observed_bad')
        # Reset request must not persist into an unrelated decision.
        planner.propose([frame((44, 45))], 1, ACTIONS)
        self.assertFalse(planner.v90_request_reset)

    def test_observed_switch_trap_replans_before_switch_entry(self):
        planner = self.aligned_planner()
        before = frame((44, 45))
        failed_switch = frame((49, 45), pose=GOAL)
        # Simulate prior one-step observation, NOT invented future actions.
        planner.record_frame_transition(observed(before), observed(failed_switch),
                                        'ACTION4', step_index=12)
        planner._level2_risky_exits.update((fp(failed_switch), a) for a in ACTIONS)
        planner.reset_pending()  # Run-local transition learning survives RESET.
        new_choice = planner.propose([before], 1, ACTIONS)
        self.assertIn(new_choice, ACTIONS)
        self.assertNotEqual(new_choice, 'ACTION4')
        self.assertGreaterEqual(planner.level2_transition_trap_avoids, 1)

    def test_same_frame_action_twice_marks_self_loop_for_avoidance(self):
        planner = self.aligned_planner()
        before = frame((44, 45))
        for i in range(2):
            planner.record_frame_transition(observed(before), observed(before),
                                            'ACTION1', step_index=i)
        self.assertEqual(planner.summary()['level2_transition_self_loops'], 2)
        planner.reset_pending()
        planner.propose([before], 1, ACTIONS)
        self.assertGreaterEqual(planner.level2_transition_loop_avoids, 1)

    def test_bounded_memory_rejects_new_pairs_but_counts_attempts(self):
        planner = self.aligned_planner()
        planner._v90_max_pairs = 1
        before = frame((44, 45))
        after = frame((49, 45))
        planner.record_frame_transition(observed(before), observed(after),
                                        'ACTION4', step_index=1)
        planner.record_frame_transition(observed(before), observed(after),
                                        'ACTION3', step_index=2)
        self.assertEqual(len(planner._v90_transitions), 1)
        self.assertEqual(planner.summary()['level2_transition_memory_full'], 1)

    def test_reset_does_not_erase_learning_but_resets_switch_phase(self):
        planner = self.aligned_planner()
        before = frame((44, 45))
        planner.record_frame_transition(observed(before), observed(frame((49, 45))),
                                        'ACTION4', step_index=1)
        planner.reset_pending()
        self.assertIn((fp(before), 'ACTION4'), planner._v90_transitions)
        self.assertIsNone(planner._switch_plan)

    def test_other_levels_and_unvalidated_frames_never_learn(self):
        planner = p.LS20VisualPlanner()
        valid = frame((44, 45))
        planner.record_frame_transition(observed(valid, level=0), observed(valid),
                                        'ACTION4', step_index=1)
        planner.record_frame_transition(observed(valid, level=2), observed(valid),
                                        'ACTION4', step_index=2)
        planner.record_frame_transition(observed([[0]]), observed(valid),
                                        'ACTION4', step_index=3)
        self.assertEqual(planner.summary()['level2_transition_samples'], 0)
        self.assertEqual(planner.summary()['level2_transition_distinct_pairs'], 0)

    def test_diagnostics_are_aggregates_not_raw_frames_or_unbounded_graph(self):
        planner = self.aligned_planner()
        summary = planner.summary()
        self.assertNotIn('_v90_transitions', summary)
        self.assertNotIn('transition_graph', summary)
        self.assertIn('level2_transition_distinct_pairs', summary)
        self.assertIn('level2_transition_hazard_samples', summary)
        self.assertIn('level2_transition_trap_avoids', summary)
        self.assertLessEqual(planner._v90_max_pairs, 192)

    def test_agent_has_bounded_reset_interlock_only_on_validated_level2(self):
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / 'agents' / 'templates' / 'feedback_explorer.py'
        content = path.read_text()
        self.assertIn('AGENT_VERSION = "9.0"', content)
        self.assertIn("if level2_visual and getattr(self._ls20_visual_planner, 'v90_request_reset', False):", content)
        self.assertIn('action = GameAction.RESET', content)


if __name__ == '__main__':
    unittest.main()
