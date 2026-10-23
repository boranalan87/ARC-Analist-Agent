
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

# Positions observed in real level-2 frames 1, 6 and 16.
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
                pixel = index(cell)
                if not 0 <= pixel <= 255:
                    return None
                out_row.append(pixel)
            result.append(out_row)
        return result
    except (TypeError, ValueError, OverflowError, IndexError):
        return None


def locate_player(grid: list[list[int]]) -> tuple[int, int] | None:
    """Find the unique rendered 5x5 LS20 cursor."""
    matches = []
    for y in range(0, 56, 5):
        for x in range(4, 60, 5):
            if all(
                grid[y + dy][x + dx] == (12 if dy < 2 else 9)
                for dy in range(5)
                for dx in range(5)
            ):
                matches.append((x, y))
    return matches[0] if len(matches) == 1 else None


def locate_goal(grid: list[list[int]]) -> tuple[int, int] | None:
    """Find a unique visible 5x5 goal pad."""
    matches = []
    for y in range(0, 56, 5):
        for x in range(4, 60, 5):
            tile = [
                grid[y + dy][x + dx]
                for dy in range(5)
                for dx in range(5)
            ]
            if (
                tile.count(5) >= 11
                and 3 <= tile.count(9) <= 12
                and 4 not in tile
                and 12 not in tile
            ):
                matches.append((x, y))
    return matches[0] if len(matches) == 1 else None


def locate_rotation_switch(
    grid: list[list[int]],
) -> tuple[int, int] | None:
    """Identify the rendered LS20 rotation tile."""
    matches = []
    for y in range(0, 56, 5):
        for x in range(4, 60, 5):
            if (
                grid[y + 1][x + 2] == 0
                and grid[y + 2][x + 1] == 1
                and grid[y + 2][x + 2] == 0
                and grid[y + 2][x + 3] == 0
                and grid[y + 3][x + 2] == 1
            ):
                matches.append((x, y))
    return matches[0] if len(matches) == 1 else None


def _shape_mask(
    grid: list[list[int]],
    x: int,
    y: int,
    *,
    scale: int,
) -> tuple[tuple[bool, ...], ...] | None:
    """Read a 3x3 colored shape from visible pixels."""
    result = []
    for dy in range(3):
        row = []
        for dx in range(3):
            pixels = [
                grid[y + scale * dy + sy][x + scale * dx + sx]
                for sy in range(scale)
                for sx in range(scale)
            ]
            colored = sum(1 for p in pixels if p == 9)
            if 0 < colored < len(pixels):
                return None
            row.append(colored == len(pixels))
        result.append(tuple(row))

    shape = tuple(result)
    return shape if 3 <= sum(sum(r) for r in shape) <= 7 else None


def _turn_clockwise(
    shape: tuple[tuple[bool, ...], ...],
) -> tuple[tuple[bool, ...], ...]:
    return tuple(
        tuple(shape[2 - x][y] for x in range(3))
        for y in range(3)
    )


def shape_rotations_needed(
    grid: list[list[int]],
    goal: tuple[int, int],
) -> int | None:
    """Calculate turns using only rendered pose and goal symbols."""
    gx, gy = goal
    target = _shape_mask(grid, gx + 1, gy + 1, scale=1)
    current = _shape_mask(grid, 3, 55, scale=2)

    if target is None or current is None:
        return None

    rotated = current
    for count in range(4):
        if rotated == target:
            return count
        rotated = _turn_clockwise(rotated)
    return None


def _passable(
    grid: list[list[int]],
    x: int,
    y: int,
) -> bool:
    if x < 4 or x > 54 or y < 0 or y > 55:
        return False

    wall_pixels = sum(
        grid[y + dy][x + dx] == 4
        for dy in range(5)
        for dx in range(5)
    )
    return wall_pixels < 13


def shortest_visible_path(
    grid: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
    candidates: Sequence[str],
    blocked: set[tuple[tuple[int, int], str]],
) -> list[str] | None:
    """Find a bounded route over visible 5x5 cells."""
    if start == goal:
        return []

    queue = deque([(start, ())])
    seen = {start}

    while queue:
        pos, moves = queue.popleft()

        for action, (dx, dy) in DIRECTIONS.items():
            if not moves and action not in candidates:
                continue
            if (pos, action) in blocked:
                continue

            next_pos = (pos[0] + dx, pos[1] + dy)

            if next_pos in seen:
                continue
            if not _passable(grid, *next_pos):
                continue

            new_moves = moves + (action,)
            if next_pos == goal:
                return list(new_moves)

            seen.add(next_pos)
            queue.append((next_pos, new_moves))

    return None


class LS20VisualPlanner:
    """Conservative LS20 planning using visible game frames."""

    def __init__(self) -> None:
        self.proposals = 0
        self.fallbacks = 0
        self.blocked_moves = 0
        self.last_reason = "not_started"

        self._pending: (
            tuple[tuple[int, int], str, int] | None
        ) = None

        self._blocked: set[
            tuple[tuple[int, int], str]
        ] = set()

        self._last_level: int | None = None
        self.level2_proposals = 0
        self.level2_fallbacks = 0
        # Run-local counters; selecting a route is NOT proof of progress.
        self.preferred_actions_applied = 0
        self.preferred_actions_rejected = 0
        self.level2_reverse_filter_overrides = 0

    def reset_pending(self) -> None:
        """Clear temporary movement information after a reset."""
        self._pending = None
        self._blocked.clear()

    def propose(
        self,
        frames: Sequence[Any],
        level: int,
        candidates: Sequence[str],
    ) -> str | None:
        if (
            self._last_level is not None
            and level != self._last_level
        ):
            self._blocked.clear()
            self._pending = None

        self._last_level = level

        if level not in (0, LS20_LEVEL_2_INDEX):
            return self._fallback("unvalidated_level")

        grid = visible_grid(frames)
        if grid is None:
            return self._fallback("invalid_frame")

        player = locate_player(grid)
        goal = locate_goal(grid)

        if player is None or goal is None:
            self._pending = None
            return self._fallback(
                "player_or_goal_not_visible"
            )

        rotation_tile = None

        if level == LS20_LEVEL_2_INDEX:
            rotation_tile = locate_rotation_switch(grid)

            if (
                goal != LEVEL_2_GOAL
                or rotation_tile != LEVEL_2_ROTATION_SWITCH
            ):
                self._pending = None
                return self._fallback("unvalidated_level")

        if self._pending is not None:
            previous, action, previous_level = self._pending

            if previous_level == level and previous == player:
                self._blocked.add((previous, action))
                self.blocked_moves += 1

        self._pending = None

        turns = shape_rotations_needed(grid, goal)
        if turns is None:
            return self._fallback("pose_not_visible")

        if turns:
            if rotation_tile is None:
                rotation_tile = locate_rotation_switch(grid)

            if rotation_tile is None:
                return self._fallback(
                    "rotation_switch_not_visible"
                )

            destination = rotation_tile
            reason = "rotation_required"
        else:
            destination = goal
            reason = "pose_matches_goal"

        route = shortest_visible_path(
            grid,
            player,
            destination,
            candidates,
            self._blocked,
        )

        if not route:
            return self._fallback("no_visible_route")

        action = route[0]
        self._pending = (player, action, level)
        self.last_reason = reason
        self.proposals += 1

        if level == LS20_LEVEL_2_INDEX:
            self.level2_proposals += 1

        return action

    def record_choice(
        self,
        proposal: str | None,
        selected: str,
        *,
        reverse_override: bool = False,
    ) -> None:
        """Count choices actually selected; never claim a level was solved."""
        if proposal is None:
            return
        if selected == proposal:
            self.preferred_actions_applied += 1
            if reverse_override:
                self.level2_reverse_filter_overrides += 1
        else:
            self.preferred_actions_rejected += 1

    def _fallback(self, reason: str) -> None:
        self.last_reason = reason
        self.fallbacks += 1

        if self._last_level == LS20_LEVEL_2_INDEX:
            self.level2_fallbacks += 1

        return None

    def summary(self) -> dict[str, int | bool | str]:
        return {
            "enabled": True,
            "scope": "ls20_levels_1_and_validated_2_visible_frames",
            "proposed_actions": self.proposals,
            "fallbacks": self.fallbacks,
            "blocked_moves": self.blocked_moves,
            "level2_proposed_actions": self.level2_proposals,
            "level2_fallbacks": self.level2_fallbacks,
            "preferred_actions_applied": self.preferred_actions_applied,
            "preferred_actions_rejected": self.preferred_actions_rejected,
            "level2_reverse_filter_overrides": self.level2_reverse_filter_overrides,
            "last_reason": self.last_reason,
        }
