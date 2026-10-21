"""Dependency-free feedback policy for keyboard ARC-AGI-3 games.

FeedbackExplorer V5:
- Preserve V3 balanced exploration.
- Preserve rewards based on observed outcomes.
- Optionally avoid immediate opposite-direction actions.
- Keep the new behavior disabled by default.

This is an exploration policy, not a complete game solver.
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

OPPOSITE_ACTIONS = {
    "ACTION1": "ACTION2",
    "ACTION2": "ACTION1",
    "ACTION3": "ACTION4",
    "ACTION4": "ACTION3",
}


def observation_key(
    frame: Sequence[Any],
    levels_completed: int,
    state: str,
) -> str:
    """Generate a stable fingerprint of an observation."""

    final_grid = frame[-1] if frame else []

    raw = repr(
        (state, levels_completed, final_grid)
    ).encode("utf-8")

    return blake2b(
        raw,
        digest_size=16,
    ).hexdigest()


class FeedbackPolicy:
    """Choose exploration actions using observed feedback.

    V3: Balanced exploration across visited screens.

    V5: Optional prevention of immediate opposite actions.

    Level completion and scores are never invented.
    """

    def __init__(
        self,
        actions: Sequence[str] = KEYBOARD_ACTIONS,
        avoid_immediate_reverse: bool = False,
    ) -> None:

        if not actions or len(set(actions)) != len(actions):
            raise ValueError(
                "Provide distinct nonempty actions"
            )

        self.actions = tuple(actions)

        self.avoid_immediate_reverse = (
            avoid_immediate_reverse
        )

        self._last_action: str | None = None

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
        """Clear pending state when the game resets."""

        self._pending = None
        self._last_action = None

    def observe(
        self,
        key: str,
        levels_completed: int,
        state: str,
    ) -> None:
        """Evaluate the observed outcome of the last action."""

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

            # A new level starts a new movement context.
            if progressed or state in ("WIN", "GAME_OVER"):
                self._last_action = None

        self.visits[key] += 1

    def _candidate_actions(self) -> list[str]:
        """Return actions allowed by the optional V5 rule."""

        candidates = list(self.actions)

        if not self.avoid_immediate_reverse:
            return candidates

        opposite = OPPOSITE_ACTIONS.get(
            self._last_action
        )

        if opposite is None:
            return candidates

        filtered = [
            action
            for action in candidates
            if action != opposite
        ]

        # Always keep at least one valid action available.
        return filtered if filtered else candidates

    def choose(
        self,
        key: str,
        levels_completed: int,
    ) -> str:
        """Select an action using balanced exploration.

        V5 optionally excludes the immediate reverse direction.

        Among untried actions, choose the least-used action.

        Once candidate actions have been explored, use their
        observed rewards, novelty and exploration bonuses.
        """

        candidates = self._candidate_actions()

        unseen = [
            action
            for action in candidates
            if self.attempts[(key, action)] == 0
        ]

        if unseen:

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
                candidates,
                key=value,
            )

        self.attempts[(key, action)] += 1

        self._pending = (
            key,
            action,
            levels_completed,
        )

        self._last_action = action

        return action
