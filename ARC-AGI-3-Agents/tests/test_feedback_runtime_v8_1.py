"""V8.1 tests: the runtime probe reports facts from the actual in-memory agent.

No game engine or runtime credentials are required.
"""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


RUNTIME_PATH = Path(__file__).resolve().parents[2] / "runtime" / "main.py"
EXPLORER_PATH = (
    Path(__file__).resolve().parents[1]
    / "agents" / "templates" / "feedback_explorer.py"
)

tree = ast.parse(RUNTIME_PATH.read_text(encoding="utf-8"))
probe_node = next(
    node for node in tree.body
    if isinstance(node, ast.FunctionDef)
    and node.name == "collect_agent_runtime_probe"
)
namespace = {}
exec(
    compile(
        ast.fix_missing_locations(ast.Module(body=[probe_node], type_ignores=[])),
        str(RUNTIME_PATH), "exec",
    ),
    namespace,
)
probe = namespace["collect_agent_runtime_probe"]


class RuntimeProbeV81Tests(unittest.TestCase):
    def test_reports_actual_planner_navigation_and_version(self):
        class ActualAgent:
            AGENT_VERSION = "8.1"
            game_id = "ls20"
            policy = SimpleNamespace(
                navigation_summary=lambda: {
                    "navigation_decisions": 3, "navigation_fallbacks": 2,
                }
            )
            _ls20_visual_planner = SimpleNamespace(
                summary=lambda: {
                    "proposed_actions": 4, "fallbacks": 5,
                    "last_reason": "pose_not_visible",
                }
            )
            diagnostics = SimpleNamespace()

        result = probe(
            SimpleNamespace(agents=[ActualAgent()]), "feedbackexplorer", "ls20"
        )
        self.assertEqual(result["agent_version"], "8.1")
        self.assertTrue(result["agent_found"])
        self.assertTrue(result["planner_attached"])
        self.assertEqual(result["navigation"]["navigation_decisions"], 3)
        self.assertEqual(result["visible_goal_planning"]["proposed_actions"], 4)
        self.assertEqual(result["visible_goal_planning"]["fallbacks"], 5)
        self.assertEqual(result["agent_class"], "ActualAgent")

    def test_absent_planner_is_explicit_and_not_fabricated(self):
        agent = SimpleNamespace(game_id="ls20")
        result = probe(
            SimpleNamespace(agents=[agent]), "feedbackexplorer", "ls20"
        )
        self.assertFalse(result["planner_attached"])
        self.assertIsNone(result["navigation"])
        self.assertIsNone(result["visible_goal_planning"])
        self.assertIsNone(result["agent_version"])

    def test_wrong_game_is_reported_not_assumed(self):
        agent = SimpleNamespace(game_id="other")
        result = probe(
            SimpleNamespace(agents=[agent]), "feedbackexplorer", "ls20"
        )
        self.assertFalse(result["agent_found"])

    def test_other_agents_are_not_probed(self):
        result = probe(SimpleNamespace(agents=[]), "random", "ls20")
        self.assertIsNone(result)

    def test_loaded_explorer_declares_version(self):
        tree = ast.parse(EXPLORER_PATH.read_text(encoding="utf-8"))
        cls = next(
            item for item in tree.body
            if isinstance(item, ast.ClassDef) and item.name == "FeedbackExplorer"
        )
        versions = [
            node.value.value for node in cls.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "AGENT_VERSION"
                for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
        ]
        self.assertEqual(versions, ["8.1"])

    def test_runtime_version_exposed_without_tokens(self):
        source = RUNTIME_PATH.read_text(encoding="utf-8")
        self.assertIn('"runtime_version": "0.5.1"', source)
        self.assertIn('"runtime_probe": runtime_probe', source)
        self.assertIn('diagnostics["runtime_probe_v8_1"] = runtime_probe', source)
        self.assertNotIn('"runtime_token": ARC_RUNTIME_TOKEN', source)


if __name__ == "__main__":
    unittest.main()
