
"""Tests for FeedbackExplorer V3 balanced action selection."""

import importlib.util
import unittest
from collections import Counter
from pathlib import Path


# Load the real policy without requiring the ARC game engine.
POLICY_PATH = (
    Path(__file__).resolve().parents[1]
    / "agents"
    / "templates"
    / "feedback_policy.py"
)

spec = importlib.util.spec_from_file_location(
    "feedback_policy_v3",
    POLICY_PATH,
)

assert spec is not None
assert spec.loader is not None

policy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy_module)

FeedbackPolicy = policy_module.FeedbackPolicy
KEYBOARD_ACTIONS = policy_module.KEYBOARD_ACTIONS


class FeedbackPolicyV3Tests(unittest.TestCase):

    def test_balanced_exploration_across_new_screens(self):
        """All five actions should receive equal exploration."""

        policy = FeedbackPolicy()
        selected_actions = []

        for step in range(15):
            screen = f"unique-screen-{step}"

            policy.observe(
                screen,
                levels_completed=0,
                state="IN_PROGRESS",
            )

            action = policy.choose(
                screen,
                levels_completed=0,
            )

            selected_actions.append(action)

        counts = Counter(selected_actions)

        # The first five choices should cover all five actions.
        self.assertEqual(
            selected_actions[:5],
            list(KEYBOARD_ACTIONS),
        )

        # After 15 new screens, every action is tried 3 times.
        self.assertEqual(
            set(counts),
            set(KEYBOARD_ACTIONS),
        )

        for action in KEYBOARD_ACTIONS:
            self.assertEqual(counts[action], 3)

    def test_untried_actions_on_same_screen(self):
        """A no-op must not prevent exploring other actions."""

        policy = FeedbackPolicy(
            actions=("ACTION1", "ACTION2", "ACTION3")
        )

        policy.observe("screen-a", 0, "IN_PROGRESS")

        self.assertEqual(
            policy.choose("screen-a", 0),
            "ACTION1",
        )

        # ACTION1 did not change the screen.
        policy.observe("screen-a", 0, "IN_PROGRESS")

        self.assertEqual(
            policy.choose("screen-a", 0),
            "ACTION2",
        )

        policy.observe("screen-a", 0, "IN_PROGRESS")

        self.assertEqual(
            policy.choose("screen-a", 0),
            "ACTION3",
        )

        self.assertEqual(
            policy.reward_sum[("screen-a", "ACTION1")],
            -2.0,
        )


if __name__ == "__main__":
    unittest.main()
