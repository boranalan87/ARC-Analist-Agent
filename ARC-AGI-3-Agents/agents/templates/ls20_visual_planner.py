
"""FeedbackExplorer V8.3 — conservative LS20 visible-frame route planner.

Uses only rendered 64x64 game pixels. Level 1 (index 0) follows the old
V8.1 planner. Level 2 (index 1) is gated by the positions of two unique,
observable landmarks independently confirmed in three genuine level-2 frames.
Unrecognized frames fall back to the existing exploration policy.

No hidden game state or precomputed solution is used. This is NOT proof of
level completion, and a valid-looking path is not necessarily a winning path.
"""

from __future__ import annotations

import hashlib
from collections import deque
from operator import index
from typing import Any, Sequence

LS20_LEVEL_2_INDEX = 1

# Positions observed in real level-2 frames 1, 6 and 16.
LEVEL_2_GOAL = (14, 40)
LEVEL_2_ROTATION_SWITCH = (49, 45)

# V8.8 genuine before-frame fingerprints in the 27 Oct read-only test.
# These are observations of failed ACTION1 exits, NOT inferred game rules.
# Match the entire displayed 64x64 frame, not merely player coordinates.
V88_OBSERVED_RISKY_EXIT_FPS = frozenset({
    'e58c8a39094e9e8f',  # alignment lost, observed -20,-5
    '70c046c20de8d462',  # alignment lost, observed -20,-5
    '869a0f09dcb2c63c',  # game over after nominal movement
})

# V9.0: only observations from the confirmed 27 Oct V8.8/V8.9 tests.
# All four exits from the first hash yielded a loss of alignment;
# others have untried choices. We DO NOT infer hidden game rules.
V90_FAILED_EXIT_ACTIONS = {
    'e58c8a39094e9e8f': frozenset(('ACTION1', 'ACTION2', 'ACTION3', 'ACTION4')),
    '70c046c20de8d462': frozenset(('ACTION1', 'ACTION3', 'ACTION4')),
    '869a0f09dcb2c63c': frozenset(('ACTION1', 'ACTION3', 'ACTION4')),
}

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
    *,
    avoid_positions: set[tuple[int, int]] | None = None,
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
            if avoid_positions is not None and next_pos in avoid_positions:
                continue
            if not _passable(grid, *next_pos):
                continue

            new_moves = moves + (action,)
            if next_pos == goal:
                return list(new_moves)

            seen.add(next_pos)
            queue.append((next_pos, new_moves))

    return None


def _v93_visible_state_fp(grid):
    """Hash only *rendered* LS20 pixels, masking the varying step HUD.

    V6's already-observed step counter occupies rows 61-62, columns 13-55.
    Without masking this strip, a repeated screen sequence appears different
    on each lap, defeating loop detection. This is not hidden game state.
    """
    return hashlib.sha256(bytes(
        0 if 61 <= y <= 62 and 13 <= x < 56 else pixel
        for y, row in enumerate(grid) for x, pixel in enumerate(row)
    )).hexdigest()[:16]


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
        # V8.5: inspect switch contact and attempt at most three visible
        # exit/re-entry cycles when the shape still requires rotation.
        self.level2_switch_contacts = 0
        self.level2_switch_exits_proposed = 0
        self.level2_switch_returns_proposed = 0
        self.level2_pose_changes_observed = 0
        self.level2_switch_cycles_stalled = 0
        self.level2_switch_retry_exhausted = 0
        self.level2_goal_routes_after_alignment = 0
        # V8.6: planning measurements do not imply level completion.
        self.level2_aligned_safe_routes = 0
        self.level2_aligned_goal_route_blocked = 0
        self.level2_alignment_lost = 0
        self._level2_was_aligned = False
        # V8.7: bounded observational events; never used for actions.
        self.level2_alignment_events = []
        self._level2_observations = 0
        self._level2_last_visible = None
        # V8.8: bounded observational evidence from immediate action frames.
        self.level2_switch_exit_transitions = []
        self.level2_switch_exit_transitions_total = 0
        self.level2_switch_exit_transition_errors = 0
        # V8.9: specific real visible observations from V8.8, plus
        # newly observed risks during THIS run. Persist during RESET
        # inside a run so identical failures do not loop forever.
        self._level2_risky_exits = {(fp, 'ACTION1') for fp in V88_OBSERVED_RISKY_EXIT_FPS}
        self.level2_exit_guard_activations = 0
        self.level2_exit_guard_alternatives = 0
        self.level2_exit_guard_no_route = 0
        self.level2_exit_guard_new_risks = 0
        # V9.0: bounded run-local state-action -> observed-successor model.
        # Retain across in-run RESETs, never across unrelated agent runs.
        self._v90_transitions = {}  # (frame_fp, action) -> aggregate
        self._v90_max_pairs = 192
        self.v90_request_reset = False
        self.level2_transition_samples = 0
        self.level2_transition_hazard_samples = 0
        self.level2_transition_self_loops = 0
        self.level2_transition_memory_full = 0
        self.level2_transition_errors = 0
        self.level2_transition_trap_avoids = 0
        self.level2_transition_loop_avoids = 0
        self.level2_transition_guarded_choices = 0
        self.level2_transition_forced_resets = 0
        for _fp, _actions in V90_FAILED_EXIT_ACTIONS.items():
            self._level2_risky_exits.update((_fp, _action) for _action in _actions)
        self._switch_plan = None  # (phase, exit_position, return_action, rotations_before)
        self._switch_previous_contact = False
        self._switch_retry_count = 0
        self._switch_used_exits = set()
        self._level2_landmark_validated = False
        # V9.1: keep only bounded, in-run history of failed switch approaches.
        # The waypoint set has at most four *visible* switch-adjacent tiles.
        self._v91_dead_end_resets = 0
        self._v91_waypoints_tried = set()
        self._v91_approach_waypoint = None
        self._v91_exhausted_reported_for = 0
        self.level2_v91_alternative_steps = 0
        self.level2_v91_approaches_selected = 0
        self.level2_v91_approaches_exhausted = 0
        # V9.2: infer an approach only from an actual before/after frame.
        # This history lives within one run and contains at most 4 tiles.
        self._v92_last_observed_entry = None  # (adjacent_tile, exact_switch_frame_fp)
        self._v92_confirmed_dead_end_approaches = set()
        self.level2_v92_observed_entries = 0
        self.level2_v92_verified_bad_approaches = 0
        self.level2_v92_approaches_skipped = 0
        # V9.3: bounded, run-local history of ACTUALLY observed level-2
        # before/action/after frames. Detect cycles, not repeated coordinates.
        self._v93_recent_steps = deque(maxlen=48)
        self._v93_repeated_actions = set()  # at most 8 exact (frame, action) keys
        self.level2_v93_observed_steps = 0
        self.level2_v93_cycles_confirmed = 0
        self.level2_v93_unique_actions_blocked = 0
        self.level2_v93_guard_activations = 0
        self.level2_v93_detours_selected = 0
        self.level2_v93_no_alternative = 0
        self.level2_v93_observation_errors = 0
        # V9.4: two fully observed, consecutive, exact A->B->A
        # oscillations. No inferred or position-only transitions.
        self._v94_short_guard_pairs = set()  # max 8 masked-screen/action pairs
        self.level2_v94_short_cycles_confirmed = 0
        self.level2_v94_unique_pairs_blocked = 0
        self.level2_v94_guard_activations = 0
        self.level2_v94_detours_selected = 0
        self.level2_v94_no_alternative = 0
        self.level2_v94_observation_errors = 0
        # V9.5: strictly read-only, bounded no-detour diagnostics.
        self.level2_v95_no_alternative_events_total = 0
        self._v95_no_alternative_events = []  # at most 8
        # Stage 2: evidence is from consecutive observed transitions,
        # not repeat calls to propose() on the same frame.
        self._v95_confirmed_short_cycles_by_fp = {}  # max 8
        self._v95_recovery_attempted_fps = set()  # max 2
        self.level2_v95_recovery_resets = 0
        self.level2_v95_recovery_no_waypoint = 0
        self.level2_v95_recovery_repeat_suppressed = 0

    def reset_pending(self) -> None:
        """Clear temporary movement information after a reset."""
        self._pending = None
        self._blocked.clear()
        self._reset_switch_state()

    def _reset_switch_state(self) -> None:
        """Reset cycle state; run-level diagnostics remain cumulative."""
        self._switch_plan = None
        self._switch_previous_contact = False
        self._switch_retry_count = 0
        self._switch_used_exits.clear()
        self._level2_landmark_validated = False
        self._level2_was_aligned = False
        self._level2_last_visible = None
        self._v91_approach_waypoint = None
        self._v92_last_observed_entry = None

    def _v92_observe_switch_entry(self, before, after, action_name):
        """Retain an actual adjacent-to-switch entry, never a proposed move.

        The full rendered destination fingerprint prevents incorrectly
        associating an earlier entry with a different switch configuration.
        """
        if action_name not in DIRECTIONS:
            return
        if (getattr(before, 'levels_completed', None) != LS20_LEVEL_2_INDEX or
                getattr(after, 'levels_completed', None) != LS20_LEVEL_2_INDEX):
            return
        if getattr(getattr(after, 'state', None), 'name', '') != 'NOT_FINISHED':
            return
        before_grid = visible_grid(getattr(before, 'frame', None))
        after_grid = visible_grid(getattr(after, 'frame', None))
        if before_grid is None or after_grid is None:
            return
        if (locate_goal(before_grid) != LEVEL_2_GOAL or
                locate_goal(after_grid) != LEVEL_2_GOAL or
                locate_rotation_switch(before_grid) != LEVEL_2_ROTATION_SWITCH):
            return
        start = locate_player(before_grid)
        end = locate_player(after_grid)
        if start is None or end != LEVEL_2_ROTATION_SWITCH:
            return
        dx, dy = DIRECTIONS[action_name]
        if (start[0] + dx, start[1] + dy) != end:
            return
        if shape_rotations_needed(after_grid, LEVEL_2_GOAL) is None:
            return
        fingerprint = hashlib.sha256(
            bytes(px for row in after_grid for px in row)
        ).hexdigest()[:16]
        self._v92_last_observed_entry = (start, fingerprint)
        self.level2_v92_observed_entries += 1

    def _v93_observe_repeated_cycle(self, before, after, action_name):
        """Detect a strictly repeated 8–24-step *observed* level-2 cycle.

        Accept RESET only when both actual frames are still level 2. Stop
        comparing across level changes, invalid images and game-over states.
        Store bounded fingerprints, NEVER synthetic engine transitions or
        hidden state. A repeated cycle is not proof of an unsafe action.
        """
        before_level = getattr(before, 'levels_completed', None)
        after_level = getattr(after, 'levels_completed', None)
        if before_level != LS20_LEVEL_2_INDEX or after_level != LS20_LEVEL_2_INDEX:
            self._v93_recent_steps.clear()
            if after_level != LS20_LEVEL_2_INDEX:
                self._v93_repeated_actions.clear()
                self._v94_short_guard_pairs.clear()
                # A new level needs fresh observed cycle evidence.
                self._v95_confirmed_short_cycles_by_fp.clear()
            return
        if (action_name not in DIRECTIONS and action_name != 'RESET') or (
            getattr(getattr(before, 'state', None), 'name', '') != 'NOT_FINISHED' or
            getattr(getattr(after, 'state', None), 'name', '') != 'NOT_FINISHED'
        ):
            self._v93_recent_steps.clear()
            return
        before_grid = visible_grid(getattr(before, 'frame', None))
        after_grid = visible_grid(getattr(after, 'frame', None))
        if (before_grid is None or after_grid is None or
                locate_goal(before_grid) != LEVEL_2_GOAL or
                locate_goal(after_grid) != LEVEL_2_GOAL or
                locate_player(before_grid) is None or
                locate_player(after_grid) is None or
                shape_rotations_needed(before_grid, LEVEL_2_GOAL) is None or
                shape_rotations_needed(after_grid, LEVEL_2_GOAL) is None):
            self._v93_recent_steps.clear()
            return
        before_fp = _v93_visible_state_fp(before_grid)
        after_fp = _v93_visible_state_fp(after_grid)
        # Require exact continuous observations; no stitching unrelated runs.
        if self._v93_recent_steps and self._v93_recent_steps[-1][2] != before_fp:
            self._v93_recent_steps.clear()
        self._v93_recent_steps.append((before_fp, action_name, after_fp))
        self.level2_v93_observed_steps += 1
        steps = list(self._v93_recent_steps)
        try:
            self._v94_check_exact_two_step_oscillation(steps)
        except Exception:
            self.level2_v94_observation_errors += 1
        # Compare adjacent equally long *complete* sequences. A one-off
        # self-loop or shared tile can never establish this threshold.
        for period in range(8, min(24, len(steps) // 2) + 1):
            previous, recent = steps[-2 * period:-period], steps[-period:]
            if previous != recent:
                continue
            self.level2_v93_cycles_confirmed += 1
            # A witnessed cycle predicts the action already executed when
            # this exact displayed frame occurred in the matched sequence.
            # Ambiguous actions at the frame remain unmodified.
            next_actions = {
                action for fp, action, _ in recent
                if fp == after_fp and action in DIRECTIONS
            }
            if len(next_actions) == 1 and len(self._v93_repeated_actions) < 8:
                key = (after_fp, next(iter(next_actions)))
                if key not in self._v93_repeated_actions:
                    self._v93_repeated_actions.add(key)
                    self.level2_v93_unique_actions_blocked += 1
            break

    def _v94_check_exact_two_step_oscillation(self, steps):
        """Confirm twice observed A--key1-->B--opposite key2-->A.

        Four consecutive real transitions must agree on both full visible
        screen fingerprints (excluding the known HUD counter) AND actions.
        A one-off reverse, individual pixel change or same-screen key repeat
        does not prove a short cycle. This is not a game-engine rule.
        """
        if len(steps) < 4:
            return
        first, second, third, fourth = steps[-4:]
        if first != third or second != fourth:
            return
        a, forward, b = first
        b2, backward, a2 = second
        if a == b or b != b2 or a != a2:
            return
        if forward not in DIRECTIONS or backward not in DIRECTIONS:
            return
        dx, dy = DIRECTIONS[forward]
        if DIRECTIONS[backward] != (-dx, -dy):
            return
        self.level2_v94_short_cycles_confirmed += 1
        # Never block an unobserved next action; require that the first
        # key was actually taken from the exact displayed state A.
        pair = (a, forward)
        # Count independent real 4-step observations per exact masked
        # visible state; a repeated propose() cannot increment this.
        counts = self._v95_confirmed_short_cycles_by_fp
        if a in counts or len(counts) < 8:
            counts[a] = min(3, counts.get(a, 0) + 1)
        if pair not in self._v94_short_guard_pairs and len(self._v94_short_guard_pairs) < 8:
            self._v94_short_guard_pairs.add(pair)
            self.level2_v94_unique_pairs_blocked += 1

    def _v95_try_recovery_reset(self, grid, player, switch, masked_fp, candidates):
        """Bounded RESET only after repeated, *observed* 2-step loops.

        A reset merely starts a new experimental approach through V9.1's
        existing visible waypoint planner. We require a reachable, as-yet
        untried switch-adjacent tile. This does not prove that tile is safe,
        or that resetting/proposing a route will complete the level.
        """
        if self._v95_confirmed_short_cycles_by_fp.get(masked_fp, 0) < 2:
            return False
        if (masked_fp in self._v95_recovery_attempted_fps or
                self.level2_v95_recovery_resets >= 2):
            self.level2_v95_recovery_repeat_suppressed += 1
            return False
        # RESET clears only temporary _blocked observations, so use that
        # post-reset condition for route availability. The visible switch
        # cannot be crossed on the way to a distinct approach waypoint.
        waypoint_exists = False
        for dx, dy in DIRECTIONS.values():
            waypoint = (switch[0] + dx, switch[1] + dy)
            if (waypoint == player or
                    waypoint in self._v91_waypoints_tried or
                    waypoint in self._v92_confirmed_dead_end_approaches or
                    not _passable(grid, *waypoint)):
                continue
            path = shortest_visible_path(
                grid, player, waypoint, candidates, set(),
                avoid_positions={switch},
            )
            if path:
                waypoint_exists = True
                break
        if not waypoint_exists:
            self.level2_v95_recovery_no_waypoint += 1
            return False
        self._v95_recovery_attempted_fps.add(masked_fp)
        self.level2_v95_recovery_resets += 1
        # Trigger V9.1's existing alternative-approach policy on next entry.
        self._v91_dead_end_resets += 1
        self.v90_request_reset = True
        return True

    def _v90_transition_avoid_actions(self, frame_fp, candidates):
        """Reject confirmed bad immediate transitions, not guessed future moves."""
        excluded = set()
        self._v90_current_traps = 0
        self._v90_current_loops = 0
        for action in candidates:
            sample = self._v90_transitions.get((frame_fp, action))
            if not sample:
                continue
            # An observed next frame can be a fully known dead-end;
            # avoid that approach BEFORE returning to the switch.
            next_fp = sample['after_fp']
            fully_bad = bool(next_fp) and all(
                (next_fp, key) in self._level2_risky_exits for key in DIRECTIONS
            )
            repeated_self_loop = sample['self_loops'] >= 2
            if sample['hazards'] or fully_bad or repeated_self_loop:
                excluded.add(action)
                if fully_bad:
                    self._v90_current_traps += 1
                if repeated_self_loop:
                    self._v90_current_loops += 1
        return excluded

    def _record_v90_transition(self, before, after, action_name):
        """Learn only from one actual LS20 level-2 action and visible frames."""
        if getattr(before, 'levels_completed', None) != LS20_LEVEL_2_INDEX:
            return
        if action_name not in DIRECTIONS:
            return
        before_grid = visible_grid(getattr(before, 'frame', None))
        if before_grid is None or locate_goal(before_grid) != LEVEL_2_GOAL:
            return
        before_pos = locate_player(before_grid)
        before_turns = shape_rotations_needed(before_grid, LEVEL_2_GOAL)
        visible_switch = locate_rotation_switch(before_grid) == LEVEL_2_ROTATION_SWITCH
        if (before_pos is None or before_turns is None or not (
                visible_switch or self._level2_landmark_validated)):
            return
        after_grid = visible_grid(getattr(after, 'frame', None))
        if after_grid is None:
            return
        before_fp = hashlib.sha256(bytes(z for row in before_grid for z in row)).hexdigest()[:16]
        after_fp = hashlib.sha256(bytes(z for row in after_grid for z in row)).hexdigest()[:16]
        key = (before_fp, action_name)
        sample = self._v90_transitions.get(key)
        if sample is None:
            if len(self._v90_transitions) >= self._v90_max_pairs:
                self.level2_transition_memory_full += 1
                return
            sample = {'attempts': 0, 'hazards': 0, 'self_loops': 0, 'after_fp': None}
            self._v90_transitions[key] = sample
        # Store the last *observed* successor. No invented map transitions.
        sample['attempts'] += 1
        sample['after_fp'] = after_fp
        sample['self_loops'] += int(after_fp == before_fp)
        self.level2_transition_self_loops += int(after_fp == before_fp)
        next_level = getattr(after, 'levels_completed', None)
        new_state = getattr(getattr(after, 'state', None), 'name', 'UNKNOWN')
        after_turns = (
            shape_rotations_needed(after_grid, LEVEL_2_GOAL)
            if locate_goal(after_grid) == LEVEL_2_GOAL else None
        )
        # Mark a hazard ONLY if the outcome is explicitly witnessed.
        hazard = (new_state == 'GAME_OVER') or (
            next_level == LS20_LEVEL_2_INDEX and
            before_turns == 0 and after_turns is not None and after_turns != 0
        )
        if hazard:
            sample['hazards'] += 1
            self.level2_transition_hazard_samples += 1
        self.level2_transition_samples += 1

    def _v91_pre_switch_route(self, grid, player, switch, candidates, blocked):
        """Trial a different visible approach AFTER an observed dead-end RESET.

        Uses only validated current pixels and a bounded pathfinder. Never
        chooses a historically dangerous switch EXIT and never assumes a tile
        is safe merely because it is visibly passable. No persistent memory.
        """
        if self._v91_dead_end_resets == 0 or player == switch:
            return None
        if self._v91_approach_waypoint is None:
            for _, (dx, dy) in DIRECTIONS.items():
                waypoint = (switch[0] + dx, switch[1] + dy)
                if waypoint in self._v92_confirmed_dead_end_approaches:
                    self.level2_v92_approaches_skipped += 1
                    continue
                if waypoint in self._v91_waypoints_tried or not _passable(grid, *waypoint):
                    continue
                # The route to the approach point must NOT transit the switch.
                path = shortest_visible_path(grid, player, waypoint, candidates,
                                             blocked, avoid_positions={switch})
                if path is None:
                    continue
                # Reaching an adjacent tile is a hypothesis, not a win.
                self._v91_waypoints_tried.add(waypoint)
                self._v91_approach_waypoint = waypoint
                self.level2_v91_approaches_selected += 1
                break
        waypoint = self._v91_approach_waypoint
        if waypoint is None:
            if self._v91_exhausted_reported_for != self._v91_dead_end_resets:
                self._v91_exhausted_reported_for = self._v91_dead_end_resets
                self.level2_v91_approaches_exhausted += 1
            return None
        if player == waypoint:
            move = next((name for name, (dx, dy) in DIRECTIONS.items()
                         if (player[0] + dx, player[1] + dy) == switch), None)
            if move not in candidates or (player, move) in blocked or not _passable(grid, *switch):
                self._v91_approach_waypoint = None
                return None
            self._v91_approach_waypoint = None
        else:
            path = shortest_visible_path(grid, player, waypoint, candidates,
                                         blocked, avoid_positions={switch})
            if not path:
                self._v91_approach_waypoint = None
                return None
            move = path[0]
        self._pending = (player, move, LS20_LEVEL_2_INDEX)
        self.last_reason = 'v91_observed_dead_end_alternate_approach'
        self.level2_v91_alternative_steps += 1
        self.proposals += 1
        self.level2_proposals += 1
        return move

    def _switch_cycle_step(self, grid, player, switch, rotations, candidates):
        """Suggest an exit/return ONLY for verified visible LS20 level-2.

        No assumed game rules: rotation is credited only if a later visible
        frame changes the current-vs-target shape orientation. If this fails,
        stop forcing the cycle after three unconfirmed attempts.
        """
        if player == switch and not self._switch_previous_contact:
            self.level2_switch_contacts += 1
        self._switch_previous_contact = player == switch

        if self._switch_plan is not None:
            phase, exit_pos, return_action, prior_rotations = self._switch_plan
            if rotations != prior_rotations:
                self.level2_pose_changes_observed += 1
                self._switch_retry_count = 0
                self._switch_used_exits.clear()
                self._switch_plan = None
                # If aligned, the caller will route toward the visible goal.
                if rotations == 0:
                    return None
            elif phase == 'exit' and player == exit_pos:
                # Exit was observed; try stepping back onto the visible switch.
                dx, dy = DIRECTIONS[return_action]
                if (player[0] + dx, player[1] + dy) == switch and _passable(grid, *switch):
                    self._switch_plan = ('return', exit_pos, return_action, prior_rotations)
                    self.level2_switch_returns_proposed += 1
                    self.last_reason = 'switch_return_to_verify_pose'
                    return return_action
                self._switch_plan = None
            elif phase == 'return' and player == switch:
                # Re-entered with no observable pose change.
                self.level2_switch_cycles_stalled += 1
                self._switch_retry_count += 1
                self._switch_plan = None
            elif phase == 'exit' and player == switch:
                # Exit was blocked or not executed; attempt another neighbor.
                self._switch_plan = None
            elif phase == 'return' and player == exit_pos:
                # Re-attempt return while the frame and route remain valid.
                dx, dy = DIRECTIONS[return_action]
                if (player[0] + dx, player[1] + dy) == switch and _passable(grid, *switch):
                    self.level2_switch_returns_proposed += 1
                    self.last_reason = 'switch_return_retry'
                    return return_action
                self._switch_plan = None
            else:
                # Unexpected screen transition: do not hallucinate contact.
                self._switch_plan = None

        if rotations == 0 or player != switch:
            return None
        if self._switch_retry_count >= 3:
            self.level2_switch_retry_exhausted += 1
            self.last_reason = 'switch_cycles_unconfirmed'
            return None

        # A step off the switch followed by a step back is a controlled
        # hypothesis, not a claim that this mechanic rotates the shape.
        for action, (dx, dy) in DIRECTIONS.items():
            if action not in candidates or action in self._switch_used_exits:
                continue
            exit_pos = (player[0] + dx, player[1] + dy)
            return_action = next((a for a, (rx, ry) in DIRECTIONS.items()
                                  if (rx, ry) == (-dx, -dy)), None)
            if return_action not in candidates or not _passable(grid, *exit_pos):
                continue
            if (player, action) in self._blocked:
                continue
            self._switch_used_exits.add(action)
            self._switch_plan = ('exit', exit_pos, return_action, rotations)
            self.level2_switch_exits_proposed += 1
            self.last_reason = 'switch_exit_to_retry_rotation'
            return action
        return None

    def propose(
        self,
        frames: Sequence[Any],
        level: int,
        candidates: Sequence[str],
    ) -> str | None:
        self.v90_request_reset = False
        if (
            self._last_level is not None
            and level != self._last_level
        ):
            self._blocked.clear()
            self._pending = None
            self._reset_switch_state()

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

            if goal != LEVEL_2_GOAL:
                self._pending = None
                return self._fallback("unvalidated_level")
            if rotation_tile == LEVEL_2_ROTATION_SWITCH:
                self._level2_landmark_validated = True
            elif not (
                self._level2_landmark_validated
                and player == LEVEL_2_ROTATION_SWITCH
            ):
                # A player sprite may occlude the switch glyph. Only permit
                # that exact occlusion AFTER prior visible-frame validation.
                self._pending = None
                return self._fallback("unvalidated_level")
            rotation_tile = LEVEL_2_ROTATION_SWITCH

        if self._pending is not None:
            previous, action, previous_level = self._pending

            if previous_level == level and previous == player:
                self._blocked.add((previous, action))
                self.blocked_moves += 1

        self._pending = None

        turns = shape_rotations_needed(grid, goal)
        if turns is None:
            # Missing visual evidence must not count as alignment loss.
            return self._fallback("pose_not_visible")

        if level == LS20_LEVEL_2_INDEX:
            self._level2_observations += 1
            previous = self._level2_last_visible
            if self._level2_was_aligned and turns != 0:
                self.level2_alignment_lost += 1
                if len(self.level2_alignment_events) < 16:
                    self.level2_alignment_events.append({
                        "event_index": self.level2_alignment_lost,
                        "level2_observation": self._level2_observations,
                        "previous_player": list(previous["player"]) if previous else None,
                        "current_player": list(player),
                        "switch": list(LEVEL_2_ROTATION_SWITCH),
                        "previous_rotations": previous["rotations"] if previous else 0,
                        "current_rotations": turns,
                        "previous_proposed_action": previous.get("proposed_action") if previous else None,
                        "previous_selected_action": previous.get("selected_action") if previous else None,
                        "previous_planner_reason": previous.get("planner_reason") if previous else None,
                        "previous_on_switch": previous["player"] == LEVEL_2_ROTATION_SWITCH if previous else None,
                        "current_on_switch": player == LEVEL_2_ROTATION_SWITCH,
                        "source": "visible_frame",
                    })
            self._level2_was_aligned = turns == 0
            self._level2_last_visible = {
                "player": player,
                "rotations": turns,
                "planner_reason": None,
                "proposed_action": None,
                "selected_action": None,
            }

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
            if level == LS20_LEVEL_2_INDEX and player != goal:
                self.level2_goal_routes_after_alignment += 1

        # V8.5 switch-cycle recovery is scoped to validated level-2 frames.
        # A proposed cycle is a testable hypothesis, not a solved-game claim.
        if level == LS20_LEVEL_2_INDEX:
            cycle = self._switch_cycle_step(
                grid, player, rotation_tile, turns, candidates
            )
            if cycle is not None:
                self.proposals += 1
                self.level2_proposals += 1
                return cycle
            if turns and player == rotation_tile:
                # Never mistake being on the switch for a successful route.
                return self._fallback('switch_awaits_observed_rotation')

        # Never intentionally route BACK onto the visible rotation
        # switch once the rendered current shape matches the goal.
        # Leaving the switch (when already standing on it) is allowed.
        aligned_level2 = level == LS20_LEVEL_2_INDEX and turns == 0
        # Guard only exact known visible level-2 frames: no coordinate-only
        # assumptions, no hidden engine information, no other-game changes.
        risky_actions = set()
        guarded_blocked = self._blocked
        v93_avoided = set()
        v94_avoided = set()
        if aligned_level2 and player == LEVEL_2_ROTATION_SWITCH:
            fp = hashlib.sha256(bytes(v for row in grid for v in row)).hexdigest()[:16]
            risky_actions = {
                action for action in candidates
                if (fp, action) in self._level2_risky_exits
            }
            if risky_actions:
                self.level2_exit_guard_activations += 1
                guarded_blocked = self._blocked | {(player, a) for a in risky_actions}

        # Learn from real immediate outcomes. An observed successor that
        # already has four failed switch exits is a trap to approach differently.
        # This is an EXACT visible-frame match, never a coordinate heuristic.
        if level == LS20_LEVEL_2_INDEX:
            frame_fp = hashlib.sha256(bytes(z for row in grid for z in row)).hexdigest()[:16]
            avoided = self._v90_transition_avoid_actions(frame_fp, candidates)
            # V9.3: only a twice-observed complete, progress-free cycle
            # marks its EXACT next state/action for an experimental detour.
            # Never override a visibly aligned goal route or force a move
            # when there is no other visibly passable candidate.
            if turns and player != rotation_tile:
                short_repeated = {
                    a for a in candidates
                    if (_v93_visible_state_fp(grid), a) in self._v94_short_guard_pairs
                }
                repeated = {
                    a for a in candidates
                    if (_v93_visible_state_fp(grid), a) in self._v93_repeated_actions
                } | short_repeated
                viable_other = any(
                    a not in repeated and (player, a) not in guarded_blocked
                    and _passable(grid, player[0] + DIRECTIONS[a][0],
                                  player[1] + DIRECTIONS[a][1])
                    for a in candidates if a in DIRECTIONS
                )
                if repeated and viable_other:
                    v93_avoided = repeated
                    if short_repeated:
                        v94_avoided = short_repeated
                        self.level2_v94_guard_activations += 1
                    guarded_blocked = guarded_blocked | {(player, a) for a in repeated}
                    self.level2_v93_guard_activations += 1
                elif repeated:
                    if short_repeated:
                        self.level2_v94_no_alternative += 1
                        # Diagnosing a short-cycle dead end never changes
                        # the candidate list or the chosen action.
                        self.level2_v95_no_alternative_events_total += 1
                        if len(self._v95_no_alternative_events) < 8:
                            passable = sorted(a for a in candidates
                                if a in DIRECTIONS and _passable(
                                    grid, player[0] + DIRECTIONS[a][0],
                                    player[1] + DIRECTIONS[a][1]))
                            self._v95_no_alternative_events.append({
                                "frame_fp": _v93_visible_state_fp(grid),
                                "player": list(player),
                                "repeated_actions": sorted(repeated),
                                "passable_actions": passable,
                                "blocked_actions": sorted(a for a in passable
                                    if (player, a) in guarded_blocked),
                                "source": "validated_visible_level2",
                            })
                    self.level2_v93_no_alternative += 1
                    if (short_repeated and self._v95_try_recovery_reset(
                            grid, player, rotation_tile,
                            _v93_visible_state_fp(grid), candidates)):
                        return self._fallback(
                            "v95_observed_short_cycle_no_route_recovery")
            if aligned_level2 and player == LEVEL_2_ROTATION_SWITCH:
                avoided.update(a for a in candidates if (frame_fp, a) in self._level2_risky_exits)
            if avoided:
                guarded_blocked = guarded_blocked | {(player, a) for a in avoided}
                self.level2_transition_guarded_choices += 1
                self.level2_transition_trap_avoids += self._v90_current_traps
                self.level2_transition_loop_avoids += self._v90_current_loops
            # Every visible move from this exact aligned switch frame has
            # FAILED before. The default fallback might repeat a known
            # dangerous action; ask the agent for an explicit bounded RESET.
            if (aligned_level2 and player == LEVEL_2_ROTATION_SWITCH
                    and candidates and all(
                        (frame_fp, a) in self._level2_risky_exits for a in candidates
                    )):
                self.v90_request_reset = True
                self.level2_transition_forced_resets += 1
                self._v91_dead_end_resets += 1
                # Only a real, matching inbound transition can disqualify
                # this approach; neither coordinates nor a route guess suffice.
                entry = self._v92_last_observed_entry
                if entry is not None and entry[1] == frame_fp:
                    was_new = entry[0] not in self._v92_confirmed_dead_end_approaches
                    self._v92_confirmed_dead_end_approaches.add(entry[0])
                    self.level2_v92_verified_bad_approaches += int(was_new)
                    self._v92_last_observed_entry = None
                return self._fallback('v90_all_switch_exits_observed_bad')

        # Only after a confirmed dead-end RESET, attempt a different
        # approach to the visible rotation switch, never an untested exit.
        # This is conditional on the same validated level-2 frame gate.
        if level == LS20_LEVEL_2_INDEX and turns and player != rotation_tile:
            alternate = self._v91_pre_switch_route(
                grid, player, rotation_tile, candidates, guarded_blocked
            )
            if alternate is not None:
                if v93_avoided and alternate not in v93_avoided:
                    self.level2_v93_detours_selected += 1
                    if v94_avoided:
                        self.level2_v94_detours_selected += 1
                return alternate

        route = shortest_visible_path(
            grid,
            player,
            destination,
            candidates,
            guarded_blocked,
            avoid_positions={LEVEL_2_ROTATION_SWITCH} if aligned_level2 else None,
        )
        if not route and risky_actions:
            self.level2_exit_guard_no_route += 1
            # A visually passable NEW action is an experimental alternative,
            # not a promise that the game engine will take a nominal step.
            for candidate in DIRECTIONS:
                if candidate not in candidates or candidate in risky_actions:
                    continue
                dx, dy = DIRECTIONS[candidate]
                if (player, candidate) in self._blocked:
                    continue
                if not _passable(grid, player[0] + dx, player[1] + dy):
                    continue
                self._pending = (player, candidate, level)
                self.last_reason = 'v89_observed_exit_risk_exploration'
                self.level2_exit_guard_alternatives += 1
                self.proposals += 1
                self.level2_proposals += 1
                return candidate
            # No verified visible alternative: fail closed to old policy,
            # and report that guarding did not guarantee a safe move.
            return self._fallback('v89_risky_exit_no_visible_alternative')

        if not route:
            # Bounded experimental detour when the normal switch route is
            # unavailable after excluding one twice-observed loop action.
            # This is NOT a claim that the destination is safe or a win.
            if v93_avoided and level == LS20_LEVEL_2_INDEX and turns:
                for candidate in DIRECTIONS:
                    if (candidate not in candidates or candidate in v93_avoided
                            or (player, candidate) in guarded_blocked):
                        continue
                    dx, dy = DIRECTIONS[candidate]
                    if not _passable(grid, player[0] + dx, player[1] + dy):
                        continue
                    self._pending = (player, candidate, level)
                    self.last_reason = 'v93_observed_cycle_visible_detour'
                    self.level2_v93_detours_selected += 1
                    if v94_avoided:
                        self.level2_v94_detours_selected += 1
                    self.proposals += 1
                    self.level2_proposals += 1
                    return candidate
            if aligned_level2:
                self.level2_aligned_goal_route_blocked += 1
                return self._fallback('aligned_safe_goal_route_not_visible')
            return self._fallback("no_visible_route")

        if aligned_level2:
            self.level2_aligned_safe_routes += 1

        action = route[0]
        if v93_avoided and action not in v93_avoided:
            self.level2_v93_detours_selected += 1
            if v94_avoided:
                self.level2_v94_detours_selected += 1
            reason = 'v93_observed_cycle_route_detour'
        if risky_actions and action not in risky_actions:
            self.level2_exit_guard_alternatives += 1
            reason = 'v89_observed_exit_risk_safe_route'
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
        if self._last_level == LS20_LEVEL_2_INDEX and self._level2_last_visible is not None:
            self._level2_last_visible["proposed_action"] = proposal
            self._level2_last_visible["selected_action"] = selected
            self._level2_last_visible["planner_reason"] = self.last_reason
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

    def record_frame_transition(self, before, after, action_name, *, step_index):
        """Record switch exits and learn bounded observed level-2 transitions.

        A nominal 5px movement is only the planner-grid reference, NOT a
        verified statement about how the game engine interprets a key press.
        Frame fingerprints are bounded hashes, never hidden game state.
        """
        try:
            self._v93_observe_repeated_cycle(before, after, action_name)
        except Exception:
            # Observation failure cannot change agent actions.
            self.level2_v93_observation_errors += 1
        try:
            self._v92_observe_switch_entry(before, after, action_name)
        except Exception:
            # Telemetry must never fail or change a game action.
            pass
        try:
            self._record_v90_transition(before, after, action_name)
        except Exception:
            # Never break an ARC action to collect telemetry.
            self.level2_transition_errors += 1
        try:
            if getattr(before, "levels_completed", None) != LS20_LEVEL_2_INDEX:
                return
            if action_name not in DIRECTIONS:
                return
            before_grid = visible_grid(getattr(before, "frame", None))
            if before_grid is None:
                return
            before_player = locate_player(before_grid)
            before_goal = locate_goal(before_grid)
            if before_player != LEVEL_2_ROTATION_SWITCH or before_goal != LEVEL_2_GOAL:
                return
            before_turns = shape_rotations_needed(before_grid, before_goal)
            if before_turns != 0:
                return

            self.level2_switch_exit_transitions_total += 1
            if len(self.level2_switch_exit_transitions) >= 16:
                return

            after_grid = visible_grid(getattr(after, "frame", None))
            after_player = locate_player(after_grid) if after_grid is not None else None
            after_goal = locate_goal(after_grid) if after_grid is not None else None
            after_turns = (
                shape_rotations_needed(after_grid, after_goal)
                if after_grid is not None and after_goal is not None else None
            )
            dx, dy = DIRECTIONS[action_name]
            nominal_next = (before_player[0] + dx, before_player[1] + dy)
            actual_delta = (
                (after_player[0] - before_player[0],
                 after_player[1] - before_player[1])
                if after_player is not None else None
            )
            old_state = getattr(getattr(before, "state", None), "name", "UNKNOWN")
            new_state = getattr(getattr(after, "state", None), "name", "UNKNOWN")
            before_fp = hashlib.sha256(bytes(p for row in before_grid for p in row)).hexdigest()[:16]
            self.level2_switch_exit_transitions.append({
                "step_index": step_index if isinstance(step_index, int) else None,
                "selected_action": action_name,
                "before_player": list(before_player),
                "after_player": list(after_player) if after_player is not None else None,
                "switch": list(LEVEL_2_ROTATION_SWITCH),
                "nominal_delta": [dx, dy],
                "nominal_next_player": list(nominal_next),
                "observed_delta": list(actual_delta) if actual_delta is not None else None,
                "nominal_step_match": after_player == nominal_next if after_player is not None else None,
                "before_rotations": before_turns,
                "after_rotations": after_turns,
                "alignment_lost": after_turns is not None and after_turns != 0,
                "before_level": before.levels_completed,
                "after_level": getattr(after, "levels_completed", None),
                "before_state": str(old_state)[:32],
                "after_state": str(new_state)[:32],
                "after_full_reset": getattr(after, "full_reset", None) is True,
                "before_frame_fp": before_fp,
                "after_frame_fp": (
                    hashlib.sha256(bytes(p for row in after_grid for p in row)).hexdigest()[:16]
                    if after_grid is not None else None
                ),
                "source": "visible_action_before_after",
            })
            # Only failed real after-frames justify a run-local risk mark.
            if (getattr(after, 'levels_completed', None) == LS20_LEVEL_2_INDEX
                    and (new_state == 'GAME_OVER' or (after_turns is not None and after_turns != 0))
                    and len(self._level2_risky_exits) < 64):
                old_size = len(self._level2_risky_exits)
                self._level2_risky_exits.add((before_fp, action_name))
                self.level2_exit_guard_new_risks += len(self._level2_risky_exits) - old_size
        except Exception:
            # Diagnosing a bad frame can NEVER interfere with the game action.
            self.level2_switch_exit_transition_errors += 1

    def summary(self) -> dict[str, Any]:
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
            "level2_switch_contacts": self.level2_switch_contacts,
            "level2_switch_exits_proposed": self.level2_switch_exits_proposed,
            "level2_switch_returns_proposed": self.level2_switch_returns_proposed,
            "level2_pose_changes_observed": self.level2_pose_changes_observed,
            "level2_switch_cycles_stalled": self.level2_switch_cycles_stalled,
            "level2_switch_retry_exhausted": self.level2_switch_retry_exhausted,
            "level2_goal_routes_after_alignment": self.level2_goal_routes_after_alignment,
            "level2_aligned_safe_routes": self.level2_aligned_safe_routes,
            "level2_aligned_goal_route_blocked": self.level2_aligned_goal_route_blocked,
            "level2_alignment_lost": self.level2_alignment_lost,
            "level2_alignment_events": list(self.level2_alignment_events),
            "level2_switch_exit_transitions_total": self.level2_switch_exit_transitions_total,
            "level2_switch_exit_transition_errors": self.level2_switch_exit_transition_errors,
            "level2_switch_exit_transitions": list(self.level2_switch_exit_transitions),
            "level2_exit_guard_activations": self.level2_exit_guard_activations,
            "level2_exit_guard_alternatives": self.level2_exit_guard_alternatives,
            "level2_exit_guard_no_route": self.level2_exit_guard_no_route,
            "level2_exit_guard_new_risks": self.level2_exit_guard_new_risks,
            # Aggregate counters ONLY: do not overflow 16KB ARCRun logs.
            "level2_transition_samples": self.level2_transition_samples,
            "level2_transition_distinct_pairs": len(self._v90_transitions),
            "level2_transition_hazard_samples": self.level2_transition_hazard_samples,
            "level2_transition_self_loops": self.level2_transition_self_loops,
            "level2_transition_memory_full": self.level2_transition_memory_full,
            "level2_transition_errors": self.level2_transition_errors,
            "level2_transition_trap_avoids": self.level2_transition_trap_avoids,
            "level2_transition_loop_avoids": self.level2_transition_loop_avoids,
            "level2_transition_guarded_choices": self.level2_transition_guarded_choices,
            "level2_transition_forced_resets": self.level2_transition_forced_resets,
            "level2_v91_dead_end_resets": self._v91_dead_end_resets,
            "level2_v91_alternative_steps": self.level2_v91_alternative_steps,
            "level2_v91_approaches_selected": self.level2_v91_approaches_selected,
            "level2_v91_approaches_exhausted": self.level2_v91_approaches_exhausted,
            "level2_v91_distinct_waypoints": len(self._v91_waypoints_tried),
            "level2_v92_observed_entries": self.level2_v92_observed_entries,
            "level2_v92_verified_bad_approaches": self.level2_v92_verified_bad_approaches,
            "level2_v92_approaches_skipped": self.level2_v92_approaches_skipped,
            "level2_v93_observed_steps": self.level2_v93_observed_steps,
            "level2_v93_cycles_confirmed": self.level2_v93_cycles_confirmed,
            "level2_v93_unique_actions_blocked": self.level2_v93_unique_actions_blocked,
            "level2_v93_guard_activations": self.level2_v93_guard_activations,
            "level2_v93_detours_selected": self.level2_v93_detours_selected,
            "level2_v93_no_alternative": self.level2_v93_no_alternative,
            "level2_v93_observation_errors": self.level2_v93_observation_errors,
            "level2_v94_short_cycles_confirmed": self.level2_v94_short_cycles_confirmed,
            "level2_v94_unique_pairs_blocked": self.level2_v94_unique_pairs_blocked,
            "level2_v94_guard_activations": self.level2_v94_guard_activations,
            "level2_v94_detours_selected": self.level2_v94_detours_selected,
            "level2_v94_no_alternative": self.level2_v94_no_alternative,
            "level2_v94_observation_errors": self.level2_v94_observation_errors,
            "level2_v95_no_alternative_events_total": self.level2_v95_no_alternative_events_total,
            "level2_v95_no_alternative_events": list(self._v95_no_alternative_events),
            "level2_v95_recovery_resets": self.level2_v95_recovery_resets,
            "level2_v95_recovery_no_waypoint": self.level2_v95_recovery_no_waypoint,
            "level2_v95_recovery_repeat_suppressed": self.level2_v95_recovery_repeat_suppressed,
            "last_reason": self.last_reason,
        }
