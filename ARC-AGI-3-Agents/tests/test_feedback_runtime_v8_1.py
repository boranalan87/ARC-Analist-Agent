"""FeedbackExplorer V8.3 runtime compatibility tests.

Verify the actual agent version, runtime probe behavior,
visible-planner diagnostics, and backward compatibility.

These tests do not require the ARC game engine,
API credentials, or a running server.
"""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]

RUNTIME_PATH = ROOT.parent / "runtime" / "main.py"

EXPLORER_PATH = (
    ROOT
    / "agents"
    / "templates"
    / "feedback_explorer.py"
)


def load_runtime_probe():
    """Load only the real runtime probe function."""

    source = RUNTIME_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    probe_node = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "collect_agent_runtime_probe"
        ),
        None,
    )

    if probe_node is None:
        raise AssertionError(
            "Runtime probe function was not found."
        )

    module = ast.Module(
        body=[probe_node],
        type_ignores=[],
    )

    namespace = {}

    exec(
        compile(
            ast.fix_missing_locations(module),
            str(RUNTIME_PATH),
            "exec",
        ),
        namespace,
    )

    return namespace["collect_agent_runtime_probe"]


probe = load_runtime_probe()


class RuntimeProbeV83Tests(unittest.TestCase):

    def test_reports_v83_agent_and_level2_diagnostics(self):
        """V8.3 information must come from the actual agent."""

        class ActualAgent:
            AGENT_VERSION = "8.3"
            game_id = "ls20"

            policy = SimpleNamespace(
                navigation_summary=lambda: {
                    "navigation_decisions": 3,
                    "navigation_fallbacks": 2,
                }
            )

            _ls20_visual_planner = SimpleNamespace(
                summary=lambda: {
                    "enabled": True,
                    "proposed_actions": 12,
                    "fallbacks": 5,
                    "level2_proposed_actions": 4,
                    "level2_fallbacks": 2,
                    "last_reason": "rotation_required",
                }
            )

            diagnostics = SimpleNamespace()

        result = probe(
            SimpleNamespace(agents=[ActualAgent()]),
            "feedbackexplorer",
            "ls20",
        )

        self.assertTrue(result["agent_found"])
        self.assertEqual(result["agent_version"], "8.3")
        self.assertEqual(result["agent_class"], "ActualAgent")
        self.assertTrue(result["planner_attached"])

        navigation = result["navigation"]

        self.assertEqual(
            navigation["navigation_decisions"],
            3,
        )

        planning = result["visible_goal_planning"]

        self.assertEqual(
            planning["proposed_actions"],
            12,
        )
        self.assertEqual(
            planning["fallbacks"],
            5,
        )
        self.assertEqual(
            planning["level2_proposed_actions"],
            4,
        )
        self.assertEqual(
            planning["level2_fallbacks"],
            2,
        )
        self.assertEqual(
            planning["last_reason"],
            "rotation_required",
        )

    def test_preserves_legacy_v81_agent_reporting(self):
        """The runtime probe must still report older versions."""

        agent = SimpleNamespace(
            AGENT_VERSION="8.1",
            game_id="ls20",
            policy=None,
            _ls20_visual_planner=None,
            diagnostics=None,
        )

        result = probe(
            SimpleNamespace(agents=[agent]),
            "feedbackexplorer",
            "ls20",
        )

        self.assertTrue(result["agent_found"])
        self.assertEqual(result["agent_version"], "8.1")
        self.assertFalse(result["planner_attached"])
        self.assertIsNone(result["navigation"])
        self.assertIsNone(result["visible_goal_planning"])

    def test_absent_planner_is_reported_explicitly(self):
        """Missing diagnostic components must not be invented."""

        agent = SimpleNamespace(game_id="ls20")

        result = probe(
            SimpleNamespace(agents=[agent]),
            "feedbackexplorer",
            "ls20",
        )

        self.assertTrue(result["agent_found"])
        self.assertFalse(result["planner_attached"])
        self.assertIsNone(result["navigation"])
        self.assertIsNone(result["visible_goal_planning"])
        self.assertIsNone(result["agent_version"])

    def test_wrong_game_is_not_reported_as_found(self):
        agent = SimpleNamespace(game_id="other")

        result = probe(
            SimpleNamespace(agents=[agent]),
            "feedbackexplorer",
            "ls20",
        )

        self.assertFalse(result["agent_found"])

    def test_other_agent_types_are_not_probed(self):
        result = probe(
            SimpleNamespace(agents=[]),
            "random",
            "ls20",
        )

        self.assertIsNone(result)

    def test_loaded_explorer_declares_v83(self):
        """Check the actual source rather than a hardcoded stub."""

        source = EXPLORER_PATH.read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)

        cls = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "FeedbackExplorer"
        )

        versions = [
            node.value.value
            for node in cls.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "AGENT_VERSION"
                for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
        ]

        self.assertEqual(versions, ["9.5"])

    def test_runtime_version_and_probe_are_preserved(self):
        """Changing agent version must not alter API metadata."""

        source = RUNTIME_PATH.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            '"runtime_version": "0.5.1"',
            source,
        )
        self.assertIn(
            '"runtime_probe": runtime_probe',
            source,
        )
        self.assertIn(
            'diagnostics["runtime_probe_v8_1"] = runtime_probe',
            source,
        )

    def test_runtime_does_not_expose_secret_token(self):
        source = RUNTIME_PATH.read_text(
            encoding="utf-8"
        )

        self.assertNotIn(
            '"runtime_token": ARC_RUNTIME_TOKEN',
            source,
        )


if __name__ == "__main__":
    unittest.main()
