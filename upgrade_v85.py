#!/usr/bin/env python3
"""Apply FeedbackExplorer V8.5 switch-cycle diagnostics and conservative recovery.

GitHub Actions may run this script from the repository root. It validates all
source anchors before writing, never changes secrets, deployment or main.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
AGENTS = ROOT / 'ARC-AGI-3-Agents' / 'agents' / 'templates'
TESTS = ROOT / 'ARC-AGI-3-Agents' / 'tests'


def replace_once(source: str, before: str, after: str, name: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f'{name}: expected exactly one source anchor, found {count}; nothing changed')
    return source.replace(before, after, 1)


def updates() -> dict[Path, str]:
    test_pack = ROOT / 'test_feedback_v8_5_rotation_state.py'
    test_target = TESTS / test_pack.name
    if not test_pack.is_file():
        raise FileNotFoundError(f'Missing V8.5 test file: {test_pack}')
    if test_target.exists():
        raise RuntimeError('V8.5 tests already installed. Refusing to overwrite existing code.')

    agent_path = AGENTS / 'feedback_explorer.py'
    planner_path = AGENTS / 'ls20_visual_planner.py'
    probe_test_path = TESTS / 'test_feedback_runtime_v8_1.py'
    for p in (agent_path, planner_path, probe_test_path):
        if not p.is_file():
            raise FileNotFoundError(f'Missing source file: {p}')
    agent = agent_path.read_text(encoding='utf-8')
    planner = planner_path.read_text(encoding='utf-8')
    probe = probe_test_path.read_text(encoding='utf-8')

    agent = replace_once(agent, '\nFeedbackExplorer V8.4:\n', '\nFeedbackExplorer V8.5:\n', 'agent description')
    agent = replace_once(agent, 'AGENT_VERSION = "8.4"', 'AGENT_VERSION = "8.5"', 'agent version')
    agent = replace_once(agent,
        '"FeedbackExplorer V8.4: start or restart game"',
        '"FeedbackExplorer V8.5: start or restart game"', 'reset reason')
    agent = replace_once(agent,
        'f"FeedbackExplorer V8.4: {action_name}; "',
        'f"FeedbackExplorer V8.5: {action_name}; "', 'action reason')
    probe = replace_once(probe, 'self.assertEqual(versions, ["8.4"])',
                         'self.assertEqual(versions, ["8.5"])', 'runtime version assertion')

    old_fields = '''        self.level2_reverse_filter_overrides = 0
'''
    new_fields = '''        self.level2_reverse_filter_overrides = 0
        # V8.5: inspect switch contact and attempt at most three visible
        # exit/re-entry cycles when the shape still requires rotation.
        self.level2_switch_contacts = 0
        self.level2_switch_exits_proposed = 0
        self.level2_switch_returns_proposed = 0
        self.level2_pose_changes_observed = 0
        self.level2_switch_cycles_stalled = 0
        self.level2_switch_retry_exhausted = 0
        self.level2_goal_routes_after_alignment = 0
        self._switch_plan = None  # (phase, exit_position, return_action, rotations_before)
        self._switch_previous_contact = False
        self._switch_retry_count = 0
        self._switch_used_exits = set()
        self._level2_landmark_validated = False
'''
    planner = replace_once(planner, old_fields, new_fields, 'planner state')

    old_reset = '''    def reset_pending(self) -> None:
        """Clear temporary movement information after a reset."""
        self._pending = None
        self._blocked.clear()
'''
    new_reset = '''    def reset_pending(self) -> None:
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
'''
    planner = replace_once(planner, old_reset, new_reset, 'switch helper and reset')

    old_level_reset = '''            self._blocked.clear()
            self._pending = None

        self._last_level = level
'''
    new_level_reset = '''            self._blocked.clear()
            self._pending = None
            self._reset_switch_state()

        self._last_level = level
'''
    planner = replace_once(planner, old_level_reset, new_level_reset, 'level transition')

    old_landmark = '''        if level == LS20_LEVEL_2_INDEX:
            rotation_tile = locate_rotation_switch(grid)

            if (
                goal != LEVEL_2_GOAL
                or rotation_tile != LEVEL_2_ROTATION_SWITCH
            ):
                self._pending = None
                return self._fallback("unvalidated_level")
'''
    new_landmark = '''        if level == LS20_LEVEL_2_INDEX:
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
'''
    planner = replace_once(planner, old_landmark, new_landmark, 'occluded switch validation')

    old_destination = '''        if turns:
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
'''
    new_destination = '''        if turns:
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

        route = shortest_visible_path(
'''
    planner = replace_once(planner, old_destination, new_destination, 'switch route control')

    old_summary = '''            "level2_reverse_filter_overrides": self.level2_reverse_filter_overrides,
            "last_reason": self.last_reason,
'''
    new_summary = '''            "level2_reverse_filter_overrides": self.level2_reverse_filter_overrides,
            "level2_switch_contacts": self.level2_switch_contacts,
            "level2_switch_exits_proposed": self.level2_switch_exits_proposed,
            "level2_switch_returns_proposed": self.level2_switch_returns_proposed,
            "level2_pose_changes_observed": self.level2_pose_changes_observed,
            "level2_switch_cycles_stalled": self.level2_switch_cycles_stalled,
            "level2_switch_retry_exhausted": self.level2_switch_retry_exhausted,
            "level2_goal_routes_after_alignment": self.level2_goal_routes_after_alignment,
            "last_reason": self.last_reason,
'''
    planner = replace_once(planner, old_summary, new_summary, 'diagnostics summary')

    return {agent_path: agent, planner_path: planner, probe_test_path: probe}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--check', action='store_true')
    flags.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    changes = updates()  # validate every change before writing any file
    for p, text in changes.items():
        compile(text, str(p), 'exec')
    if args.check:
        print('V8.5 source anchors and Python syntax OK; no files changed.')
        return
    for p, text in changes.items():
        shutil.copy2(p, p.with_suffix(p.suffix + '.v84.bak'))
        p.write_text(text, encoding='utf-8')
        print('Updated:', p.relative_to(ROOT))
    src = ROOT / 'test_feedback_v8_5_rotation_state.py'
    dest = TESTS / src.name
    shutil.copy2(src, dest)
    print('Test installed:', dest.relative_to(ROOT))
    print('No merge, deployment or production changes were made by this script.')


if __name__ == '__main__':
    main()
