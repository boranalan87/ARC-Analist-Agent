"""Apply a bounded, observed-only ARC FeedbackExplorer V9.0 experiment.

DOES NOT call an ARC game. Apply only to a separate V9.0 feature branch
created from the final tested V8.9 branch; old versions stay untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

BRANCH = 'feat/feedback-explorer-v9-0-transition-learning'
PLANNER = Path('ARC-AGI-3-Agents/agents/templates/ls20_visual_planner.py')
EXPLORER = Path('ARC-AGI-3-Agents/agents/templates/feedback_explorer.py')
RUNTIME_TEST = Path('ARC-AGI-3-Agents/tests/test_feedback_runtime_v8_1.py')
TEST_SRC = Path('test_feedback_v9_0_transition_learning.py')
TEST_DST = Path('ARC-AGI-3-Agents/tests/test_feedback_v9_0_transition_learning.py')
EXPECTED_BLOBS = {
    PLANNER: '50cc8cf0229b663086edbae728f19fb5d32b545d',
    EXPLORER: '39ec9f858ce7212beb9846e44463bccdf1fea64c',
    RUNTIME_TEST: '36a4140a44586225bda4616d752de07d5f9a437b',
}


def git_blob_sha(blob: bytes) -> str:
    return hashlib.sha1(f'blob {len(blob)}\0'.encode('ascii') + blob).hexdigest()


def once(content: str, old: str, new: str, label: str) -> str:
    matches = content.count(old)
    if matches != 1:
        raise RuntimeError(f'SAFE ABORT: {label}: wanted one anchor, found {matches}')
    return content.replace(old, new, 1)


def generate() -> dict[Path, str]:
    branch = subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip()
    if branch != BRANCH:
        raise RuntimeError(f'SAFE ABORT: wrong branch: {branch!r}; expected {BRANCH!r}')
    originals: dict[Path, str] = {}
    for path, sha in EXPECTED_BLOBS.items():
        blob = path.read_bytes()
        current = git_blob_sha(blob)
        if current != sha:
            raise RuntimeError(f'SAFE ABORT: source blob drift: {path}: {current} != {sha}')
        originals[path] = blob.decode('utf-8')
    if not TEST_SRC.is_file() or TEST_DST.exists():
        raise RuntimeError('SAFE ABORT: test source is missing or target already exists')

    s = originals[PLANNER]
    s = once(s, 'DIRECTIONS = {\n', '''# V9.0: only observations from the confirmed 27 Oct V8.8/V8.9 tests.
# All four exits from the first hash yielded a loss of alignment;
# others have untried choices. We DO NOT infer hidden game rules.
V90_FAILED_EXIT_ACTIONS = {
    'e58c8a39094e9e8f': frozenset(('ACTION1', 'ACTION2', 'ACTION3', 'ACTION4')),
    '70c046c20de8d462': frozenset(('ACTION1', 'ACTION3', 'ACTION4')),
    '869a0f09dcb2c63c': frozenset(('ACTION1', 'ACTION3', 'ACTION4')),
}

DIRECTIONS = {
''', 'reference transition outcomes')

    s = once(s, "        self.level2_exit_guard_new_risks = 0\n", '''        self.level2_exit_guard_new_risks = 0
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
''', 'V9.0 model state')

    s = once(s, '    def _switch_cycle_step(self, grid, player, switch, rotations, candidates):\n', '''    def _v90_transition_avoid_actions(self, frame_fp, candidates):
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
            if before_pos == LEVEL_2_ROTATION_SWITCH and before_turns == 0:
                self._level2_risky_exits.add(key)
        self.level2_transition_samples += 1

    def _switch_cycle_step(self, grid, player, switch, rotations, candidates):
''', 'learned transition model')

    s = once(s, '    def propose(\n', '''    def propose(\n''', 'propose definition')
    s = once(s, '''    ) -> str | None:
        if (
            self._last_level is not None
''', '''    ) -> str | None:
        self.v90_request_reset = False
        if (
            self._last_level is not None
''', 'clear V9.0 reset signal at each proposal')

    s = once(s, '''        route = shortest_visible_path(
            grid,
            player,
            destination,
            candidates,
            guarded_blocked,
''', '''        # Learn from real immediate outcomes. An observed successor that
        # already has four failed switch exits is a trap to approach differently.
        # This is an EXACT visible-frame match, never a coordinate heuristic.
        if level == LS20_LEVEL_2_INDEX:
            frame_fp = hashlib.sha256(bytes(z for row in grid for z in row)).hexdigest()[:16]
            avoided = self._v90_transition_avoid_actions(frame_fp, candidates)
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
                return self._fallback('v90_all_switch_exits_observed_bad')

        route = shortest_visible_path(
            grid,
            player,
            destination,
            candidates,
            guarded_blocked,
''', 'first-step observed transition avoidance')

    s = once(s, '''    def record_frame_transition(self, before, after, action_name, *, step_index):
        """Record visible one-action switch exits without changing decisions.
''', '''    def record_frame_transition(self, before, after, action_name, *, step_index):
        """Record switch exits and learn bounded observed level-2 transitions.
''', 'transition hook docstring')
    s = once(s, '''        verified statement about how the game engine interprets a key press.
        Frame fingerprints are bounded hashes, never hidden game state.
        """
        try:
            if getattr(before, "levels_completed", None) != LS20_LEVEL_2_INDEX:
''', '''        verified statement about how the game engine interprets a key press.
        Frame fingerprints are bounded hashes, never hidden game state.
        """
        try:
            self._record_v90_transition(before, after, action_name)
        except Exception:
            # Never break an ARC action to collect telemetry.
            self.level2_transition_errors += 1
        try:
            if getattr(before, "levels_completed", None) != LS20_LEVEL_2_INDEX:
''', 'call run-local learning on every level-2 action')

    s = once(s, '''            "level2_exit_guard_new_risks": self.level2_exit_guard_new_risks,
            "last_reason": self.last_reason,
''', '''            "level2_exit_guard_new_risks": self.level2_exit_guard_new_risks,
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
            "last_reason": self.last_reason,
''', 'bounded aggregate V9.0 diagnostics')

    e = originals[EXPLORER]
    e = once(e, '    AGENT_VERSION = "8.9"', '    AGENT_VERSION = "9.0"', 'agent version')
    e = once(e, 'FeedbackExplorer V8.9 observed switch-exit guard experiment:',
             'FeedbackExplorer V9.0 observed transition learning and loop-avoidance experiment:', 'header')
    e = once(e, 'FeedbackExplorer V8.9: start or restart game',
             'FeedbackExplorer V9.0: start or restart game', 'reset reason')
    e = once(e, 'FeedbackExplorer V8.9: {action_name}',
             'FeedbackExplorer V9.0: {action_name}', 'action reason')
    e = once(e, '''        reverse_override = bool(
''', '''        # V9.0: do not silently fall back to another historically failed
        # exit when all four exits from an EXACT rendered switch frame failed.
        if level2_visual and getattr(self._ls20_visual_planner, 'v90_request_reset', False):
            self.policy.clear_pending()
            self._ls20_visual_planner.reset_pending()
            action = GameAction.RESET
            action.reasoning = 'FeedbackExplorer V9.0: observed switch exit dead-end; reset to explore alternative approach'
            return action

        reverse_override = bool(
''', 'honor guarded RESET')
    t = once(originals[RUNTIME_TEST], 'self.assertEqual(versions, ["8.9"])',
             'self.assertEqual(versions, ["9.0"])', 'runtime version compatibility test')
    return {PLANNER: s, EXPLORER: e, RUNTIME_TEST: t}


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    patch = generate()  # Every source hash and anchor checked BEFORE writing anything.
    if args.check:
        print('V9.0 branch, base V8.9 blobs, and all patch anchors verified. Nothing changed.')
        return
    for path, content in patch.items():
        path.write_text(content, encoding='utf-8')
    TEST_DST.write_bytes(TEST_SRC.read_bytes())
    print('Applied isolated V9.0 observed transition learning. Run regression tests before commit.')


if __name__ == '__main__':
    main()
