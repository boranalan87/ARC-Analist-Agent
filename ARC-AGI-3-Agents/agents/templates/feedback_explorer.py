"""Keyboard frame-aware ARC-AGI-3 baseline (no external LLM or API key)."""

from typing import Any

from arcengine import FrameData, GameAction, GameState

from ..agent import Agent
from .feedback_policy import FeedbackPolicy, observation_key


class FeedbackExplorer(Agent):
    """Explore one game's keyboard actions using observed frame changes.

    Intended first for keyboard-only games such as LS20. ACTION6/click games
    require a separate coordinate-selection policy. No claim is made that
    this strategy solves a level; compare actual scorecards against random.
    """

    MAX_ACTIONS = 80  # comparable to existing Random baseline

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.policy = FeedbackPolicy()

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return latest_frame.state is GameState.WIN

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        state = latest_frame.state
        if state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            # Start/restart as required by the environment. Never learn a
            # misleading transition between two unrelated game episodes.
            if state is GameState.GAME_OVER:
                self.policy.observe(
                    observation_key(latest_frame.frame, latest_frame.levels_completed, state.name),
                    latest_frame.levels_completed,
                    state.name,
                )
            self.policy.clear_pending()
            action = GameAction.RESET
            action.reasoning = "Start/restart game after NOT_PLAYED/GAME_OVER"
            return action

        key = observation_key(latest_frame.frame, latest_frame.levels_completed, state.name)
        self.policy.observe(key, latest_frame.levels_completed, state.name)
        action_name = self.policy.choose(key, latest_frame.levels_completed)
        action = GameAction.from_name(action_name)
        action.reasoning = (
            f"FeedbackExplorer: {action_name}; state_visits={self.policy.visits[key]}; "
            f"state_action_trials={self.policy.attempts[(key, action_name)]}"
        )
        return action
