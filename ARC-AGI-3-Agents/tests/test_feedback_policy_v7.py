"""Offline FeedbackExplorer V7 navigation regression tests."""

import ast
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "agents" / "templates" / "feedback_policy.py"
EXPLORER_PATH = ROOT / "agents" / "templates" / "feedback_explorer.py"

spec = importlib.util.spec_from_file_location("feedback_policy_v7_test", POLICY_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
FeedbackPolicy = module.FeedbackPolicy
observation_key = module.observation_key


def train_transition(policy, origin, action, destination, level=0, state="NOT_FINISHED"):
    """Record a transition through real public observe/choose methods."""
    policy.observe(origin, level, "NOT_FINISHED")
    selected = policy.choose(origin, level)
    assert selected == action, (selected, action)
    policy.observe(destination, level, state)
    policy.clear_pending()


class FeedbackPolicyV7Tests(unittest.TestCase):
    def test_navigation_opt_in_keeps_default_disabled(self):
        self.assertFalse(FeedbackPolicy().enable_navigation)

    def test_observation_mask_is_preserved(self):
        one = [[0] * 64 for _ in range(64)]
        two = [[0] * 64 for _ in range(64)]
        two[61][13] = 4
        self.assertEqual(
            observation_key([one], 0, "NOT_FINISHED", mask_ls20_step_counter=True),
            observation_key([two], 0, "NOT_FINISHED", mask_ls20_step_counter=True),
        )
        self.assertNotEqual(
            observation_key([one], 0, "NOT_FINISHED"),
            observation_key([two], 0, "NOT_FINISHED"),
        )

    def test_transition_graph_records_actual_outcomes(self):
        p = FeedbackPolicy(actions=("ACTION1",), enable_navigation=True)
        train_transition(p, "a", "ACTION1", "b")
        train_transition(p, "a", "ACTION1", "c")
        self.assertEqual(p.transition_counts[("a", "ACTION1")]["b"], 1)
        self.assertEqual(p.transition_counts[("a", "ACTION1")]["c"], 1)
        self.assertEqual(p.next_screen[("a", "ACTION1")], "c")
        self.assertEqual(p.navigation_summary()["observed_transition_edges"], 2)

    def test_nearest_frontier_uses_observed_route(self):
        p = FeedbackPolicy(actions=("ACTION1", "ACTION2"), enable_navigation=True)
        # A has tried both actions; B still has an untried action.
        p.visits.update({"A": 5, "B": 2, "C": 8})
        p.state_levels.update({"A": 0, "B": 0, "C": 0})
        p.attempts[("A", "ACTION1")] = 4
        p.attempts[("A", "ACTION2")] = 4
        p.attempts[("B", "ACTION1")] = 1
        p.attempts[("C", "ACTION1")] = 2
        p.attempts[("C", "ACTION2")] = 2
        p.transition_counts[("A", "ACTION1")]["C"] = 2
        p.transition_counts[("A", "ACTION2")]["B"] = 1
        p.reward_sum[("A", "ACTION1")] = 90.0  # tempt reward-only choice
        self.assertEqual(p.choose("A", 0), "ACTION2")
        self.assertEqual(p.navigation_decisions, 1)

    def test_navigation_can_reach_frontier_two_hops_away(self):
        p = FeedbackPolicy(actions=("ACTION1", "ACTION2"), enable_navigation=True)
        p.visits.update({"A": 8, "B": 4, "C": 1})
        p.state_levels.update({"A": 0, "B": 0, "C": 0})
        for s in ("A", "B"):
            for a in p.actions:
                p.attempts[(s, a)] = 1
        p.transition_counts[("A", "ACTION2")]["B"] = 2
        p.transition_counts[("B", "ACTION1")]["C"] = 1
        self.assertEqual(p.choose("A", 0), "ACTION2")

    def test_reverse_protection_holds_for_planned_path(self):
        p = FeedbackPolicy(
            actions=("ACTION1", "ACTION2", "ACTION3", "ACTION4"),
            avoid_immediate_reverse=True,
            enable_navigation=True,
        )
        p.visits.update({"A": 5, "B": 2})
        p.state_levels.update({"A": 0, "B": 0})
        for a in ("ACTION1", "ACTION3", "ACTION4"):
            p.attempts[("A", a)] = 2
        p._last_action = "ACTION1"
        p.transition_counts[("A", "ACTION3")]["B"] = 1
        self.assertEqual(p.choose("A", 0), "ACTION3")
        self.assertNotEqual(p._last_action, "ACTION2")

    def test_terminal_and_cross_level_edges_not_used_for_routes(self):
        p = FeedbackPolicy(actions=("ACTION1", "ACTION2"), enable_navigation=True)
        p.visits.update({"A": 3, "D": 1, "E": 1})
        p.state_levels.update({"A": 0, "D": 0, "E": 1})
        p.terminal_states.add("D")
        for a in p.actions:
            p.attempts[("A", a)] = 1
        p.transition_counts[("A", "ACTION1")]["D"] = 1
        p.transition_counts[("A", "ACTION2")]["E"] = 1
        self.assertIsNone(p._frontier_action("A", 0))

    def test_self_loop_is_penalized_in_fallback(self):
        p = FeedbackPolicy(actions=("ACTION1", "ACTION2"), enable_navigation=True)
        p.visits["A"] = 10
        p.state_levels["A"] = 0
        for a in p.actions:
            p.attempts[("A", a)] = 4
            p.reward_sum[("A", a)] = 0.0
        p.transition_counts[("A", "ACTION1")]["A"] = 4
        self.assertEqual(p.choose("A", 0), "ACTION2")
        self.assertEqual(p.navigation_fallbacks, 1)

    def test_graph_persists_across_pending_reset(self):
        p = FeedbackPolicy(actions=("ACTION1",), enable_navigation=True)
        train_transition(p, "A", "ACTION1", "B")
        p.clear_pending()
        self.assertEqual(p.transition_counts[("A", "ACTION1")]["B"], 1)
        self.assertIsNone(p._last_action)

    def test_non_navigation_v3_balancing_unchanged(self):
        p = FeedbackPolicy()
        picks = []
        for i in range(5):
            key = f"new-{i}"
            p.observe(key, 0, "NOT_FINISHED")
            picks.append(p.choose(key, 0))
        self.assertEqual(picks, list(module.KEYBOARD_ACTIONS))

    def test_explorer_enables_navigation_only_for_ls20(self):
        tree = ast.parse(EXPLORER_PATH.read_text(encoding="utf-8"))
        clazz = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "FeedbackExplorer")
        init = next(n for n in clazz.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
        self.assertTrue(any(
            isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Attribute) and t.attr == "enable_navigation"
                for t in n.targets
            ) for n in ast.walk(init)
        ))


if __name__ == "__main__":
    unittest.main()
