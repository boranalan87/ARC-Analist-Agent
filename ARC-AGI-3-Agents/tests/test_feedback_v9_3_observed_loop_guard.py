"""V9.3 synthetic visible frame regression tests. NOT an actual ARC game score."""
import unittest
from test_feedback_v8_5_rotation_state import ACTIONS, frame, p
from test_feedback_v8_8_switch_transition import observed

# A synthetic closed eight-step circuit, without hidden game state.
POINTS = [(29,45), (34,45), (39,45), (44,45),
          (44,40), (39,40), (34,40), (29,40), (29,45)]
MOVES = ('ACTION4','ACTION4','ACTION4','ACTION1',
         'ACTION3','ACTION3','ACTION3','ACTION2')


def feed(planner, n=2, change_at=None):
    idx=0
    for _ in range(n):
        for i, name in enumerate(MOVES):
            idx+=1
            action = 'ACTION2' if idx == change_at else name
            planner.record_frame_transition(observed(frame(POINTS[i])),
                observed(frame(POINTS[i+1])), action, step_index=idx)


class V93ObservedLoopTests(unittest.TestCase):
    def test_step_counter_hud_changes_do_not_hide_real_repeated_cycle(self):
        x=p.LS20VisualPlanner()
        for idx in range(16):
            i=idx%8
            before=frame(POINTS[i]); after=frame(POINTS[i+1])
            # HUD digits differ on every observed step, but game state does not.
            before[61][13]=idx; after[61][13]=idx+1
            x.record_frame_transition(observed(before),observed(after),
                  MOVES[i],step_index=idx+1)
        self.assertGreaterEqual(x.summary()['level2_v93_cycles_confirmed'],1)
        self.assertEqual(x.summary()['level2_v93_unique_actions_blocked'],1)
        now=frame((29,45)); now[61][13]=40
        self.assertNotEqual(x.propose([now],1,ACTIONS),'ACTION4')

    def test_one_observed_circuit_is_not_a_proven_cycle(self):
        x=p.LS20VisualPlanner(); feed(x,1)
        self.assertEqual(x.summary()['level2_v93_cycles_confirmed'],0)
        self.assertEqual(x.summary()['level2_v93_unique_actions_blocked'],0)

    def test_exact_two_circuits_mark_only_next_witnessed_action(self):
        x=p.LS20VisualPlanner(); feed(x)
        self.assertGreaterEqual(x.summary()['level2_v93_cycles_confirmed'],1)
        self.assertEqual(x.summary()['level2_v93_unique_actions_blocked'],1)
        self.assertEqual(len(x._v93_repeated_actions),1)
        candidate = next(iter(x._v93_repeated_actions))
        self.assertEqual(candidate[1],'ACTION4')

    def test_observed_cycle_guard_routes_around_previous_first_move(self):
        x=p.LS20VisualPlanner(); feed(x)
        choice=x.propose([frame((29,45))],1,ACTIONS)
        self.assertIn(choice,ACTIONS)
        self.assertNotEqual(choice,'ACTION4')
        self.assertGreaterEqual(x.summary()['level2_v93_guard_activations'],1)
        self.assertGreaterEqual(x.summary()['level2_v93_detours_selected'],1)

    def test_changed_action_in_second_circuit_does_not_prove_cycle(self):
        x=p.LS20VisualPlanner(); feed(x,change_at=12)
        self.assertEqual(x.summary()['level2_v93_cycles_confirmed'],0)

    def test_single_frame_self_loops_are_not_enough(self):
        x=p.LS20VisualPlanner()
        for i in range(7):
            x.record_frame_transition(observed(frame((29,45))),
              observed(frame((29,45))),'ACTION1',step_index=i)
        self.assertEqual(x.summary()['level2_v93_cycles_confirmed'],0)

    def test_reset_pending_preserves_only_this_run_observations(self):
        x=p.LS20VisualPlanner(); feed(x)
        x.reset_pending()
        self.assertEqual(len(x._v93_repeated_actions),1)
        self.assertEqual(len(x._v93_recent_steps),16)

    def test_other_level_clears_history_and_bans(self):
        x=p.LS20VisualPlanner(); feed(x)
        x.record_frame_transition(observed(frame((29,45))),
             observed(frame((29,45)),level=2),'ACTION1',step_index=17)
        self.assertFalse(x._v93_recent_steps)
        self.assertFalse(x._v93_repeated_actions)

    def test_invalid_frame_cannot_trigger_cycle(self):
        x=p.LS20VisualPlanner()
        for i in range(40):
            x.record_frame_transition(observed([[0]]),observed(frame((29,45))),
                'ACTION1',step_index=i)
        self.assertEqual(x.summary()['level2_v93_observed_steps'],0)
        self.assertEqual(x.summary()['level2_v93_cycles_confirmed'],0)
        self.assertEqual(x.summary()['level2_v93_observation_errors'],0)

    def test_game_over_breaks_history(self):
        x=p.LS20VisualPlanner(); feed(x,1)
        x.record_frame_transition(observed(frame((29,45))),
            observed(frame((34,45)),state='GAME_OVER'),'ACTION4',step_index=9)
        self.assertEqual(len(x._v93_recent_steps),0)

    def test_history_and_bans_are_strictly_bounded(self):
        x=p.LS20VisualPlanner(); feed(x,9)
        self.assertLessEqual(len(x._v93_recent_steps),48)
        self.assertLessEqual(len(x._v93_repeated_actions),8)
        report=x.summary()
        self.assertNotIn('_v93_recent_steps',report)
        self.assertNotIn('_v93_repeated_actions',report)

    def test_only_observed_not_inferred_future_actions_are_blocked(self):
        x=p.LS20VisualPlanner(); x.propose([frame((29,45))],1,ACTIONS)
        self.assertEqual(len(x._v93_repeated_actions),0)


if __name__=='__main__':
    unittest.main()
