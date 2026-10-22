    return None


def _passable(grid: list[list[int]], x: int, y: int) -> bool:
    if x < 4 or x > 54 or y < 0 or y > 55:
        return False
    # Solid 4-colored blocks correspond to observed impassable walls.
    wall_pixels = sum(grid[y+dy][x+dx] == 4 for dy in range(5) for dx in range(5))
    return wall_pixels < 13


def shortest_visible_path(
    grid: list[list[int]], start: tuple[int, int], goal: tuple[int, int],
    candidates: Sequence[str], blocked: set[tuple[tuple[int, int], str]],
) -> list[str] | None:
    """Find a bounded route on visible 5x5 cells, honoring observed walls."""
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
            next_pos = (pos[0]+dx, pos[1]+dy)
            if next_pos in seen or not _passable(grid, *next_pos):
                continue
            new_moves = moves + (action,)
            if next_pos == goal:
                return list(new_moves)
            seen.add(next_pos)
            queue.append((next_pos, new_moves))
    return None


class LS20VisualPlanner:
    """Conservative LS20 planning: pose mismatch -> rotate -> visible goal."""

    def __init__(self) -> None:
        self.proposals = 0
        self.fallbacks = 0
        self.blocked_moves = 0
        self.last_reason = "not_started"
        self._pending: tuple[tuple[int, int], str, int] | None = None
        self._blocked: set[tuple[tuple[int, int], str]] = set()
        self._last_level: int | None = None
        self.level2_proposals = 0
        self.level2_fallbacks = 0

    def reset_pending(self) -> None:
        """Forget temporary move blocks after a game reset."""
        self._pending = None
        self._blocked.clear()

    def propose(self, frames: Sequence[Any], level: int, candidates: Sequence[str]) -> str | None:
        if self._last_level is not None and level != self._last_level:
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
            return self._fallback("player_or_goal_not_visible")

        # Activating a level-1 heuristic in all higher levels would be unsafe.
        # Restrict level-2 use to the layout observed in three REAL frames.
        # Revalidate the switch each time; no frame fingerprint memorization.
        rotation_tile = None
        if level == LS20_LEVEL_2_INDEX:
            rotation_tile = locate_rotation_switch(grid)
            if (goal != LEVEL_2_GOAL
                    or rotation_tile != LEVEL_2_ROTATION_SWITCH):
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
                return self._fallback("rotation_switch_not_visible")
            destination = rotation_tile
            reason = "rotation_required"
        else:
            destination = goal
            reason = "pose_matches_goal"
        route = shortest_visible_path(grid, player, destination, candidates, self._blocked)
        if not route:
            return self._fallback("no_visible_route")
        action = route[0]
        self._pending = (player, action, level)
        self.last_reason = reason
        self.proposals += 1
        if level == LS20_LEVEL_2_INDEX:
            self.level2_proposals += 1
        return action

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
