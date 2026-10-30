"""Keyboard frame-aware ARC-AGI-3 exploration agent.

FeedbackExplorer V9.0 observed transition learning and loop-avoidance experiment:
- Preserve V3 balanced action exploration.
- Preserve V4 LS20 action compatibility (ACTION1 through ACTION4).
- Preserve V5 immediate reverse movement prevention for LS20.
- Preserve V6 LS20 step-counter HUD masking.
- Retain V7 graph navigation; optionally prefer visible LS20 goal paths.
- Enable conservatively validated LS20 level-2 visible planning.
- Preserve other games' default policy and real diagnostics.

This agent explores the game but does not guarantee a solution.
"""

from typing import Any

from arcengine import FrameData, GameAction, GameState

from ..agent import Agent
from .feedback_policy import FeedbackPolicy, observation_key
from .feedback_diagnostics_v2 import FeedbackDiagnosticsV2
from .ls20_visual_planner import LS20VisualPlanner
from .ls20_level2_frame_capture import LS20Level2FrameCapture


class FeedbackExplorer(Agent):
    """Explore keyboard games and record observed outcomes."""

    AGENT_VERSION = "9.2"

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
        # Agent.main() runs while action_counter <= MAX_ACTIONS; therefore
        # 179 permits at most 180 actions. Preserve 81-action behavior in
        # other games, where MAX_ACTIONS stays at 80.
        if self._mask_ls20_step_counter:
            self.MAX_ACTIONS = 179

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

        # Existing V4 tests execute the constructor with dependency stubs.
        # In production the imported planner is always available.
        planner_class = globals().get("LS20VisualPlanner")
        self._ls20_visual_planner = (
            planner_class()
            if self._mask_ls20_step_counter and planner_class is not None
            else None
        )
        self.diagnostics = FeedbackDiagnosticsV2(
            policy=self.policy
        )
        self.diagnostics.visual_planner = self._ls20_visual_planner

        # Capture level-2 evidence without modifying recorded frames.
        capture_class = globals().get("LS20Level2FrameCapture")
        self._ls20_level2_capture = (
            capture_class()
            if self._mask_ls20_step_counter and capture_class is not None
            else None
        )
        self.diagnostics.level2_frame_capture = self._ls20_level2_capture

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
            if self._ls20_visual_planner is not None:
                self._ls20_visual_planner.reset_pending()

            action = GameAction.RESET
            action.reasoning = (
                "FeedbackExplorer V9.2: start or restart game"
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

        if self._ls20_level2_capture is not None:
            self._ls20_level2_capture.observe(
                latest_frame.frame,
                level=latest_frame.levels_completed,
            )

        # V8.4: only on LS20 level 2, allow a validated pixel-based route
        # to suggest a necessary reverse move. Other levels retain the V8.3
        # reverse guard, and all non-visual choices use the legacy policy.
        allowed_actions = self.policy._candidate_actions()
        level2_visual = (
            self._ls20_visual_planner is not None
            and latest_frame.levels_completed == 1
        )
        planner_candidates = (
            getattr(self.policy, "actions", tuple(allowed_actions))
            if level2_visual else allowed_actions
        )
        proposed = None
        if self._ls20_visual_planner is not None:
            proposed = self._ls20_visual_planner.propose(
                latest_frame.frame,
                latest_frame.levels_completed,
                planner_candidates,
            )

        # V9.0: do not silently fall back to another historically failed
        # exit when all four exits from an EXACT rendered switch frame failed.
        if level2_visual and getattr(self._ls20_visual_planner, 'v90_request_reset', False):
            self.policy.clear_pending()
            self._ls20_visual_planner.reset_pending()
            action = GameAction.RESET
            action.reasoning = 'FeedbackExplorer V9.2: observed switch exit dead-end; reset to explore alternative approach'
            return action

        reverse_override = bool(
            level2_visual
            and proposed is not None
            and proposed not in allowed_actions
            and proposed in planner_candidates
        )
        if proposed is not None:
            # Pass the new option only when actually required, maintaining
            # compatibility with existing policy/test adapter signatures.
            preference_options = (
                {"allow_preferred_reverse": True} if reverse_override else {}
            )
            action_name = self.policy.choose(
                key,
                latest_frame.levels_completed,
                preferred_action=proposed,
                **preference_options,
            )
        else:
            action_name = self.policy.choose(
                key,
                latest_frame.levels_completed,
            )

        if self._ls20_visual_planner is not None:
            report = getattr(self._ls20_visual_planner, "record_choice", None)
            if callable(report):
                report(proposed, action_name, reverse_override=reverse_override)

        action = GameAction.from_name(action_name)
        action.reasoning = (
            f"FeedbackExplorer V9.2: {action_name}; "
            f"state_visits={self.policy.visits[key]}; "
            f"trials={self.policy.attempts[(key, action_name)]}; "
            f"avoid_reverse={self.policy.avoid_immediate_reverse}; "
            f"mask_ls20_step_counter={self._mask_ls20_step_counter}; "
            f"navigation={getattr(self.policy, 'enable_navigation', False)}; "
            f"visible_goal_plan={proposed is not None}"
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
            # V8.8 read-only action boundary: actual returned frame.
            planner = self._ls20_visual_planner
            if planner is not None:
                observe = getattr(planner, "record_frame_transition", None)
                if callable(observe):
                    observe(before, after, action.name, step_index=self.action_counter + 1)
            self.diagnostics.record_action(
                action=action.name,
                before_frame=before.frame,
                after_frame=after.frame,
                before_levels=before.levels_completed,
                after_levels=after.levels_completed,
                after_state=after.state.name,
            )

        return after
