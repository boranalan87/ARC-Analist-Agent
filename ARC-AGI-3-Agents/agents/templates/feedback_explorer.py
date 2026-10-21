"""Keyboard frame-aware ARC-AGI-3 exploration agent.

FeedbackExplorer V4:
Use the supported action set for LS20 while preserving
the default exploration policy for other games.
"""

from typing import Any

from arcengine import FrameData, GameAction, GameState

from ..agent import Agent
from .feedback_policy import FeedbackPolicy, observation_key
from .feedback_diagnostics_v2 import FeedbackDiagnosticsV2


class FeedbackExplorer(Agent):
    """Explore keyboard games and record action outcomes."""

    MAX_ACTIONS = 80

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # V4: LS20 supports only ACTION1 through ACTION4.
        # Preserve the existing default policy for other games.
        if self.game_id == "ls20-9607627b":
            self.policy = FeedbackPolicy(
                actions=(
                    "ACTION1",
                    "ACTION2",
                    "ACTION3",
                    "ACTION4",
                )
            )
        else:
            self.policy = FeedbackPolicy()

        self.diagnostics = FeedbackDiagnosticsV2(
            policy=self.policy
        )

    def is_done(
        self,
        frames: list[FrameData],
        latest_frame: FrameData,
    ) -> bool:
        return latest_frame.state is GameState.WIN

    def choose_action(
        self,
        frames: list[FrameData],
        latest_frame: FrameData,
    ) -> GameAction:

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

            self.policy.clear_pending()

            action = GameAction.RESET
            action.reasoning = "Start or restart game"
            return action

        key = observation_key(
            latest_frame.frame,
            latest_frame.levels_completed,
            state.name,
        )

        self.policy.observe(
            key,
            latest_frame.levels_completed,
            state.name,
        )

        action_name = self.policy.choose(
            key,
            latest_frame.levels_completed,
        )

        action = GameAction.from_name(action_name)

        action.reasoning = (
            f"FeedbackExplorer V4: {action_name}; "
            f"state_visits={self.policy.visits[key]}; "
            f"trials={self.policy.attempts[(key, action_name)]}"
        )

        return action

    def take_action(
        self,
        action: GameAction,
    ) -> FrameData | None:
        """Execute action and collect its observed outcome."""

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
