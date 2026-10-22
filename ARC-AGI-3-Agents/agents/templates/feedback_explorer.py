"""FeedbackExplorer V8.3 — conservative LS20 visible-frame route planner.

Uses only rendered 64x64 game pixels. Level 1 (index 0) follows the old
V8.1 planner. Level 2 (index 1) is gated by the positions of two unique,
observable landmarks independently confirmed in three genuine level-2 frames.
Unrecognized frames fall back to the existing exploration policy.

No hidden game state or precomputed solution is used. This is NOT proof of
level completion, and a valid-looking path is not necessarily a winning path.
"""

from __future__ import annotations

from collections import deque
from operator import index
from typing import Any, Sequence

LS20_LEVEL_2_INDEX = 1
# Positions were observed in real level-2 frames 1, 6 and 16 (22 Oct 2026).
LEVEL_2_GOAL = (14, 40)
LEVEL_2_ROTATION_SWITCH = (49, 45)

DIRECTIONS = {
    "ACTION1": (0, -5),
    "ACTION2": (0, 5),
    "ACTION3": (-5, 0),
    "ACTION4": (5, 0),
}


def visible_grid(frames: Sequence[Any]) -> list[list[int]] | None:
    """Decode the most recent visible 64x64 frame, or fail closed."""
    try:
        if frames is None or len(frames) == 0:
            return None
        grid = frames[-1]
        if len(grid) != 64 or any(len(row) != 64 for row in grid):
            return None
        result = []
        for row in grid:
            out_row = []
            for cell in row:
                pixel = index(cell)  # unlike int(), rejects float and text
                if not 0 <= pixel <= 255:
                    return None
                out_row.append(pixel)
            result.append(out_row)
        return result
    except (TypeError, ValueError, OverflowError, IndexError):
        return None


def locate_player(grid: list[list[int]]) -> tuple[int, int] | None:
    """Find the unique rendered 5x5 LS20 cursor (two 12 rows, three 9)."""
    matches = []
    for y in range(0, 56, 5):
        for x in range(4, 60, 5):
            if (all(grid[y + dy][x + dx] == (12 if dy < 2 else 9)
                    for dy in range(5) for dx in range(5))):
                matches.append((x, y))
    return matches[0] if len(matches) == 1 else None


def locate_goal(grid: list[list[int]]) -> tuple[int, int] | None:
    """Find a visible 5x5 goal pad with 5 background and 9 icon pixels.

    This is a cautious recognition heuristic specific to LS20's public
    rendered graphics; ambiguity results in no plan, never a guessed goal.
    """
    matches = []
    for y in range(0, 56, 5):
        for x in range(4, 60, 5):
            tile = [grid[y + dy][x + dx] for dy in range(5) for dx in range(5)]
            if (tile.count(5) >= 11 and 3 <= tile.count(9) <= 12
                    and 4 not in tile and 12 not in tile):
                matches.append((x, y))
    return matches[0] if len(matches) == 1 else None


def locate_rotation_switch(grid: list[list[int]]) -> tuple[int, int] | None:
    """Identify the rendered LS20 rotation tile's distinctive 0/1 symbol."""
    matches = []
    for y in range(0, 56, 5):
        for x in range(4, 60, 5):
            if (grid[y+1][x+2] == 0 and grid[y+2][x+1] == 1
                    and grid[y+2][x+2] == 0 and grid[y+2][x+3] == 0
                    and grid[y+3][x+2] == 1):
                matches.append((x, y))
    return matches[0] if len(matches) == 1 else None


def _shape_mask(grid: list[list[int]], x: int, y: int, *, scale: int) -> tuple[tuple[bool, ...], ...] | None:
    """Read a 3x3 colored shape from visible pixels (optionally 2x HUD)."""
    result = []
    for dy in range(3):
        row = []

