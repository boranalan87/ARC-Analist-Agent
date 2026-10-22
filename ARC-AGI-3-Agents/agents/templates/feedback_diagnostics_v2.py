"""Bounded V2 telemetry; preserves all existing V1 summary fields.

V8.2 phase-2 adds optional, bounded LS20 level-2 visible-frame evidence.
Only the explicitly attached capture object's public summary is exported;
other game diagnostics and action-selection behavior remain unchanged.
"""

from __future__ import annotations

from collections import Counter, deque
from typing import Any, Sequence

from .feedback_diagnostics import FeedbackDiagnostics, screen_key


class FeedbackDiagnosticsV2(FeedbackDiagnostics):
    """Keep action-level outcomes and optionally bounded visible-frame evidence."""

    def __init__(self, policy: Any = None, max_events: int = 100) -> None:
        if not isinstance(max_events, int) or not 1 <= max_events <= 1000:
            raise ValueError("max_events must be between 1 and 1000")
        super().__init__()
        self.policy = policy
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._outcomes: Counter[str] = Counter()
        self._by_action: dict[str, Counter[str]] = {}
        self._streak = 0
        self._longest_streak = 0

    def record_action(
        self,
        action: str,
        before_frame: Sequence[Any],
        after_frame: Sequence[Any],
        before_levels: int,
        after_levels: int,
        after_state: str | None = None,
    ) -> None:
        super().record_action(
            action, before_frame, after_frame, before_levels, after_levels
        )
        changed = screen_key(before_frame) != screen_key(after_frame)
        levels_delta = max(0, after_levels - before_levels)
        outcome = (
            "progressed" if levels_delta else "changed" if changed else "unchanged"
        )
        self._outcomes[outcome] += 1
        self._by_action.setdefault(action, Counter())[outcome] += 1
        self._streak = 0 if changed or levels_delta else self._streak + 1
        self._longest_streak = max(self._longest_streak, self._streak)
        self._events.append({
            "step": sum(self.actions.values()),
            "action": action,
            "outcome": outcome,
            "screen_changed": changed,
            "levels_delta": levels_delta,
            "after_state": after_state,
            "screen_id": screen_key(after_frame),
        })

    def _memory_summary(self) -> dict[str, Any] | None:
        """Aggregate policy memory for this run only."""
        policy = self.policy
        if policy is None:
            return None
        trials: Counter[str] = Counter()
        rewards: Counter[str] = Counter()
        pairs = 0
        for (screen, action), count in policy.attempts.items():
            if count <= 0:
                continue
            pairs += 1
            trials[action] += count
            rewards[action] += policy.reward_sum.get((screen, action), 0.0)
        return {
            "scope": "current_run",
            "known_states": len(policy.visits),
            "state_observations": sum(policy.visits.values()),
            "tried_state_action_pairs": pairs,
            "action_trials": dict(sorted(trials.items())),
            "mean_reward_by_action": {
                action: round(rewards[action] / count, 3)
                for action, count in sorted(trials.items())
            },
            "feedback_pending": getattr(policy, "_pending", None) is not None,
        }

    def summary(self) -> dict[str, Any]:
        base = super().summary()
        total = base["recorded_actions"]
        by_action = {}
        for action in sorted(self.actions):
            outcomes = self._by_action.get(action, Counter())
            count = self.actions[action]
            by_action[action] = {
                "trials": count,
                "progressed": outcomes["progressed"],
                "changed": outcomes["changed"],
                "unchanged": outcomes["unchanged"],
                "progress_rate": round(outcomes["progressed"] / count, 4),
            }
        # Additional V8 opt-in telemetry; legacy V2 fields stay untouched.
        policy_navigation = (
            self.policy.navigation_summary()
            if self.policy is not None
            and callable(getattr(self.policy, "navigation_summary", None))
            else None
        )
        visual_planner = getattr(self, "visual_planner", None)
        visible_goal = (
            visual_planner.summary() if visual_planner is not None else None
        )
        # V8.2: Expose up to three real, rendered LS20 level-2 images for
        # offline validation. Never infer that samples exist if none were seen.
        capture = getattr(self, "level2_frame_capture", None)
        level2_capture = (
            capture.summary() if capture is not None
            and callable(getattr(capture, "summary", None)) else None
        )
        base["v2"] = {
            "version": 2,
            "frame_change_rate": (
                round(base["changed_frames"] / total, 4) if total else 0.0
            ),
            "outcomes": {
                name: self._outcomes[name]
                for name in ("progressed", "changed", "unchanged")
            },
            "action_effectiveness": by_action,
            "longest_unchanged_streak": self._longest_streak,
            "events_retained": len(self._events),
            "history_truncated": total > len(self._events),
            "recent_actions": list(self._events),
            "policy_memory": self._memory_summary(),
            "navigation": policy_navigation,
            "visible_goal_planning": visible_goal,
            "level2_frame_capture": level2_capture,
        }
        return base
