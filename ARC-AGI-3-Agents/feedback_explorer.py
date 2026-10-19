"""Feedback-driven exploration baseline for keyboard-controlled ARC-AGI-3 games.

Unlike a random policy, this agent remembers screen states and action results.
It explores untried actions at each observed state and uses known paths to
return to states that still offer unexplored actions.

This is a non-LLM exploration baseline, NOT a trained solver and it does not
claim to infer the game's goals or mechanics.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import deque
from typing import Any

from arcengine import FrameData, GameAction, GameState

from ..agent import Agent


class FeedbackExplorer(Agent):
    """Explore the observed state graph, prioritizing new action outcomes."""

    MAX_ACTIONS = 80
    DIRECTIONS = (
        GameAction.ACTION1,
        GameAction.ACTION2,
        GameAction.ACTION3,
        GameAction.ACTION4,
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        seed = int.from_bytes(
            hashlib.blake2b(self.game_id.encode("utf-8"), digest_size=8).digest(),
            "big",
        )
        self._rng = random.Random(seed)
        self._level = 0
        self._reset_exploration()

    @property
    def name(self) -> str:
        return f"{super().name}.{self.MAX_ACTIONS}"

    def _reset_exploration(self) -> None:
        self._visits: dict[str, int] = {}
        self._tried: dict[str, set[GameAction]] = {}
        self._edges: dict[str, dict[GameAction, str]] = {}
        self._previous: tuple[str, GameAction] | None = None

    @staticmethod
    def _state_key(frame: FrameData) -> str:
        # Pixel-grid observation only. The level is tracked separately.
        # The last grid is the final screen when a frame contains several grids.
        grid = frame.frame[-1] if frame.frame else []
        blob = json.dumps(grid, separators=(",", ":")).encode("utf-8")
        return hashlib.blake2b(blob, digest_size=12).hexdigest()

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return latest_frame.state is GameState.WIN

    def _nearest_frontier_action(self, start: str) -> GameAction | None:
        """BFS toward a previously seen state with a direction left to try."""
        queue: deque[tuple[str, GameAction | None]] = deque([(start, None)])
        seen = {start}
        while queue:
            state, first = queue.popleft()
            if first is not None and any(
                action not in self._tried.get(state, set())
                for action in self.DIRECTIONS
            ):
                return first
            for action, next_state in self._edges.get(state, {}).items():
                if next_state not in seen:
                    seen.add(next_state)
                    queue.append((next_state, first or action))
        return None

    def _choose_direction(self, state: str) -> tuple[GameAction, str]:
        tried = self._tried.setdefault(state, set())
        untried = [action for action in self.DIRECTIONS if action not in tried]
        if untried:
            # Randomize tie-breaks reproducibly, but don't repeat an untried
            # direction until the others at this observation have been tried.
            return self._rng.choice(untried), "untried direction at this screen"

        frontier = self._nearest_frontier_action(state)
        if frontier is not None:
            return frontier, "route to an observed unexplored screen"

        # No reachable frontier: prefer a transition toward a less-visited
        # state. In a dynamic game, all screens may be new, so this is fallback.
        edges = self._edges.get(state, {})
        candidates = list(self.DIRECTIONS)
        self._rng.shuffle(candidates)
        direction = min(
            candidates,
            key=lambda action: (
                self._visits.get(edges.get(action, state), 0),
                int(edges.get(action, state) == state),
            ),
        )
        return direction, "least-visited known outcome"

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            self._reset_exploration()
            self._level = latest_frame.levels_completed
            action = GameAction.RESET
            action.reasoning = "Start or restart the game"
            return action

        if latest_frame.levels_completed != self._level:
            self._reset_exploration()
            self._level = latest_frame.levels_completed

        state = self._state_key(latest_frame)
        self._visits[state] = self._visits.get(state, 0) + 1

        if self._previous is not None:
            previous_state, previous_action = self._previous
            self._tried.setdefault(previous_state, set()).add(previous_action)
            self._edges.setdefault(previous_state, {})[previous_action] = state

        action, reason = self._choose_direction(state)
        self._previous = (state, action)
        action.reasoning = {
            "policy": "feedback_explorer_v1",
            "reason": reason,
            "screen_visits": self._visits[state],
            "known_screen_states": len(self._visits),
        }
        return action
