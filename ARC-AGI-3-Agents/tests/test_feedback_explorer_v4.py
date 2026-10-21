"""FeedbackExplorer V4 action compatibility tests.

These tests do not require the ARC game engine.
"""

import ast
import unittest
from pathlib import Path
from typing import Any


SOURCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "agents"
    / "templates"
    / "feedback_explorer.py"
)

DEFAULT_ACTIONS = (
    "ACTION1",
    "ACTION2",
    "ACTION3",
    "ACTION4",
    "ACTION5",
)

LS20_ACTIONS = DEFAULT_ACTIONS[:4]


class StubAgent:
    def __init__(self, *, game_id: str):
        self.game_id = game_id


class StubPolicy:
    def __init__(self, actions=None):
        self.actions = (
            tuple(actions)
            if actions is not None
            else DEFAULT_ACTIONS
        )


class StubDiagnostics:
    def __init__(self, *, policy):
        self.policy = policy


def load_agent_class():
    """Execute the real agent constructor using lightweight stubs."""

    tree = ast.parse(
        SOURCE_PATH.read_text(encoding="utf-8")
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
        "FeedbackPolicy": StubPolicy,
        "FeedbackDiagnosticsV2": StubDiagnostics,
    }

    module = ast.Module(
        body=[agent_class],
        type_ignores=[],
    )

    exec(
        compile(
            ast.fix_missing_locations(module),
            str(SOURCE_PATH),
            "exec",
        ),
        namespace,
    )

    return namespace["FeedbackExplorer"]


class FeedbackExplorerV4Tests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.agent_class = load_agent_class()

    def test_ls20_uses_only_four_supported_actions(self):
        agent = self.agent_class(
            game_id="ls20-9607627b"
        )

        self.assertEqual(
            agent.policy.actions,
            LS20_ACTIONS,
        )
        self.assertNotIn(
            "ACTION5",
            agent.policy.actions,
        )

    def test_other_games_preserve_default_actions(self):
        agent = self.agent_class(
            game_id="tr87-cd924810"
        )

        self.assertEqual(
            agent.policy.actions,
            DEFAULT_ACTIONS,
        )

    def test_diagnostics_share_the_active_policy(self):
        agent = self.agent_class(
            game_id="ls20-9607627b"
        )

        self.assertIs(
            agent.diagnostics.policy,
            agent.policy,
        )


if __name__ == "__main__":
    unittest.main()
