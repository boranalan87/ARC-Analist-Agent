"""Conservative, read-only LS20 level-2 visible-frame inspection (V8.2 phase 1).

Level-2 means ``levels_completed == 1``. This module never accesses hidden
sprites, level data, precomputed solutions, or the game engine. It only assesses
rendered 64x64 pixels, reusing the V8.1 observable pattern detectors.

Crucially, this is NOT wired into action selection yet. Synthetic-unit-test
success does not establish that level-2 production frames match the heuristics.
Activate planning only after evidence from real level-2 frames is validated.
"""

from __future__ import annotations

from typing import Any, Sequence

from .ls20_visual_planner import (
    DIRECTIONS,
    locate_goal,
    locate_player,
    locate_rotation_switch,
    shape_rotations_needed,
    shortest_visible_path,
    visible_grid,
)


LEVEL_2_INDEX = 1


def inspect_visible_level2(
    frames: Sequence[Any],
    *,
    level: int,
    candidates: Sequence[str] = tuple(DIRECTIONS),
) -> dict[str, Any]:
    """Return bounded, evidence-based diagnostics, not a gameplay command.

    ``suggested_action`` is an *unexecuted* route candidate for inspection. It
    must not be used by the agent without further validation of real frames.
    Unsupported, malformed, or ambiguous images fail closed with null hints.
    """
    result: dict[str, Any] = {
        "observer_version": "8.2-phase1",
        "level_index": level,
        "validated": False,
        "reason": "unvalidated_level",
        "player_visible": False,
        "goal_visible": False,
        "rotation_switch_visible": False,
        "pose_visible": False,
        "turns_needed": None,
        "route_length": None,
        "suggested_action": None,
    }
    if level != LEVEL_2_INDEX:
        return result

    grid = visible_grid(frames)
    if grid is None:
        result["reason"] = "invalid_frame"
        return result

    player = locate_player(grid)
    goal = locate_goal(grid)
    result["player_visible"] = player is not None
    result["goal_visible"] = goal is not None
    if player is None or goal is None:
        result["reason"] = "player_or_goal_not_visible"
        return result

    turns = shape_rotations_needed(grid, goal)
    result["pose_visible"] = turns is not None
    result["turns_needed"] = turns
    if turns is None:
        result["reason"] = "pose_not_visible"
        return result

    switch = locate_rotation_switch(grid)
    result["rotation_switch_visible"] = switch is not None
    if turns and switch is None:
        result["reason"] = "rotation_switch_not_visible"
        return result

    destination = switch if turns else goal
    if destination is None:
        result["reason"] = "missing_destination"
        return result

    safe_candidates = tuple(
        action for action in candidates
        if isinstance(action, str) and action in DIRECTIONS
    )
    if not safe_candidates:
        result["reason"] = "no_supported_actions"
        return result

    route = shortest_visible_path(grid, player, destination, safe_candidates, set())
    if route is None:
        result["reason"] = "no_visible_route"
        return result
    if not route:
        result["reason"] = "already_at_visible_destination"
        return result

    result["validated"] = True
    result["reason"] = "visible_route_to_switch" if turns else "visible_route_to_goal"
    result["route_length"] = len(route)
    result["suggested_action"] = route[0]
    return result
