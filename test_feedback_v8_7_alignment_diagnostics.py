"""V8.7 synthetic-frame event tracing tests. Not proof of an ARC score."""
import unittest

from test_feedback_v8_5_rotation_state import ACTIONS, GOAL, frame, p
from test_feedback_v8_6_aligned_route import aligned_frame


class V87AlignmentDiagnosticsTests(unittest.TestCase):
    def test_records_loss_with_previous_selected_action_and_visible_positions(self):
        planner = p.LS20VisualPlanner()
        proposed = planner.propose([aligned_frame()], 1, ACTIONS)
        self.assertEqual(proposed, 'ACTION2')
        planner.record_choice(proposed, 'ACTION2')
        planner.propose([frame((44, 45))], 1, ACTIONS)
        report = planner.summary()
        self.assertEqual(report['level2_alignment_lost'], 1)
        event = report['level2_alignment_events'][0]
        self.assertEqual(event['event_index'], 1)
        self.assertEqual(event['previous_player'], [54, 45])
        self.assertEqual(event['current_player'], [44, 45])
        self.assertEqual(event['switch'], [49, 45])
        self.assertEqual(event['previous_rotations'], 0)
        self.assertGreater(event['current_rotations'], 0)
        self.assertEqual(event['previous_proposed_action'], 'ACTION2')
        self.assertEqual(event['previous_selected_action'], 'ACTION2')
        self.assertEqual(event['previous_planner_reason'], 'pose_matches_goal')
        self.assertFalse(event['previous_on_switch'])
        self.assertFalse(event['current_on_switch'])
        self.assertEqual(event['source'], 'visible_frame')

    def test_missing_pose_is_not_counted_as_alignment_loss(self):
        planner = p.LS20VisualPlanner()
        planner.propose([aligned_frame()], 1, ACTIONS)
        missing = frame((44, 45), pose=GOAL)
        for y in range(55, 61):
            for x in range(3, 9):
                missing[y][x] = 0
        # Missing/invalid source should not create a false diagnostic event.
        self.assertIsNone(planner.propose([missing], 1, ACTIONS))
        self.assertEqual(planner.summary()['level2_alignment_lost'], 0)
        self.assertEqual(planner.summary()['level2_alignment_events'], [])

    def test_reset_discards_pending_pose_without_erasing_run_evidence(self):
        planner = p.LS20VisualPlanner()
        planner.propose([aligned_frame()], 1, ACTIONS)
        planner.record_choice('ACTION2', 'ACTION2')
        planner.propose([frame((44, 45))], 1, ACTIONS)
        self.assertEqual(len(planner.summary()['level2_alignment_events']), 1)
        planner.reset_pending()
        self.assertIsNone(planner._level2_last_visible)
        self.assertEqual(len(planner.summary()['level2_alignment_events']), 1)
        planner.propose([frame((44, 45))], 1, ACTIONS)
        self.assertEqual(planner.summary()['level2_alignment_lost'], 1)

    def test_unvalidated_level_does_not_create_event(self):
        planner = p.LS20VisualPlanner()
        planner.propose([aligned_frame()], 2, ACTIONS)
        self.assertEqual(planner.summary()['level2_alignment_events'], [])


if __name__ == '__main__':
    unittest.main()
