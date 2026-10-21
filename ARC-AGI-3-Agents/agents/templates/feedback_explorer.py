"""Keyboard frame-aware ARC-AGI-3 exploration agent.

FeedbackExplorer V7:
- Preserve V3 balanced action exploration.
- Preserve V4 LS20 action compatibility (ACTION1 through ACTION4).
- Preserve V5 immediate reverse movement prevention for LS20.
- Preserve V6 LS20 step-counter HUD masking.
- Enable V7 observed-state graph navigation for LS20 only.
- Preserve other games' default policy and real diagnostics.

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

        self._mask_ls20_step_counter = (
            self.game_id == "ls20-9607627b"
        )

        if self._mask_ls20_step_counter:
            self.policy = FeedbackPolicy(
                actions=(
                    "ACTION1",
                    "ACTION2",
                    "ACTION3",
                    "ACTION4",
                )
            )
            # Keep assignments compatible with V4 constructor test stubs.
            self.policy.avoid_immediate_reverse = True
            self.policy.enable_navigation = True

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
        """Stop only when the game reports WIN."""
        return latest_frame.state is GameState.WIN

    def choose_action(
        self,
        frames: list[FrameData],
        latest_frame: FrameData,
    ) -> GameAction:
        """Choose an action from real feedback and observed game state."""
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
                        mask_ls20_step_counter=(
                            self._mask_ls20_step_counter
                        ),
                    ),
                    latest_frame.levels_completed,
                    state.name,
                )

            self.policy.clear_pending()
            action = GameAction.RESET
            action.reasoning = (
                "FeedbackExplorer V7: start or restart game"
            )
            return action

        key = observation_key(
            latest_frame.frame,
            latest_frame.levels_completed,
            state.name,
            mask_ls20_step_counter=(
                self._mask_ls20_step_counter
            ),
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
            f"FeedbackExplorer V7: {action_name}; "
            f"state_visits={self.policy.visits[key]}; "
            f"trials={self.policy.attempts[(key, action_name)]}; "
            f"avoid_reverse={self.policy.avoid_immediate_reverse}; "
            f"mask_ls20_step_counter={self._mask_ls20_step_counter}; "
            f"navigation={getattr(self.policy, 'enable_navigation', False)}"
        )
        return action

    def take_action(
        self,
        action: GameAction,
    ) -> FrameData | None:
        """Execute a real action and record its unmodified outcome."""
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
