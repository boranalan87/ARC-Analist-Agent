"""V8.7 diagnostics-only, fail-closed patch of an exact V8.6 source tree.

Usage (at repository root):
    python upgrade_v87.py --check
    python upgrade_v87.py --apply

This instrumentation records visible alignment transitions but does not change
LS20 action selection, navigation, switch handling, or score calculations.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

PLANNER = Path('ARC-AGI-3-Agents/agents/templates/ls20_visual_planner.py')
EXPLORER = Path('ARC-AGI-3-Agents/agents/templates/feedback_explorer.py')
RUNTIME_TEST = Path('ARC-AGI-3-Agents/tests/test_feedback_runtime_v8_1.py')
V87_TEST_SOURCE = Path('test_feedback_v8_7_alignment_diagnostics.py')
V87_TEST_DEST = Path('ARC-AGI-3-Agents/tests/test_feedback_v8_7_alignment_diagnostics.py')

# Pin source blobs from verified V8.6 commit 3d4c82d.
# Abort for unknown source.
EXPECTED_BLOBS = {
    PLANNER: '46f3a6a6014036affce9be18b20116696f2c53fd',
    EXPLORER: '8365d6ffd33c46be4607bc16dceaa8b4bbd61e11',
    RUNTIME_TEST: 'cdb5a17789fa13bc6a3ef229f7fe15ce9ba110cd',
}


def git_blob_sha(content: bytes) -> str:
    header = f'blob {len(content)}\0'.encode('ascii')
    return hashlib.sha1(header + content).hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f'{label}: expected exactly one anchor, found {count}'
        )
    return source.replace(old, new, 1)


def plan() -> dict[Path, str]:
    contents = {}

    for path, expected in EXPECTED_BLOBS.items():
        data = path.read_bytes()
        actual = git_blob_sha(data)

        if actual != expected:
            raise RuntimeError(
                f'SAFE ABORT: {path} blob {actual} != V8.6 {expected}'
            )

        contents[path] = data.decode('utf-8')

    if not V87_TEST_SOURCE.is_file() or V87_TEST_DEST.exists():
        raise RuntimeError(
            'SAFE ABORT: V8.7 test source missing or test destination exists'
        )

    planner = contents[PLANNER]

    planner = replace_once(
        planner,
        '        self.level2_alignment_lost = 0\n'
        '        self._level2_was_aligned = False\n',
        '        self.level2_alignment_lost = 0\n'
        '        self._level2_was_aligned = False\n'
        '        # V8.7: bounded observational events; never used for actions.\n'
        '        self.level2_alignment_events = []\n'
        '        self._level2_observations = 0\n'
        '        self._level2_last_visible = None\n',
        'planner counters',
    )

    planner = replace_once(
        planner,
        '        self._level2_was_aligned = False\n\n'
        '    def _switch_cycle_step(',
        '        self._level2_was_aligned = False\n'
        '        self._level2_last_visible = None\n\n'
        '    def _switch_cycle_step(',
        'planner reset',
    )

    planner = replace_once(
        planner,
        '        if level == LS20_LEVEL_2_INDEX:\n'
        '            if self._level2_was_aligned and turns != 0:\n'
        '                self.level2_alignment_lost += 1\n'
        '            self._level2_was_aligned = turns == 0\n',
        '        if level == LS20_LEVEL_2_INDEX:\n'
        '            self._level2_observations += 1\n'
        '            previous = self._level2_last_visible\n'
        '            if self._level2_was_aligned and turns != 0:\n'
        '                self.level2_alignment_lost += 1\n'
        '                if len(self.level2_alignment_events) < 16:\n'
        '                    self.level2_alignment_events.append({\n'
        '                        "event_index": self.level2_alignment_lost,\n'
        '                        "level2_observation": self._level2_observations,\n'
        '                        "previous_player": list(previous["player"]) if previous else None,\n'
        '                        "current_player": list(player),\n'
        '                        "switch": list(LEVEL_2_ROTATION_SWITCH),\n'
        '                        "previous_rotations": previous["rotations"] if previous else 0,\n'
        '                        "current_rotations": turns,\n'
        '                        "previous_proposed_action": previous.get("proposed_action") if previous else None,\n'
        '                        "previous_selected_action": previous.get("selected_action") if previous else None,\n'
        '                        "previous_planner_reason": previous.get("planner_reason") if previous else None,\n'
        '                        "previous_on_switch": previous["player"] == LEVEL_2_ROTATION_SWITCH if previous else None,\n'
        '                        "current_on_switch": player == LEVEL_2_ROTATION_SWITCH,\n'
        '                        "source": "visible_frame",\n'
        '                    })\n'
        '            self._level2_was_aligned = turns == 0\n'
        '            self._level2_last_visible = {\n'
        '                "player": player,\n'
        '                "rotations": turns,\n'
        '                "planner_reason": None,\n'
        '                "proposed_action": None,\n'
        '                "selected_action": None,\n'
        '            }\n',
        'planner loss recording',
    )

    planner = replace_once(
        planner,
        '        """Count choices actually selected; never claim a level was solved."""\n'
        '        if proposal is None:\n',
        '        """Count choices actually selected; never claim a level was solved."""\n'
        '        if self._last_level == LS20_LEVEL_2_INDEX and self._level2_last_visible is not None:\n'
        '            self._level2_last_visible["proposed_action"] = proposal\n'
        '            self._level2_last_visible["selected_action"] = selected\n'
        '            self._level2_last_visible["planner_reason"] = self.last_reason\n'
        '        if proposal is None:\n',
        'planner action observation',
    )

    planner = replace_once(
        planner,
        '    def summary(self) -> dict[str, int | bool | str]:\n',
        '    def summary(self) -> dict[str, Any]:\n',
        'summary type',
    )

    planner = replace_once(
        planner,
        '            "level2_alignment_lost": self.level2_alignment_lost,\n',
        '            "level2_alignment_lost": self.level2_alignment_lost,\n'
        '            "level2_alignment_events": list(self.level2_alignment_events),\n',
        'summary event export',
    )

    explorer = contents[EXPLORER]

    explorer = replace_once(
        explorer,
        '    AGENT_VERSION = "8.6"',
        '    AGENT_VERSION = "8.7"',
        'agent class version',
    )

    # FIX: Match only the unique module-header line.
    # Other V8.6 occurrences remain available for their own replacements.
    explorer = replace_once(
        explorer,
        '\nFeedbackExplorer V8.6:\n',
        '\nFeedbackExplorer V8.7 diagnostics:\n',
        'agent header',
    )

    explorer = replace_once(
        explorer,
        'FeedbackExplorer V8.6: start or restart game',
        'FeedbackExplorer V8.7: start or restart game',
        'reset reasoning',
    )

    explorer = replace_once(
        explorer,
        'FeedbackExplorer V8.6: {action_name}',
        'FeedbackExplorer V8.7: {action_name}',
        'action reasoning',
    )

    runtime = contents[RUNTIME_TEST]

    runtime = replace_once(
        runtime,
        'self.assertEqual(versions, ["8.6"])',
        'self.assertEqual(versions, ["8.7"])',
        'runtime version assertion',
    )

    return {
        PLANNER: planner,
        EXPLORER: explorer,
        RUNTIME_TEST: runtime,
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')

    args = parser.parse_args()

    changes = plan()  # All checks precede ANY write.

    if args.check:
        print(
            'V8.7 source anchors and V8.6 blobs: VERIFIED; no files changed'
        )
        return

    for path, text in changes.items():
        path.write_text(text, encoding='utf-8')

    V87_TEST_DEST.write_bytes(V87_TEST_SOURCE.read_bytes())

    print(
        'V8.7 diagnostics-only patch applied locally; '
        'run all tests before commit'
    )


if __name__ == '__main__':
    main()
