"""Dependency-free feedback policy for the keyboard ARC-AGI-3 baseline.

FeedbackExplorer V3 — balanced action exploration.

This is an exploration policy, not a general ARC game solver.
It uses observed frame changes and level progress to evaluate actions.

Untried actions are selected according to their overall usage across
the current run, avoiding an excessive preference for ACTION1 when
the agent visits previously unseen screens.
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
    "ACTION5",  # game-dependent key
)


def observation_key(
    frame: Sequence[Any],
    levels_completed: int,
    state: str,
) -> str:
    """Generate a stable fingerprint of the current observation.

    FrameData.frame may contain multiple grids representing
    an animation. The last grid represents the latest view.
    """
    final_grid = frame[-1] if frame else []

    raw = repr(
        (state, levels_completed, final_grid)
    ).encode("utf-8")

    return blake2b(
        raw,
        digest_size=16,
    ).hexdigest()


class FeedbackPolicy:
    """Track observed actions and select exploration candidates.

    V3 balances untried actions across the current run.

    Known actions are evaluated using observed rewards,
    destination novelty, exploration bonuses and repeat penalties.

    This policy does not invent level completions or scores.
    """

    def __init__(
        self,
        actions: Sequence[str] = KEYBOARD_ACTIONS,
    ) -> None:

        if not actions or len(set(actions)) != len(actions):
            raise ValueError(
                "Provide distinct nonempty actions"
            )

        self.actions = tuple(actions)

        self.visits: Counter[str] = Counter()

        self.attempts: Counter[
            tuple[str, str]
        ] = Counter()

        self.reward_sum: dict[
            tuple[str, str], float
        ] = defaultdict(float)

        self.next_screen: dict[
            tuple[str, str], str
        ] = {}

        self._pending: (
            tuple[str, str, int] | None
        ) = None

    def clear_pending(self) -> None:
        """Clear a pending action when the game resets."""
        self._pending = None

    def observe(
        self,
        key: str,
        levels_completed: int,
        state: str,
    ) -> None:
        """Evaluate the outcome of the previous action."""

        first_visit = self.visits[key] == 0

        if self._pending is not None:

            old_key, action, old_levels = self._pending

            pair = (old_key, action)

            progressed = (
                levels_completed > old_levels
            )

            if state == "WIN":
                reward = 100.0

            elif progressed:
                reward = 20.0

            elif state == "GAME_OVER":
                reward = -3.0

            elif key == old_key:
                reward = -2.0

            elif first_visit:
                reward = 3.0

            else:
                reward = 0.5

            self.reward_sum[pair] += reward
            self.next_screen[pair] = key

            self._pending = None

        self.visits[key] += 1

    def choose(
        self,
        key: str,
        levels_completed: int,
    ) -> str:
        """Select an action using balanced exploration.

        First try actions not yet used on the current screen.

        Among those actions, prefer the action used least
        frequently across the entire current run.

        Once every action has been tried on the current screen,
        use observed rewards and exploration bonuses.
        """

        unseen = [
            action
            for action in self.actions
            if self.attempts[(key, action)] == 0
        ]

        if unseen:

            # V3: Balance action usage across visited screens.
            # Deterministic tie-breaking preserves repeatability.

            total_usage = Counter()

            for (_, action), count in self.attempts.items():
                total_usage[action] += count

            action = min(
                unseen,
                key=lambda candidate: (
                    total_usage[candidate],
                    self.actions.index(candidate),
                ),
            )

        else:

            def value(action_name: str) -> float:

                pair = (key, action_name)

                count = self.attempts[pair]

                mean_reward = (
                    self.reward_sum[pair] / count
                )

                destination = self.next_screen.get(pair)

                if destination:
                    novelty = (
                        1.5
                        / sqrt(
                            1 + self.visits[destination]
                        )
                    )
                else:
                    novelty = 0.0

                exploration_bonus = (
                    0.5 / sqrt(count)
                )

                repeat_penalty = (
                    0.1 * count
                )

                return (
                    mean_reward
                    + novelty
                    + exploration_bonus
                    - repeat_penalty
                )

            action = max(
                self.actions,
                key=value,
            )

        self.attempts[(key, action)] += 1

        self._pending = (
            key,
            action,
            levels_completed,
        )

        return action
