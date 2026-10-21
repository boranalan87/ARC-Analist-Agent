"""Dependency-free feedback policy for keyboard ARC-AGI-3 games.

FeedbackExplorer V6:
- Preserve V3 balanced exploration and reward learning.
- Preserve V5 optional immediate reverse movement prevention.
- Optionally ignore the LS20 step-counter HUD in state fingerprints.
- Keep the new LS20 state behavior disabled by default.

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
    *,
    mask_ls20_step_counter: bool = False,
) -> str:
    """Generate a stable fingerprint of the current observation.

    V6 optionally ignores the bottom-left LS20 step-counter display.
    The option is disabled by default, preserving existing behavior.
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
            # Nonstandard frames retain their original fingerprint.
            pass

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
    V6: State fingerprinting can ignore LS20's step-counter HUD.

    Level completion and scores are never invented.
    """

    def __init__(
        self,
        actions: Sequence[str] = KEYBOARD_ACTIONS,
        avoid_immediate_reverse: bool = False,
    ) -> None:

        if not actions or len(set(actions)) != len(actions):
            raise ValueError(
