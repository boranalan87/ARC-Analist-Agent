"""V8.8 synthetic visible-frame tests; NOT proof of ARC game progress."""
import unittest
from types import SimpleNamespace

from test_feedback_v8_5_rotation_state import ACTIONS, GOAL, frame, p


def observed(grid, level=1, state='NOT_FINISHED', full_reset=False):
    return SimpleNamespace(frame=[grid], levels_completed=level,
                           state=SimpleNamespace(name=state),
                           full_reset=full_reset)


class V88SwitchTransitionTests(unittest.TestCase):
    def test_switch_exit_reveals_non_nominal_displacement_and_lost_alignment(self):
        planner = p.LS20VisualPlanner()
        before = observed(frame((49, 45), pose=GOAL))
        after = observed(frame((29, 40)))
        planner.record_frame_transition(before, after, 'ACTION1', step_index=23)
        report = planner.summary()
        self.assertEqual(report['level2_switch_exit_transitions_total'], 1)
        self.assertEqual(report['level2_switch_exit_transition_errors'], 0)
        event, = report['level2_switch_exit_transitions']
        self.assertEqual(event['step_index'], 23)
        self.assertEqual(event['selected_action'], 'ACTION1')
        self.assertEqual(event['before_player'], [49, 45])
        self.assertEqual(event['after_player'], [29, 40])
        self.assertEqual(event['nominal_delta'], [0, -5])
        self.assertEqual(event['nominal_next_player'], [49, 40])
        self.assertEqual(event['observed_delta'], [-20, -5])
        self.assertFalse(event['nominal_step_match'])
        self.assertEqual(event['before_rotations'], 0)
        self.assertEqual(event['after_rotations'], 3)
        self.assertTrue(event['alignment_lost'])
        self.assertEqual(event['source'], 'visible_action_before_after')
        self.assertEqual(len(event['before_frame_fp']), 16)
        self.assertEqual(len(event['after_frame_fp']), 16)

    def test_nominal_position_is_a_reference_not_a_game_rule(self):
        planner = p.LS20VisualPlanner()
        planner.record_frame_transition(
            observed(frame((49, 45), pose=GOAL)),
            observed(frame((49, 40), pose=GOAL)), 'ACTION1', step_index=1)
        event, = planner.summary()['level2_switch_exit_transitions']
        self.assertTrue(event['nominal_step_match'])
        self.assertFalse(event['alignment_lost'])
        self.assertFalse(event['after_full_reset'])

    def test_only_current_level_2_and_aligned_switch_are_recorded(self):
        planner = p.LS20VisualPlanner()
        for initial in [
            observed(frame((44, 45), pose=GOAL)),
            observed(frame((49, 45))),
            observed(frame((49, 45), pose=GOAL), level=0),
        ]:
            planner.record_frame_transition(initial, observed(frame()), 'ACTION1', step_index=1)
        planner.record_frame_transition(
            observed(frame((49, 45), pose=GOAL)),
            observed(frame()), 'RESET', step_index=2)
        self.assertEqual(planner.summary()['level2_switch_exit_transitions_total'], 0)

    def test_bad_visible_frames_do_not_change_actions_or_throw(self):
        planner = p.LS20VisualPlanner()
        invalid = observed([[0]])
        planner.record_frame_transition(invalid, observed(frame()), 'ACTION1', step_index=1)
        self.assertEqual(planner.summary()['level2_switch_exit_transitions'], [])
        self.assertEqual(planner.summary()['level2_switch_exit_transitions_total'], 0)
        # No action policy is called by the read-only instrumentation.
        self.assertEqual(planner.summary()['level2_alignment_lost'], 0)

    def test_collector_is_bounded_and_tracks_total(self):
        planner = p.LS20VisualPlanner()
        initial = observed(frame((49, 45), pose=GOAL))
        next_frame = observed(frame((29, 40)))
        for idx in range(20):
            planner.record_frame_transition(initial, next_frame, 'ACTION1', step_index=idx + 1)
        report = planner.summary()
        self.assertEqual(report['level2_switch_exit_transitions_total'], 20)
        self.assertEqual(len(report['level2_switch_exit_transitions']), 16)
        self.assertEqual(report['level2_switch_exit_transition_errors'], 0)

    def test_game_over_and_reset_flag_are_observed_not_interpreted(self):
        planner = p.LS20VisualPlanner()
        planner.record_frame_transition(
            observed(frame((49, 45), pose=GOAL)),
            observed(frame((29, 40)), state='GAME_OVER', full_reset=True),
            'ACTION1', step_index=46)
        event, = planner.summary()['level2_switch_exit_transitions']
        self.assertTrue(event['after_full_reset'])
        self.assertEqual(event['after_state'], 'GAME_OVER')


if __name__ == '__main__':
    unittest.main()
