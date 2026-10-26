"""Fail-closed, diagnostic-only V8.8 patch for exact V8.7 commit 03c5d417.

Run at repository root:
  python upgrade_v88.py --check
  python upgrade_v88.py --apply

V8.8 observes individual ARC actions; it DOES NOT alter movement selection,
GameAction payloads, score calculation, or V8.7 alignment detection.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

PLANNER = Path('ARC-AGI-3-Agents/agents/templates/ls20_visual_planner.py')
EXPLORER = Path('ARC-AGI-3-Agents/agents/templates/feedback_explorer.py')
RUNTIME_TEST = Path('ARC-AGI-3-Agents/tests/test_feedback_runtime_v8_1.py')
NEW_TEST_SRC = Path('test_feedback_v8_8_switch_transition.py')
NEW_TEST_DST = Path('ARC-AGI-3-Agents/tests/test_feedback_v8_8_switch_transition.py')

# These Git blob SHA-1 hashes were read from the V8.7 feature branch.
# Explicitly abort when the source differs. NEVER patch main/Production.
EXPECTED_BLOBS = {
    PLANNER: '9a7e5c87382da288c1cd2914a885aec289268b17',
    EXPLORER: 'd6120548ced3b533a06597a693904caeeb255891',
    RUNTIME_TEST: 'f0fd346689927ad205f605e7b0054b012df14588',
}


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()


def once(source: str, old: str, new: str, name: str) -> str:
    n = source.count(old)
    if n != 1:
        raise RuntimeError(f'SAFE ABORT: {name} expected one anchor, found {n}')
    return source.replace(old, new, 1)


# Source is inserted as a class method on LS20VisualPlanner. It is called from
# FeedbackExplorer.take_action AFTER the environment returns a genuine frame.
# No steering, fallback or movement policy consumes this diagnostic data.
TRANSITION_METHOD = '''    def record_frame_transition(self, before, after, action_name, *, step_index):
        """Record visible one-action switch exits without changing decisions.

        A nominal 5px movement is only the planner-grid reference, NOT a
        verified statement about how the game engine interprets a key press.
        Frame fingerprints are bounded hashes, never hidden game state.
        """
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
                "before_frame_fp": hashlib.sha256(bytes(p for row in before_grid for p in row)).hexdigest()[:16],
                "after_frame_fp": (
                    hashlib.sha256(bytes(p for row in after_grid for p in row)).hexdigest()[:16]
                    if after_grid is not None else None
                ),
                "source": "visible_action_before_after",
            })
        except Exception:
            # Diagnosing a bad frame can NEVER interfere with the game action.
            self.level2_switch_exit_transition_errors += 1

'''


def plan() -> dict[Path, str]:
    data: dict[Path, str] = {}
    for path, blob in EXPECTED_BLOBS.items():
        raw = path.read_bytes()
        actual = git_blob_sha(raw)
        if actual != blob:
            raise RuntimeError(f'SAFE ABORT: {path}: blob {actual} != V8.7 {blob}')
        data[path] = raw.decode('utf-8')
    if not NEW_TEST_SRC.is_file() or NEW_TEST_DST.exists():
        raise RuntimeError('SAFE ABORT: V8.8 test source missing or destination exists')

    planner = data[PLANNER]
    planner = once(planner,
        'from __future__ import annotations\n\nfrom collections import deque',
        'from __future__ import annotations\n\nimport hashlib\nfrom collections import deque',
        'planner import')
    planner = once(planner,
        '        self._level2_last_visible = None\n        self._switch_plan = None',
        '        self._level2_last_visible = None\n'
        '        # V8.8: bounded observational evidence from immediate action frames.\n'
        '        self.level2_switch_exit_transitions = []\n'
        '        self.level2_switch_exit_transitions_total = 0\n'
        '        self.level2_switch_exit_transition_errors = 0\n'
        '        self._switch_plan = None',
        'planner counters')
    planner = once(planner,
        '    def summary(self) -> dict[str, Any]:\n',
        TRANSITION_METHOD + '    def summary(self) -> dict[str, Any]:\n',
        'planner method')
    planner = once(planner,
        '            "level2_alignment_events": list(self.level2_alignment_events),\n',
        '            "level2_alignment_events": list(self.level2_alignment_events),\n'
        '            "level2_switch_exit_transitions_total": self.level2_switch_exit_transitions_total,\n'
        '            "level2_switch_exit_transition_errors": self.level2_switch_exit_transition_errors,\n'
        '            "level2_switch_exit_transitions": list(self.level2_switch_exit_transitions),\n',
        'planner summary')

    explorer = data[EXPLORER]
    explorer = once(explorer, '    AGENT_VERSION = "8.7"', '    AGENT_VERSION = "8.8"', 'class version')
    explorer = once(explorer, '\nFeedbackExplorer V8.7 diagnostics:\n',
                    '\nFeedbackExplorer V8.8 action-transition diagnostics:\n', 'module header')
    explorer = once(explorer, 'FeedbackExplorer V8.7: start or restart game',
                    'FeedbackExplorer V8.8: start or restart game', 'reset reason')
    explorer = once(explorer, 'FeedbackExplorer V8.7: {action_name}',
                    'FeedbackExplorer V8.8: {action_name}', 'action reason')
    explorer = once(explorer,
        '        if after is not None:\n            self.diagnostics.record_action(',
        '        if after is not None:\n'
        '            # V8.8 read-only action boundary: actual returned frame.\n'
        '            planner = self._ls20_visual_planner\n'
        '            if planner is not None:\n'
        '                observe = getattr(planner, "record_frame_transition", None)\n'
        '                if callable(observe):\n'
        '                    observe(before, after, action.name, step_index=self.action_counter + 1)\n'
        '            self.diagnostics.record_action(',
        'action boundary')

    runtime = once(data[RUNTIME_TEST],
                   'self.assertEqual(versions, ["8.7"])',
                   'self.assertEqual(versions, ["8.8"])',
                   'runtime version assertion')
    return {PLANNER: planner, EXPLORER: explorer, RUNTIME_TEST: runtime}


def main():
    ap = argparse.ArgumentParser()
    modes = ap.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    changes = plan()  # ALL checks before ANY write.
    if args.check:
        print('V8.7 blob hashes and V8.8 anchors verified; no files changed.')
        return
    for path, source in changes.items():
        path.write_text(source, encoding='utf-8')
    NEW_TEST_DST.write_bytes(NEW_TEST_SRC.read_bytes())
    print('V8.8 read-only action-boundary diagnostics applied. Run tests before commit.')


if __name__ == '__main__':
    main()
