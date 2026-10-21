"""FeedbackExplorer V5 regression and action-selection tests.

Run without the ARC game engine.
"""

import ast
import importlib.util
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

POLICY_PATH = (
    ROOT / "agents" / "templates" / "feedback_policy.py"
)

EXPLORER_PATH = (
    ROOT / "agents" / "templates" / "feedback_explorer.py"
)


spec = importlib.util.spec_from_file_location(
    "feedback_policy_v5_test",
    POLICY_PATH,
)
assert spec is not None and spec.loader is not None

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

FeedbackPolicy = module.FeedbackPolicy
KEYBOARD_ACTIONS = module.KEYBOARD_ACTIONS
OPPOSITE_ACTIONS = module.OPPOSITE_ACTIONS


class StubAgent:
    def __init__(self, *, game_id: str):
        self.game_id = game_id


class StubDiagnostics:
    def __init__(self, *, policy):
        self.policy = policy


def load_explorer_class():
    """Test the real agent constructor using lightweight stubs."""

    tree = ast.parse(
        EXPLORER_PATH.read_text(encoding="utf-8")
    )

    agent_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "FeedbackExplorer"
    )

    constructor = next(
        node
        for node in agent_class.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "__init__"
    )

    agent_class.bases = [
        ast.Name(id="StubAgent", ctx=ast.Load())
    ]
    agent_class.body = [constructor]
    agent_class.decorator_list = []

    namespace = {
        "Any": Any,
        "StubAgent": StubAgent,
        "FeedbackPolicy": FeedbackPolicy,
        "FeedbackDiagnosticsV2": StubDiagnostics,
    }

    test_module = ast.Module(
        body=[agent_class],
        type_ignores=[],
    )

    exec(
        compile(
            ast.fix_missing_locations(test_module),
            str(EXPLORER_PATH),
            "exec",
        ),
        namespace,
    )

    return namespace["FeedbackExplorer"]


class FeedbackPolicyV5Tests(unittest.TestCase):

    def test_ls20_enables_reverse_prevention(self):
        agent_class = load_explorer_class()

        agent = agent_class(
            game_id="ls20-9607627b"
        )

        self.assertEqual(
            agent.policy.actions,
            (
                "ACTION1",
                "ACTION2",
                "ACTION3",
                "ACTION4",
            ),
        )

        self.assertTrue(
            agent.policy.avoid_immediate_reverse
        )

        self.assertNotIn(
            "ACTION5",
            agent.policy.actions,
        )

        self.assertIs(
            agent.diagnostics.policy,
            agent.policy,
        )

    def test_other_games_keep_default_behavior(self):
        agent_class = load_explorer_class()

        agent = agent_class(
            game_id="tr87-cd924810"
        )

        self.assertEqual(
            agent.policy.actions,
            KEYBOARD_ACTIONS,
        )

        self.assertFalse(
            agent.policy.avoid_immediate_reverse
        )

    def test_v3_balancing_is_preserved_by_default(self):
        policy = FeedbackPolicy()

        selected = []

        for step in range(5):
            screen = f"default-screen-{step}"

            policy.observe(
                screen, 0, "IN_PROGRESS"
            )

            selected.append(
                policy.choose(screen, 0)
            )

        self.assertEqual(
            selected,
            list(KEYBOARD_ACTIONS),
        )

    def test_immediate_reverse_is_avoided(self):
        policy = FeedbackPolicy(
            actions=(
                "ACTION1",
                "ACTION2",
                "ACTION3",
                "ACTION4",
            ),
            avoid_immediate_reverse=True,
        )

        selected = []

        for step in range(40):
            screen = f"unique-screen-{step}"

            policy.observe(
                screen, 0, "IN_PROGRESS"
            )

            action = policy.choose(
                screen, 0
            )

            if selected:
                previous = selected[-1]

                self.assertNotEqual(
                    action,
                    OPPOSITE_ACTIONS[previous],
                )

            selected.append(action)

        self.assertEqual(
            set(selected),
            set(policy.actions),
        )

    def test_reset_clears_movement_memory(self):
        policy = FeedbackPolicy(
            actions=("ACTION1", "ACTION2"),
            avoid_immediate_reverse=True,
        )

        policy.observe("screen-a", 0, "IN_PROGRESS")

        self.assertEqual(
            policy.choose("screen-a", 0),
            "ACTION1",
        )

        policy.clear_pending()

        self.assertIsNone(
            policy._last_action
        )

        policy.observe("screen-b", 0, "IN_PROGRESS")

        self.assertEqual(
            policy.choose("screen-b", 0),
            "ACTION2",
        )

    def test_level_progress_resets_direction(self):
        policy = FeedbackPolicy(
            actions=("ACTION1", "ACTION2"),
            avoid_immediate_reverse=True,
        )

        policy.observe("level-1", 0, "IN_PROGRESS")

        self.assertEqual(
            policy.choose("level-1", 0),
            "ACTION1",
        )

        policy.observe("level-2", 1, "IN_PROGRESS")

        self.assertEqual(
            policy.reward_sum[("level-1", "ACTION1")],
            20.0,
        )

        self.assertIsNone(
            policy._last_action
        )

        self.assertEqual(
            policy.choose("level-2", 1),
            "ACTION2",
        )

    def test_noop_receives_negative_reward(self):
        policy = FeedbackPolicy(
            actions=(
                "ACTION1",
                "ACTION2",
                "ACTION3",
            ),
            avoid_immediate_reverse=True,
        )

        policy.observe("same-screen", 0, "IN_PROGRESS")

        self.assertEqual(
            policy.choose("same-screen", 0),
            "ACTION1",
        )

        policy.observe("same-screen", 0, "IN_PROGRESS")

        self.assertEqual(
            policy.reward_sum[
                ("same-screen", "ACTION1")
            ],
            -2.0,
        )

        self.assertEqual(
            policy.choose("same-screen", 0),
            "ACTION3",
        )

    def test_reverse_filter_keeps_valid_fallback(self):
        policy = FeedbackPolicy(
            actions=("ACTION1", "ACTION2"),
            avoid_immediate_reverse=True,
        )

        policy.observe("a", 0, "IN_PROGRESS")

        self.assertEqual(
            policy.choose("a", 0),
            "ACTION1",
        )

        policy.observe("b", 0, "IN_PROGRESS")

        self.assertEqual(
            policy.choose("b", 0),
            "ACTION1",
        )


if __name__ == "__main__":
    unittest.main()
