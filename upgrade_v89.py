"""Fail-closed ARC FeedbackExplorer V8.9 visible-frame exit-risk guard.

This is an experiment, not a solved-game claim. Only LS20 level-2
validated visible frames are eligible. Reference observations are V8.8
read-only frame hashes; no hidden game state is consumed.

Create feature branch from V8.8 and run at repository root:
 python upgrade_v89.py --check
 python upgrade_v89.py --apply
"""
from __future__ import annotations
import argparse
import hashlib
import subprocess
from pathlib import Path

BRANCH = 'feat/feedback-explorer-v8-9-observed-exit-guard'
PLANNER = Path('ARC-AGI-3-Agents/agents/templates/ls20_visual_planner.py')
EXPLORER = Path('ARC-AGI-3-Agents/agents/templates/feedback_explorer.py')
RUNTIME_TEST = Path('ARC-AGI-3-Agents/tests/test_feedback_runtime_v8_1.py')
TEST_SRC = Path('test_feedback_v8_9_exit_guard.py')
TEST_DST = Path('ARC-AGI-3-Agents/tests/test_feedback_v8_9_exit_guard.py')
EXPECTED = {
    PLANNER: 'c5c448afb26516e7351e29909c3303c53a251bec',
    EXPLORER: '3c0835735cc5e31e2b15e3b00853485b9e5d72d2',
    RUNTIME_TEST: '94833f56c02d2115c4658cf4e510aafb1b25bc44',
}


def sha(blob: bytes) -> str:
    return hashlib.sha1(f'blob {len(blob)}\0'.encode() + blob).hexdigest()


def once(s: str, old: str, new: str, name: str) -> str:
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f'SAFE ABORT: {name}: expected exactly 1 anchor, found {n}')
    return s.replace(old, new, 1)


def patch() -> dict[Path, str]:
    branch = subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip()
    if branch != BRANCH:
        raise RuntimeError(f'SAFE ABORT: branch {branch!r} != {BRANCH!r}')
    contents = {}
    for path, expected in EXPECTED.items():
        current = path.read_bytes()
        if sha(current) != expected:
            raise RuntimeError(f'SAFE ABORT: {path}: content hash changed (expected {expected}, got {sha(current)})')
        contents[path] = current.decode('utf-8')
    if not TEST_SRC.is_file() or TEST_DST.exists():
        raise RuntimeError('SAFE ABORT: test source missing or target already exists')

    s = contents[PLANNER]
    s = once(s,
        'LEVEL_2_ROTATION_SWITCH = (49, 45)\n',
        '''LEVEL_2_ROTATION_SWITCH = (49, 45)

# V8.8 genuine before-frame fingerprints in the 27 Oct read-only test.
# These are observations of failed ACTION1 exits, NOT inferred game rules.
# Match the entire displayed 64x64 frame, not merely player coordinates.
V88_OBSERVED_RISKY_EXIT_FPS = frozenset({
    'e58c8a39094e9e8f',  # alignment lost, observed -20,-5
    '70c046c20de8d462',  # alignment lost, observed -20,-5
    '869a0f09dcb2c63c',  # game over after nominal movement
})
''', 'observed visible fingerprints')
    s = once(s,
        '        self.level2_switch_exit_transition_errors = 0\n        self._switch_plan = None',
        '''        self.level2_switch_exit_transition_errors = 0
        # V8.9: specific real visible observations from V8.8, plus
        # newly observed risks during THIS run. Persist during RESET
        # inside a run so identical failures do not loop forever.
        self._level2_risky_exits = {(fp, 'ACTION1') for fp in V88_OBSERVED_RISKY_EXIT_FPS}
        self.level2_exit_guard_activations = 0
        self.level2_exit_guard_alternatives = 0
        self.level2_exit_guard_no_route = 0
        self.level2_exit_guard_new_risks = 0
        self._switch_plan = None''', 'planner risk state')
    s = once(s,
        '''        aligned_level2 = level == LS20_LEVEL_2_INDEX and turns == 0
        route = shortest_visible_path(
            grid,
            player,
            destination,
            candidates,
            self._blocked,
            avoid_positions={LEVEL_2_ROTATION_SWITCH} if aligned_level2 else None,
        )
''',
        '''        aligned_level2 = level == LS20_LEVEL_2_INDEX and turns == 0
        # Guard only exact known visible level-2 frames: no coordinate-only
        # assumptions, no hidden engine information, no other-game changes.
        risky_actions = set()
        guarded_blocked = self._blocked
        if aligned_level2 and player == LEVEL_2_ROTATION_SWITCH:
            fp = hashlib.sha256(bytes(v for row in grid for v in row)).hexdigest()[:16]
            risky_actions = {
                action for action in candidates
                if (fp, action) in self._level2_risky_exits
            }
            if risky_actions:
                self.level2_exit_guard_activations += 1
                guarded_blocked = self._blocked | {(player, a) for a in risky_actions}

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
''', 'guard visible planned routes')
    s = once(s,
        '''        action = route[0]
        self._pending = (player, action, level)
        self.last_reason = reason
''',
        '''        action = route[0]
        if risky_actions and action not in risky_actions:
            self.level2_exit_guard_alternatives += 1
            reason = 'v89_observed_exit_risk_safe_route'
        self._pending = (player, action, level)
        self.last_reason = reason
''', 'guard alternative counter')
    s = once(s,
        '''            self.level2_switch_exit_transitions.append({
''',
        '''            before_fp = hashlib.sha256(bytes(p for row in before_grid for p in row)).hexdigest()[:16]
            self.level2_switch_exit_transitions.append({
''', 'before frame hash')
    s = once(s,
        '''                "before_frame_fp": hashlib.sha256(bytes(p for row in before_grid for p in row)).hexdigest()[:16],
''',
        '''                "before_frame_fp": before_fp,
''', 'replace hash repetition')
    s = once(s,
        '''                "source": "visible_action_before_after",
            })
        except Exception:
''',
        '''                "source": "visible_action_before_after",
            })
            # Only failed real after-frames justify a run-local risk mark.
            if (getattr(after, 'levels_completed', None) == LS20_LEVEL_2_INDEX
                    and (new_state == 'GAME_OVER' or (after_turns is not None and after_turns != 0))
                    and len(self._level2_risky_exits) < 64):
                old_size = len(self._level2_risky_exits)
                self._level2_risky_exits.add((before_fp, action_name))
                self.level2_exit_guard_new_risks += len(self._level2_risky_exits) - old_size
        except Exception:
''', 'learn observed risk')
    s = once(s,
        '''            "level2_switch_exit_transitions": list(self.level2_switch_exit_transitions),
            "last_reason": self.last_reason,
''',
        '''            "level2_switch_exit_transitions": list(self.level2_switch_exit_transitions),
            "level2_exit_guard_activations": self.level2_exit_guard_activations,
            "level2_exit_guard_alternatives": self.level2_exit_guard_alternatives,
            "level2_exit_guard_no_route": self.level2_exit_guard_no_route,
            "level2_exit_guard_new_risks": self.level2_exit_guard_new_risks,
            "last_reason": self.last_reason,
''', 'V8.9 summary counters')

    e = contents[EXPLORER]
    e = once(e, '    AGENT_VERSION = "8.8"', '    AGENT_VERSION = "8.9"', 'agent version')
    e = once(e, 'FeedbackExplorer V8.8 action-transition diagnostics:',
             'FeedbackExplorer V8.9 observed switch-exit guard experiment:', 'module header')
    e = once(e, 'FeedbackExplorer V8.8: start or restart game',
             'FeedbackExplorer V8.9: start or restart game', 'reset reasoning')
    e = once(e, 'FeedbackExplorer V8.8: {action_name}',
             'FeedbackExplorer V8.9: {action_name}', 'action reasoning')
    t = once(contents[RUNTIME_TEST], 'self.assertEqual(versions, ["8.8"])',
             'self.assertEqual(versions, ["8.9"])', 'runtime version test')
    return {PLANNER: s, EXPLORER: e, RUNTIME_TEST: t}


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    changes = patch()  # Every hash and anchor validated BEFORE any file write.
    if args.check:
        print('V8.8 blobs, target branch and V8.9 anchors OK; no changes made.')
        return
    for path, value in changes.items():
        path.write_text(value, encoding='utf-8')
    TEST_DST.write_bytes(TEST_SRC.read_bytes())
    print('V8.9 isolated LS20 switch-exit guard applied; run all regression tests before commit.')


if __name__ == '__main__':
    main()
