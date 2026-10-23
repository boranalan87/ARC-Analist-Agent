"""Dependency-free feedback policy for keyboard ARC-AGI-3 games.

FeedbackExplorer V8 (V7 policy plus optional visual goal preference):
- Preserve V3 balanced exploration and observation-based rewards.
- Preserve V5 optional immediate reverse-movement prevention.
- Preserve V6 optional LS20 step-counter HUD masking.
- Optionally navigate the observed state-transition graph to frontiers.
- Penalize observed self-loops and frequently revisited destinations.
- Keep V7 navigation disabled by default for other games.

This is an exploration policy, not a guaranteed game solver.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from hashlib import blake2b
from math import log1p, sqrt
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
    *,
    mask_ls20_step_counter: bool = False,
) -> str:
    """Hash the latest observation, optionally masking LS20's step HUD.

    V6 masking remains opt-in, preserving other games' fingerprints.
    """
    final_grid = frame[-1] if frame else []

    if mask_ls20_step_counter:
        try:
            if (
                len(final_grid) == 64
                and all(len(row) == 64 for row in final_grid)
            ):
                final_grid = tuple(
                    tuple(
                        -1 if (61 <= y <= 62 and 13 <= x < 56)
                        else int(pixel)
                        for x, pixel in enumerate(row)
                    )
                    for y, row in enumerate(final_grid)
                )
        except (TypeError, ValueError, OverflowError):
            pass

    raw = repr((state, levels_completed, final_grid)).encode("utf-8")
    return blake2b(raw, digest_size=16).hexdigest()


class FeedbackPolicy:
    """Select exploration actions using observed outcomes.

    V7 graph navigation is opt-in. No path or success is fabricated.
    """

    MAX_NAVIGATION_NODES = 2048

    def __init__(
        self,
        actions: Sequence[str] = KEYBOARD_ACTIONS,
        avoid_immediate_reverse: bool = False,
        enable_navigation: bool = False,
    ) -> None:
        if not actions or len(set(actions)) != len(actions):
            raise ValueError("Provide distinct nonempty actions")

        self.actions = tuple(actions)
        self.avoid_immediate_reverse = avoid_immediate_reverse
        self.enable_navigation = enable_navigation
        self._last_action: str | None = None

        self.visits: Counter[str] = Counter()
        self.attempts: Counter[tuple[str, str]] = Counter()
        self.reward_sum: dict[tuple[str, str], float] = defaultdict(float)
        # Keep the original single-destination interface for compatibility.
        self.next_screen: dict[tuple[str, str], str] = {}
        self._pending: tuple[str, str, int] | None = None

        # V7: Record real observed transitions, including nondeterministic ones.
        self.transition_counts: dict[
            tuple[str, str], Counter[str]
        ] = defaultdict(Counter)
        self.state_levels: dict[str, int] = {}
        self.terminal_states: set[str] = set()
        self.navigation_decisions = 0
        self.navigation_fallbacks = 0

    def clear_pending(self) -> None:
        """Clear pending action and direction, preserving same-run learning."""
        self._pending = None
        self._last_action = None

    def observe(
        self,
        key: str,
        levels_completed: int,
        state: str,
    ) -> None:
        """Evaluate the last real action and record its transition."""
        first_visit = self.visits[key] == 0
        self.state_levels[key] = levels_completed
        if state in ("WIN", "GAME_OVER"):
            self.terminal_states.add(key)

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
                reward = -2.0
            elif first_visit:
                reward = 3.0
            else:
                reward = 0.5

            self.reward_sum[pair] += reward
            self.next_screen[pair] = key
            self.transition_counts[pair][key] += 1
            self._pending = None

            if progressed or state in ("WIN", "GAME_OVER"):
                self._last_action = None

        self.visits[key] += 1

    def _allowed_after(self, last_action: str | None) -> list[str]:
        """Apply V5 reverse protection to an explicit prior direction."""
        candidates = list(self.actions)
        if not self.avoid_immediate_reverse:
            return candidates
        opposite = OPPOSITE_ACTIONS.get(last_action)
        if opposite is None:
            return candidates
        filtered = [action for action in candidates if action != opposite]
        return filtered if filtered else candidates

    def _candidate_actions(self) -> list[str]:
        """Preserve the original V5 candidate-selection interface."""
        return self._allowed_after(self._last_action)

    def _frontier_action(self, key: str, levels_completed: int) -> str | None:
        """BFS through *observed* transitions to the nearest usable frontier.

        The search state includes the previous action, so V5 reverse filtering
        is respected at every hop. Never route through a terminal state, an
        observed self-loop, or a transition crossing the current level.
        """
        queue: deque[tuple[str, str | None, str | None]] = deque(
            [(key, self._last_action, None)]
        )
        seen = {(key, self._last_action)}

        while queue and len(seen) <= self.MAX_NAVIGATION_NODES:
            screen, previous_action, first_action = queue.popleft()
            possible_actions = self._allowed_after(previous_action)

            if first_action is not None and any(
                self.attempts[(screen, action)] == 0
                for action in possible_actions
            ):
                return first_action

            for action in possible_actions:
                transitions = self.transition_counts.get((screen, action))
                if not transitions:
                    continue

                # Favor historically common observed outcomes, with stable ties.
                ordered_destinations = sorted(
                    transitions,
                    key=lambda dest: (-transitions[dest], dest),
                )
                for destination in ordered_destinations:
                    if destination == screen or destination in self.terminal_states:
                        continue
                    if self.state_levels.get(destination) != levels_completed:
                        continue

                    node = (destination, action)
                    if node in seen:
                        continue
                    seen.add(node)
                    queue.append((
                        destination,
                        action,
                        action if first_action is None else first_action,
                    ))
                    if len(seen) >= self.MAX_NAVIGATION_NODES:
                        break
                if len(seen) >= self.MAX_NAVIGATION_NODES:
                    break

        return None

    def _action_value(self, key: str, action: str) -> float:
        """Original reward score with optional V7 loop-avoidance penalties."""
        pair = (key, action)
        count = self.attempts[pair]
        mean_reward = self.reward_sum[pair] / count
        destination = self.next_screen.get(pair)

        novelty = (
            1.5 / sqrt(1 + self.visits[destination])
            if destination else 0.0
        )
        exploration_bonus = 0.5 / sqrt(count)
        repeat_penalty = 0.1 * count
        score = mean_reward + novelty + exploration_bonus - repeat_penalty

        if self.enable_navigation:
            transitions = self.transition_counts.get(pair)
            if transitions:
                total = sum(transitions.values())
                for reached, observations in transitions.items():
                    if total <= 0:
                        break
                    probability = observations / total
                    if reached == key:
                        score -= 2.0 * probability
                    elif reached in self.terminal_states:
                        score -= 3.0 * probability
                    else:
                        score -= (
                            0.35 * probability * log1p(self.visits[reached])
                        )
        return score

    def choose(
        self, key: str, levels_completed: int, *,
        preferred_action: str | None = None,
        allow_preferred_reverse: bool = False,
    ) -> str:
        """Try local unseen actions, then navigate to observed frontiers.

        If no frontier is reachable, fall back to reward-based exploration.
        The legacy behavior is unchanged when navigation is disabled.
        """
        candidates = self._candidate_actions()
        unseen = [
            action for action in candidates
            if self.attempts[(key, action)] == 0
        ]

        if allow_preferred_reverse and preferred_action in self.actions:
            # V8.4: callers may *explicitly* honor a validated visual route
            # even if V5's immediate-reverse heuristic filtered this move.
            action = preferred_action
        elif preferred_action in candidates:
            # V8: Prefer only an action inferred from a visible LS20 frame.
            action = preferred_action
        elif unseen:
            total_usage: Counter[str] = Counter()
            for (_, previous_action), count in self.attempts.items():
                total_usage[previous_action] += count
            action = min(
                unseen,
                key=lambda candidate: (
                    total_usage[candidate],
                    self.actions.index(candidate),
                ),
            )
        else:
            planned = (
                self._frontier_action(key, levels_completed)
                if self.enable_navigation else None
            )
            if planned in candidates:
                action = planned
                self.navigation_decisions += 1
            else:
                if self.enable_navigation:
                    self.navigation_fallbacks += 1
                action = max(
                    candidates,
                    key=lambda candidate: self._action_value(key, candidate),
                )

        self.attempts[(key, action)] += 1
        self._pending = (key, action, levels_completed)
        self._last_action = action
        return action

    def navigation_summary(self) -> dict[str, int | bool]:
        """Expose inspectable current-run graph statistics."""
        return {
            "enabled": bool(self.enable_navigation),
            "observed_transition_edges": sum(
                len(outcomes) for outcomes in self.transition_counts.values()
            ),
            "observed_transition_steps": sum(
                sum(outcomes.values()) for outcomes in self.transition_counts.values()
            ),
            "self_loop_steps": sum(
                outcomes.get(source, 0)
                for (source, _), outcomes in self.transition_counts.items()
            ),
            "navigation_decisions": self.navigation_decisions,
            "navigation_fallbacks": self.navigation_fallbacks,
        }
