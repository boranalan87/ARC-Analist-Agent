"""V9.4 synthetic frame tests: short oscillation proof, not gameplay success."""
import unittest
from test_feedback_v8_5_rotation_state import ACTIONS, GOAL, frame, p
from test_feedback_v8_8_switch_transition import observed

A = (44, 45)
B = (49, 45)


def cycle(planner, repeats=2, *, action2='ACTION3', level=1, pose=None):
    for i in range(repeats):
        planner.record_frame_transition(observed(frame(A, pose=pose), level=level),
          observed(frame(B, pose=pose), level=level), 'ACTION4', step_index=2*i+1)
        planner.record_frame_transition(observed(frame(B, pose=pose), level=level),
          observed(frame(A, pose=pose), level=level), action2, step_index=2*i+2)

class V94ShortCycleGuardTests(unittest.TestCase):
    def test_one_round_trip_not_sufficient(self):
        x=p.LS20VisualPlanner(); cycle(x,1)
        self.assertEqual(x.summary()['level2_v94_short_cycles_confirmed'],0)
        self.assertFalse(x._v94_short_guard_pairs)

    def test_two_matching_round_trips_confirm_observed_loop(self):
        x=p.LS20VisualPlanner(); cycle(x,2)
        self.assertEqual(x.summary()['level2_v94_short_cycles_confirmed'],1)
        self.assertEqual(x._v94_short_guard_pairs, {(p._v93_visible_state_fp(frame(A)), 'ACTION4')})
        self.assertEqual(x.summary()['level2_v94_unique_pairs_blocked'],1)

    def test_wrong_reverse_action_is_not_an_oscillation(self):
        x=p.LS20VisualPlanner(); cycle(x,2,action2='ACTION2')
        self.assertEqual(x.summary()['level2_v94_short_cycles_confirmed'],0)

    def test_one_self_loop_still_not_proof(self):
        x=p.LS20VisualPlanner()
        for i in range(6):
            f=observed(frame(A))
            x.record_frame_transition(f,f,'ACTION4',step_index=i+1)
        self.assertEqual(x.summary()['level2_v94_short_cycles_confirmed'],0)

    def test_hud_changes_do_not_erase_exact_observed_two_step_loop(self):
        x=p.LS20VisualPlanner()
        for i in range(4):
            start=A if i%2==0 else B
            end=B if i%2==0 else A
            before=frame(start); after=frame(end)
            before[61][13]=i+3; after[61][13]=i+4
            x.record_frame_transition(observed(before),observed(after),
              'ACTION4' if i%2==0 else 'ACTION3',step_index=i+1)
        self.assertEqual(x.summary()['level2_v94_unique_pairs_blocked'],1)

    def test_actual_alternative_route_after_two_observed_cycles(self):
        x=p.LS20VisualPlanner(); cycle(x,2)
        move=x.propose([frame(A)],1,ACTIONS)
        self.assertIn(move,ACTIONS)
        self.assertNotEqual(move,'ACTION4')
        self.assertGreaterEqual(x.summary()['level2_v94_guard_activations'],1)
        self.assertGreaterEqual(x.summary()['level2_v94_detours_selected'],1)

    def test_one_unvalidated_level_has_no_v94_guard(self):
        x=p.LS20VisualPlanner(); cycle(x,3,level=0)
        self.assertEqual(x.summary()['level2_v94_short_cycles_confirmed'],0)

    def test_invalid_frames_cannot_create_cycle(self):
        x=p.LS20VisualPlanner()
        for i in range(9):
            x.record_frame_transition(observed([[1]]),observed(frame(A)),
              'ACTION4',step_index=i+1)
        self.assertEqual(x.summary()['level2_v94_short_cycles_confirmed'],0)
        self.assertEqual(x.summary()['level2_v94_observation_errors'],0)

    def test_level_change_clears_short_cycle_guard(self):
        x=p.LS20VisualPlanner(); cycle(x,2)
        x.record_frame_transition(observed(frame(A)),observed(frame(A),level=2),
          'ACTION1',step_index=5)
        self.assertFalse(x._v94_short_guard_pairs)

    def test_reset_pending_retains_same_run_verified_short_cycle(self):
        x=p.LS20VisualPlanner(); cycle(x,2)
        x.reset_pending()
        self.assertTrue(x._v94_short_guard_pairs)

    def test_no_progress_from_route_proposal_alone(self):
        x=p.LS20VisualPlanner()
        for i in range(20): x.propose([frame(A)],1,ACTIONS)
        self.assertEqual(x.summary()['level2_v94_short_cycles_confirmed'],0)

    def test_bounded_history_and_private_summary(self):
        x=p.LS20VisualPlanner(); cycle(x,20)
        self.assertLessEqual(len(x._v94_short_guard_pairs),8)
        self.assertNotIn('_v94_short_guard_pairs',x.summary())

if __name__=='__main__': unittest.main()
