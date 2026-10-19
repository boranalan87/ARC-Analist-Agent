"""Tests for the runtime diagnostics collector."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


RUNTIME_PATH = (
    Path(__file__).resolve().parents[2]
    / "runtime"
    / "main.py"
)

source_tree = ast.parse(
    RUNTIME_PATH.read_text(encoding="utf-8")
)

collector_node = next(
    node for node in source_tree.body
    if isinstance(node, ast.FunctionDef)
    and node.name == "collect_diagnostics"
)

namespace = {}
module = ast.fix_missing_locations(
    ast.Module(body=[collector_node], type_ignores=[])
)
exec(compile(module, str(RUNTIME_PATH), "exec"), namespace)

collect_diagnostics = namespace["collect_diagnostics"]


class RuntimeDiagnosticsTests(unittest.TestCase):

    def test_feedbackexplorer_returns_summary(self):
        expected = {"recorded_actions": 5}

        agent = SimpleNamespace(
            game_id="ls20",
            diagnostics=SimpleNamespace(
                summary=lambda: expected
            ),
        )
        swarm = SimpleNamespace(agents=[agent])

        self.assertEqual(
            collect_diagnostics(
                swarm, "feedbackexplorer", "ls20"
            ),
            expected,
        )

    def test_random_agent_returns_none(self):
        swarm = SimpleNamespace(agents=[])

        self.assertIsNone(
            collect_diagnostics(swarm, "random", "ls20")
        )

    def test_missing_tracker_returns_none(self):
        agent = SimpleNamespace(game_id="ls20")
        swarm = SimpleNamespace(agents=[agent])

        self.assertIsNone(
            collect_diagnostics(
                swarm, "feedbackexplorer", "ls20"
            )
        )

    def test_wrong_game_returns_none(self):
        agent = SimpleNamespace(
            game_id="other-game",
            diagnostics=SimpleNamespace(
                summary=lambda: {"recorded_actions": 5}
            ),
        )
        swarm = SimpleNamespace(agents=[agent])

        self.assertIsNone(
            collect_diagnostics(
                swarm, "feedbackexplorer", "ls20"
            )
        )


if __name__ == "__main__":
    unittest.main()
