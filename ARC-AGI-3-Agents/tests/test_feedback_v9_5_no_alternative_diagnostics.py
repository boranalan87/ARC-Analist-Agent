"""V9.5 read-only diagnostics; these tests do not claim a game win."""
import unittest
from test_feedback_v9_4_short_cycle_guard import A, ACTIONS, cycle, frame, p


class V95NoAlternativeDiagnosticsTests(unittest.TestCase):
    def _trapped_planner(self):
        planner = p.LS20VisualPlanner()
        cycle(planner, 2)
        # Force no eligible alternatives while preserving the witnessed loop.
        for action in ACTIONS:
            if action != 'ACTION4':
                planner._blocked.add((A, action))
        return planner

    def test_short_cycle_no_alternative_records_bounded_evidence(self):
        planner = self._trapped_planner()
        planner.propose([frame(A)], 1, ACTIONS)
        info = planner.summary()
        self.assertEqual(info['level2_v95_no_alternative_events_total'], 1)
        self.assertEqual(len(info['level2_v95_no_alternative_events']), 1)
        item = info['level2_v95_no_alternative_events'][0]
        self.assertEqual(item['source'], 'validated_visible_level2')
        self.assertEqual(item['player'], list(A))
        self.assertIn('ACTION4', item['repeated_actions'])
        self.assertEqual(len(item['frame_fp']), 16)
        self.assertNotIn('frame', item)

    def test_many_repeated_diagnostics_remain_bounded(self):
        planner = self._trapped_planner()
        for _ in range(14):
            planner.propose([frame(A)], 1, ACTIONS)
        info = planner.summary()
        self.assertGreaterEqual(info['level2_v95_no_alternative_events_total'], 8)
        self.assertLessEqual(len(info['level2_v95_no_alternative_events']), 8)

    def test_unconfirmed_short_cycle_does_not_count(self):
        planner = p.LS20VisualPlanner()
        cycle(planner, 1)
        planner.propose([frame(A)], 1, ACTIONS)
        self.assertEqual(planner.summary()['level2_v95_no_alternative_events_total'], 0)

    def test_invalid_visible_frame_does_not_create_evidence(self):
        planner = p.LS20VisualPlanner()
        planner.propose([[[1]]], 1, ACTIONS)
        self.assertEqual(planner.summary()['level2_v95_no_alternative_events_total'], 0)
        self.assertEqual(planner.summary()['level2_v95_no_alternative_events'], [])


if __name__ == '__main__':
    unittest.main()
