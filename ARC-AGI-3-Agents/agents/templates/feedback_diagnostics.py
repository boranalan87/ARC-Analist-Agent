"""Track observed actions and screen changes for FeedbackExplorer."""

from collections import Counter
from hashlib import blake2b
from typing import Any, Sequence


def screen_key(frame: Sequence[Any]) -> str:
    """Fingerprint only the latest visible game screen."""
    image = frame[-1] if frame else []
    return blake2b(
        repr(image).encode("utf-8"),
        digest_size=16,
    ).hexdigest()


class FeedbackDiagnostics:
    def __init__(self) -> None:
        self.actions: Counter[str] = Counter()
        self.screens: set[str] = set()
        self.changed_frames = 0
        self.unchanged_frames = 0
        self.levels_gained = 0

    def record_action(
        self,
        action: str,
        before_frame: Sequence[Any],
        after_frame: Sequence[Any],
        before_levels: int,
        after_levels: int,
    ) -> None:
        before = screen_key(before_frame)
        after = screen_key(after_frame)

        self.actions[action] += 1
        self.screens.update((before, after))

        if before == after:
            self.unchanged_frames += 1
        else:
            self.changed_frames += 1

        self.levels_gained += max(
            0,
            after_levels - before_levels,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "recorded_actions": sum(self.actions.values()),
            "actions_by_type": dict(sorted(self.actions.items())),
            "changed_frames": self.changed_frames,
            "unchanged_frames": self.unchanged_frames,
            "unique_screens": len(self.screens),
            "levels_gained": self.levels_gained,
        }
