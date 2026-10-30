"""Tests for the actual V9.7 Preview-only activation gate."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class V97PreviewGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = (
            Path(__file__).resolve().parents[1]
            / "agents/templates/feedback_explorer.py"
        )
        tree = ast.parse(path.read_text(encoding="utf-8"))
        agent = next(
            n for n in tree.body
            if isinstance(n, ast.ClassDef)
            and n.name == "FeedbackExplorer"
        )
        constructor = next(
            n for n in agent.body
            if isinstance(n, ast.FunctionDef)
            and n.name == "__init__"
        )

        gates = [
            n for n in constructor.body
            if isinstance(n, ast.If)
            and any(
                isinstance(a, ast.Assign)
                and any(
                    isinstance(t, ast.Attribute)
                    and t.attr == "enable_v97_bounded_retry"
                    for t in a.targets
                )
                for a in ast.walk(n)
            )
        ]
        assert len(gates) == 1, "Expected exactly one V9.7 gate."
        module = ast.fix_missing_locations(
            ast.Module(body=gates, type_ignores=[])
        )
        cls.gate_code = compile(module, str(path), "exec")

    def run_gate(self, environment="preview", flag="1",
                 ls20=True, has_planner=True):
        planner = (
            SimpleNamespace(enable_v97_bounded_retry=False)
            if has_planner else None
        )
        agent = SimpleNamespace(
            _mask_ls20_step_counter=ls20,
            _ls20_visual_planner=planner,
        )
        values = {
            "VERCEL_ENV": environment,
            "ARC_V97_BOUNDED_RETRY": flag,
        }
        exec(
            self.gate_code,
            {
                "self": agent,
                "os": SimpleNamespace(getenv=values.get),
            },
        )
        return (
            planner.enable_v97_bounded_retry
            if planner is not None else None
        )

    def test_preview_explicit_opt_in_enables(self):
        self.assertTrue(self.run_gate())

    def test_preview_without_flag_remains_disabled(self):
        self.assertFalse(self.run_gate(flag=None))

    def test_preview_wrong_flag_remains_disabled(self):
        self.assertFalse(self.run_gate(flag="true"))

    def test_production_with_flag_remains_disabled(self):
        self.assertFalse(self.run_gate(environment="production"))

    def test_development_with_flag_remains_disabled(self):
        self.assertFalse(self.run_gate(environment="development"))

    def test_other_games_remain_disabled(self):
        self.assertFalse(self.run_gate(ls20=False))

    def test_missing_planner_does_not_enable(self):
        self.assertIsNone(self.run_gate(has_planner=False))


if __name__ == "__main__":
    unittest.main()
