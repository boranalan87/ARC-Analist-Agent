"""Keyboard frame-aware ARC-AGI-3 exploration agent.

FeedbackExplorer V5:
- Preserve V3 balanced action exploration.
- Preserve V4 LS20 action compatibility.
- Avoid immediate reverse movements in LS20.
- Preserve default behavior for other games.
- Keep real diagnostics and level measurements.

This agent explores the game but does not guarantee a solution.
"""

from typing import Any

from arcengine import FrameData, GameAction, GameState

from ..agent import Agent
from .feedback_policy import FeedbackPolicy, observation_key
from .feedback_diagnostics_v2 import FeedbackDiagnosticsV2


class FeedbackExplorer(Agent):
    """Explore keyboard games and record observed outcomes."""

    MAX_ACTIONS = 80

    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        # V4: LS20 supports ACTION1 through ACTION4 only.
        # V5: Avoid immediate reverse movements in LS20.
        if self.game_id == "ls20-9607627b":
            self.policy = FeedbackPolicy(
                actions=(
                    "ACTION1",
                    "ACTION2",
                    "ACTION3",
                    "ACTION4",
                )
            )

            # Enable V5 behavior while preserving
            # compatibility with existing V4 test stubs.
            self.policy.avoid_immediate_reverse = True

        else:
            # Preserve the default policy for other games.
            self.policy = FeedbackPolicy()

        # Diagnostics must use the active policy instance.
        self.diagnostics = FeedbackDiagnosticsV2(
            policy=self.policy
        )

    def is_done(
        self,
        frames: list[FrameData],
        latest_frame: FrameData,
    ) -> bool:
        """Stop only when the game reports WIN."""

        return latest_frame.state is GameState.WIN

    def choose_action(
        self,
        frames: list[FrameData],
        latest_frame: FrameData,
    ) -> GameAction:
        """Choose an action using the active feedback policy."""

        state = latest_frame.state

        if state in (
            GameState.NOT_PLAYED,
            GameState.GAME_OVER,
        ):
            if state is GameState.GAME_OVER:
                self.policy.observe(
                    observation_key(
                        latest_frame.frame,
                        latest_frame.levels_completed,
                        state.name,
                    ),
                    latest_frame.levels_completed,
                    state.name,
                )

            # Clear pending feedback and reverse-movement memory.
            self.policy.clear_pending()

            action = GameAction.RESET
            action.reasoning = (
                "FeedbackExplorer V5: start or restart game"
            )

            return action

        # Identify the current observed game state.
        key = observation_key(
            latest_frame.frame,
            latest_frame.levels_completed,
            state.name,
        )

        # Evaluate the previous action using real feedback.
        self.policy.observe(
            key,
            latest_frame.levels_completed,
            state.name,
        )

        # Select an action from the configured action set.
        action_name = self.policy.choose(
            key,
            latest_frame.levels_completed,
        )

        action = GameAction.from_name(action_name)

        # Record meaningful information about the decision.
        action.reasoning = (
            f"FeedbackExplorer V5: {action_name}; "
            f"state_visits={self.policy.visits[key]}; "
            f"trials={self.policy.attempts[(key, action_name)]}; "
            f"avoid_reverse="
            f"{self.policy.avoid_immediate_reverse}"
        )

        return action

    def take_action(
        self,
        action: GameAction,
    ) -> FrameData | None:
        """Execute an action and record its real outcome."""

        before = self.frames[-1]

        after = super().take_action(action)

        if after is not None:
            self.diagnostics.record_action(
                action=action.name,
                before_frame=before.frame,
                after_frame=after.frame,
                before_levels=before.levels_completed,
                after_levels=after.levels_completed,
                after_state=after.state.name,
            )

        return after
