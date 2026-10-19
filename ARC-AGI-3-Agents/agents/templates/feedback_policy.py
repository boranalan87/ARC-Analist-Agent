"""Dependency-free feedback policy for the keyboard ARC-AGI-3 baseline.

This is an *exploration* policy, not a general ARC game solver. It compares
consecutive observations to prefer actions associated with new states and
avoids repeatedly submitting actions that leave the screen unchanged.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import blake2b
from math import sqrt
from typing import Any, Sequence


KEYBOARD_ACTIONS = (
    "ACTION1",  # up
    "ACTION2",  # down
    "ACTION3",  # left
    "ACTION4",  # right
    "ACTION5",  # game-dependent key (Enter/Space/etc.)
)


def observation_key(frame: Sequence[Any], levels_completed: int, state: str) -> str:
    """Fingerprint the last displayed grid and the relevant game state.

    FrameData.frame is a sequence of grids. Multiple grids can describe a
    short animation; the final one is the current view used for the policy.
    """
    final_grid = frame[-1] if frame else []
    raw = repr((state, levels_completed, final_grid)).encode("utf-8")
    return blake2b(raw, digest_size=16).hexdigest()


class FeedbackPolicy:
    """Small, per-run table of observed (screen, action) outcomes.

    A new action is tried before a known one at a given screen. Once all
    actions have been tried, the policy prefers successful transitions and
    infrequently visited destination screens. No score or win is invented.
    """

    def __init__(self, actions: Sequence[str] = KEYBOARD_ACTIONS) -> None:
        if not actions or len(set(actions)) != len(actions):
            raise ValueError("Provide distinct nonempty actions")
        self.actions = tuple(actions)
        self.visits: Counter[str] = Counter()
        self.attempts: Counter[tuple[str, str]] = Counter()
        self.reward_sum: dict[tuple[str, str], float] = defaultdict(float)
        self.next_screen: dict[tuple[str, str], str] = {}
        self._pending: tuple[str, str, int] | None = None

    def clear_pending(self) -> None:
        """Discard an outstanding transition across an explicit game reset."""
        self._pending = None

    def observe(self, key: str, levels_completed: int, state: str) -> None:
        """Process the *next* observation after the previous chosen action."""
        first_visit = self.visits[key] == 0
        if self._pending is not None:
            old_key, action, old_levels = self._pending
            pair = (old_key, action)
            progressed = levels_completed > old_levels
            if state == "WIN":
                reward = 100.0
            elif progressed:
                reward = 20.0
            elif state == "GAME_OVER":
                reward = -3.0
            elif key == old_key:
                reward = -2.0  # observed no-op
            elif first_visit:
                reward = 3.0  # new visible state
            else:
                reward = 0.5  # moved, but to a known state
            self.reward_sum[pair] += reward
            self.next_screen[pair] = key
            self._pending = None
        self.visits[key] += 1

    def choose(self, key: str, levels_completed: int) -> str:
        """Select the next keyboard action, exploring untried options first."""
        unseen = [a for a in self.actions if self.attempts[(key, a)] == 0]
        if unseen:
            # Fully deterministic to make comparisons and tests reproducible.
            action = unseen[0]
        else:
            def value(a: str) -> float:
                pair = (key, a)
                count = self.attempts[pair]
                mean_reward = self.reward_sum[pair] / count
                destination = self.next_screen.get(pair)
                novelty = 1.5 / sqrt(1 + self.visits[destination]) if destination else 0.0
                exploration_bonus = 0.5 / sqrt(count)
                repeat_penalty = 0.1 * count
                return mean_reward + novelty + exploration_bonus - repeat_penalty

            action = max(self.actions, key=value)

        self.attempts[(key, action)] += 1
        self._pending = (key, action, levels_completed)
        return action
