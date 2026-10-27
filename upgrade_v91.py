"""Safely patch FeedbackExplorer V9.1 on its isolated V9.1 feature branch.

Never launches an ARC game. Rejects wrong branch, changed sources, and re-apply.
The feature is an experiment; it does NOT assert a solution or score gain.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

BRANCH = 'feat/feedback-explorer-v9-1-pre-switch-route-planning'
PLANNER = Path('ARC-AGI-3-Agents/agents/templates/ls20_visual_planner.py')
EXPLORER = Path('ARC-AGI-3-Agents/agents/templates/feedback_explorer.py')
OLD_TEST = Path('ARC-AGI-3-Agents/tests/test_feedback_v9_0_transition_learning.py')
NEW_TEST_SRC = Path('test_feedback_v9_1_pre_switch_route.py')
NEW_TEST_DST = Path('ARC-AGI-3-Agents/tests/test_feedback_v9_1_pre_switch_route.py')
EXPECTED_BLOBS = {
    PLANNER: 'ffac65adbdc706b05823af205c81e3f585632a16',
    EXPLORER: '5b15aeb71f2650c089e687c354799688aae38d8e',
    OLD_TEST: '5f9f5d914c55fd0f5b6773c4a0ad37c4421a6309',
}


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f'blob {len(data)}\0'.encode('ascii') + data).hexdigest()


def once(source: str, old: str, new: str, name: str) -> str:
    amount = source.count(old)
    if amount != 1:
        raise RuntimeError(f'SAFE ABORT: {name}: anchor count {amount}, expected 1')
    return source.replace(old, new, 1)


def generate() -> dict[Path, str]:
    branch = subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip()
    if branch != BRANCH:
        raise RuntimeError(f'SAFE ABORT: wrong branch {branch!r}; expected {BRANCH!r}')
    original: dict[Path, str] = {}
    for path, expected in EXPECTED_BLOBS.items():
        blob = path.read_bytes()
        found = git_blob_sha(blob)
        if found != expected:
            raise RuntimeError(f'SAFE ABORT: source blob drift {path}: {found} != {expected}')
        original[path] = blob.decode('utf-8')
    if not NEW_TEST_SRC.is_file() or NEW_TEST_DST.exists():
        raise RuntimeError('SAFE ABORT: V9.1 root test absent or destination already exists')

    planner = original[PLANNER]
    planner = once(planner,
        '        self._level2_landmark_validated = False\n\n    def reset_pending(self) -> None:',
        '''        self._level2_landmark_validated = False
        # V9.1: keep only bounded, in-run history of failed switch approaches.
        # The waypoint set has at most four *visible* switch-adjacent tiles.
        self._v91_dead_end_resets = 0
        self._v91_waypoints_tried = set()
        self._v91_approach_waypoint = None
        self._v91_exhausted_reported_for = 0
        self.level2_v91_alternative_steps = 0
        self.level2_v91_approaches_selected = 0
        self.level2_v91_approaches_exhausted = 0

    def reset_pending(self) -> None:''',
        'V9.1 bounded experiment state')
    planner = once(planner,
        '        self._level2_last_visible = None\n\n    def _v90_transition_avoid_actions',
        '''        self._level2_last_visible = None
        self._v91_approach_waypoint = None

    def _v90_transition_avoid_actions''',
        'reset ephemeral waypoint only')

    planner = once(planner,
        '    def _switch_cycle_step(self, grid, player, switch, rotations, candidates):\n',
        '''    def _v91_pre_switch_route(self, grid, player, switch, candidates, blocked):
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
''',
        'V9.1 alternate visible waypoint path')

    planner = once(planner,
        '''                self.v90_request_reset = True
                self.level2_transition_forced_resets += 1
                return self._fallback('v90_all_switch_exits_observed_bad')''',
        '''                self.v90_request_reset = True
                self.level2_transition_forced_resets += 1
                self._v91_dead_end_resets += 1
                return self._fallback('v90_all_switch_exits_observed_bad')''',
        'V9.1 failed-approach episode counter')

    planner = once(planner,
        '''        route = shortest_visible_path(
            grid,
            player,
            destination,
''',
        '''        # Only after a confirmed dead-end RESET, attempt a different
        # approach to the visible rotation switch, never an untested exit.
        # This is conditional on the same validated level-2 frame gate.
        if level == LS20_LEVEL_2_INDEX and turns and player != rotation_tile:
            alternate = self._v91_pre_switch_route(
                grid, player, rotation_tile, candidates, guarded_blocked
            )
            if alternate is not None:
                return alternate

        route = shortest_visible_path(
            grid,
            player,
            destination,
''',
        'pre-switch routing hook')

    planner = once(planner,
        '''            "level2_transition_forced_resets": self.level2_transition_forced_resets,
            "last_reason": self.last_reason,''',
        '''            "level2_transition_forced_resets": self.level2_transition_forced_resets,
            "level2_v91_dead_end_resets": self._v91_dead_end_resets,
            "level2_v91_alternative_steps": self.level2_v91_alternative_steps,
            "level2_v91_approaches_selected": self.level2_v91_approaches_selected,
            "level2_v91_approaches_exhausted": self.level2_v91_approaches_exhausted,
            "level2_v91_distinct_waypoints": len(self._v91_waypoints_tried),
            "last_reason": self.last_reason,''',
        'V9.1 bounded aggregated counters')

    agent = original[EXPLORER]
    agent = once(agent, 'AGENT_VERSION = "9.0"', 'AGENT_VERSION = "9.1"', 'V9.1 identity')
    agent = agent.replace('FeedbackExplorer V9.0:', 'FeedbackExplorer V9.1:')
    old_test = once(original[OLD_TEST], "self.assertIn('AGENT_VERSION = \"9.0\"', content)",
                    "self.assertIn('AGENT_VERSION = \"9.1\"', content)",
                    'keep V9.0 runtime interlock test compatible with new version')
    return {
        PLANNER: planner,
        EXPLORER: agent,
        OLD_TEST: old_test,
        NEW_TEST_DST: NEW_TEST_SRC.read_text(encoding='utf-8'),
    }


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    mode = args.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    options = args.parse_args()
    changes = generate()  # Validate ALL anchors before writing any file.
    for target, content in changes.items():
        compile(content, str(target), 'exec')
    if options.check:
        print('V9.1 SAFE CHECK PASSED: branch, blob SHAs, all anchors, compile.')
        return
    for target, content in changes.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    print('Applied V9.1 experiment; run full unit tests before committing.')


if __name__ == '__main__':
    main()
