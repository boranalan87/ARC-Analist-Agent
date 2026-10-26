#!/usr/bin/env python3
"""Install a narrow V8.6 LS20 level-2 alignment-safe routing change.

Input: the verified V8.5 source branch. Do not run on main/production.
The script is idempotent. It refuses unexpected upstream changes rather
than applying a potentially unsafe patch.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "ARC-AGI-3-Agents" / "agents" / "templates"
TESTS = ROOT / "ARC-AGI-3-Agents" / "tests"
PLANNER = TEMPLATES / "ls20_visual_planner.py"
AGENT = TEMPLATES / "feedback_explorer.py"
TEST_SOURCE = ROOT / "test_feedback_v8_6_aligned_route.py"
TEST_TARGET = TESTS / TEST_SOURCE.name

def once(text: str, old: str, new: str, desc: str) -> str:
    if new in text and old not in text:
        return text
    if text.count(old) != 1:
        raise RuntimeError(f"{desc}: expected exactly one V8.5 insertion point, found {text.count(old)}")
    return text.replace(old, new, 1)

def transform(planner: str, agent: str) -> tuple[str, str]:
    if 'AGENT_VERSION = "8.6"' not in agent and 'AGENT_VERSION = "8.5"' not in agent:
        raise RuntimeError("Expected FeedbackExplorer V8.5 or already-upgraded V8.6.")
    if "level2_aligned_safe_routes" not in planner:
        planner = once(
            planner,
            "    blocked: set[tuple[tuple[int, int], str]],\n) -> list[str] | None:",
            "    blocked: set[tuple[tuple[int, int], str]],\n"
            "    *,\n"
            "    avoid_positions: set[tuple[int, int]] | None = None,\n"
            ") -> list[str] | None:",
            "Path signature",
        )
        planner = once(
            planner,
            "            if next_pos in seen:\n                continue\n            if not _passable(grid, *next_pos):",
            "            if next_pos in seen:\n                continue\n"
            "            if avoid_positions is not None and next_pos in avoid_positions:\n"
            "                continue\n"
            "            if not _passable(grid, *next_pos):",
            "Path switch-avoidance rule",
        )
        planner = once(
            planner,
            "        self.level2_goal_routes_after_alignment = 0",
            "        self.level2_goal_routes_after_alignment = 0\n"
            "        # V8.6: planning measurements do not imply level completion.\n"
            "        self.level2_aligned_safe_routes = 0\n"
            "        self.level2_aligned_goal_route_blocked = 0\n"
            "        self.level2_alignment_lost = 0\n"
            "        self._level2_was_aligned = False",
            "Alignment counters",
        )
        planner = once(
            planner,
            "        self._level2_landmark_validated = False\n\n    def _switch_cycle_step(",
            "        self._level2_landmark_validated = False\n"
            "        self._level2_was_aligned = False\n\n"
            "    def _switch_cycle_step(",
            "Reset alignment-state tracking",
        )
        planner = once(
            planner,
            "        if turns is None:\n            return self._fallback(\"pose_not_visible\")\n\n        if turns:",
            "        if turns is None:\n"
            "            # Missing visual evidence must not count as alignment loss.\n"
            "            return self._fallback(\"pose_not_visible\")\n\n"
            "        if level == LS20_LEVEL_2_INDEX:\n"
            "            if self._level2_was_aligned and turns != 0:\n"
            "                self.level2_alignment_lost += 1\n"
            "            self._level2_was_aligned = turns == 0\n\n"
            "        if turns:",
            "Observed alignment tracking",
        )
        planner = once(
            planner,
            "        route = shortest_visible_path(\n"
            "            grid,\n"
            "            player,\n"
            "            destination,\n"
            "            candidates,\n"
            "            self._blocked,\n"
            "        )\n\n"
            "        if not route:\n"
            "            return self._fallback(\"no_visible_route\")\n\n"
            "        action = route[0]",
            "        # Never intentionally route BACK onto the visible rotation\n"
            "        # switch once the rendered current shape matches the goal.\n"
            "        # Leaving the switch (when already standing on it) is allowed.\n"
            "        aligned_level2 = level == LS20_LEVEL_2_INDEX and turns == 0\n"
            "        route = shortest_visible_path(\n"
            "            grid,\n"
            "            player,\n"
            "            destination,\n"
            "            candidates,\n"
            "            self._blocked,\n"
            "            avoid_positions={LEVEL_2_ROTATION_SWITCH} if aligned_level2 else None,\n"
            "        )\n\n"
            "        if not route:\n"
            "            if aligned_level2:\n"
            "                self.level2_aligned_goal_route_blocked += 1\n"
            "                return self._fallback('aligned_safe_goal_route_not_visible')\n"
            "            return self._fallback(\"no_visible_route\")\n\n"
            "        if aligned_level2:\n"
            "            self.level2_aligned_safe_routes += 1\n\n"
            "        action = route[0]",
            "Alignment-safe path choice",
        )
        planner = once(
            planner,
            '            "level2_goal_routes_after_alignment": self.level2_goal_routes_after_alignment,\n',
            '            "level2_goal_routes_after_alignment": self.level2_goal_routes_after_alignment,\n'
            '            "level2_aligned_safe_routes": self.level2_aligned_safe_routes,\n'
            '            "level2_aligned_goal_route_blocked": self.level2_aligned_goal_route_blocked,\n'
            '            "level2_alignment_lost": self.level2_alignment_lost,\n',
            "Summary counters",
        )

    if 'AGENT_VERSION = "8.5"' in agent:
        agent = agent.replace('AGENT_VERSION = "8.5"', 'AGENT_VERSION = "8.6"')
        agent = agent.replace("FeedbackExplorer V8.5:", "FeedbackExplorer V8.6:")
        agent = agent.replace("FeedbackExplorer V8.5:\n", "FeedbackExplorer V8.6:\n")
        if "FeedbackExplorer V8.5" in agent:
            agent = agent.replace("FeedbackExplorer V8.5", "FeedbackExplorer V8.6")
    return planner, agent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.check == args.apply:
        parser.error("Choose exactly one of --check or --apply")
    if not PLANNER.is_file() or not AGENT.is_file() or not TEST_SOURCE.is_file():
        raise RuntimeError("Expected V8.5 repo files plus root test_feedback_v8_6_aligned_route.py")
    old_planner, old_agent = PLANNER.read_text(), AGENT.read_text()
    new_planner, new_agent = transform(old_planner, old_agent)
    # Validate all safety landmarks before saving anything.
    for anchor in (
        "avoid_positions={LEVEL_2_ROTATION_SWITCH} if aligned_level2 else None",
        "level2_aligned_safe_routes",
        "level2_alignment_lost",
        "aligned_safe_goal_route_not_visible",
    ):
        if anchor not in new_planner:
            raise RuntimeError(f"V8.6 guard missing: {anchor}")
    if 'AGENT_VERSION = "8.6"' not in new_agent:
        raise RuntimeError("Agent version failed validation")
    if args.apply:
        PLANNER.write_text(new_planner)
        AGENT.write_text(new_agent)
        TESTS.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEST_SOURCE, TEST_TARGET)
        print("Applied V8.6 and installed tests. Only this branch was changed.")
    else:
        print("V8.6 patch compatible with the current source; no files changed.")

if __name__ == "__main__":
    main()
