#!/usr/bin/env python3
"""Upgrade an existing V8.3 checkout to V8.4 (opt-in visual reverse recovery).

Run from the ARC-Analist-Agent repository root:
    python upgrade_v84.py --check
    python upgrade_v84.py --apply

This script verifies ALL source anchors before modifying ANY file. Does not
publish, deploy, change secrets, or affect the Base44 app.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
AGENT_DIR = ROOT / "ARC-AGI-3-Agents" / "agents" / "templates"
TEST_DIR = ROOT / "ARC-AGI-3-Agents" / "tests"
WORKFLOW = ROOT / ".github" / "workflows" / "feedback-explorer-tests.yml"


def single(text: str, before: str, after: str, label: str) -> str:
    hits = text.count(before)
    if hits != 1:
        raise RuntimeError(f"{label}: beklenen V8.3 kod bloğu tekil değil (bulunan: {hits}). Dosyaya dokunulmadı.")
    return text.replace(before, after, 1)


def updates() -> dict[Path, str]:
    tests_source = Path(__file__).with_name("test_feedback_v8_4_visual_reverse.py")
    tests_target = TEST_DIR / tests_source.name
    if not tests_source.is_file():
        raise FileNotFoundError(f"Test paket dosyası eksik: {tests_source}")
    if tests_target.exists():
        raise RuntimeError(f"Test hedefi zaten mevcut: {tests_target}; hiçbir dosya değiştirilmedi")
    agent_path = AGENT_DIR / "feedback_explorer.py"
    policy_path = AGENT_DIR / "feedback_policy.py"
    planner_path = AGENT_DIR / "ls20_visual_planner.py"
    for p in (agent_path, policy_path, planner_path, WORKFLOW):
        if not p.is_file():
            raise FileNotFoundError(f"V8.3 kaynak dosyası bulunamadı: {p}")
    agent, policy, planner, workflow = (p.read_text(encoding="utf-8") for p in (agent_path, policy_path, planner_path, WORKFLOW))

    agent = single(agent, 'Keyboard frame-aware ARC-AGI-3 exploration agent.\n\nFeedbackExplorer V8.3:', 'Keyboard frame-aware ARC-AGI-3 exploration agent.\n\nFeedbackExplorer V8.4:', 'agent header')
    agent = single(agent, '    AGENT_VERSION = "8.3"', '    AGENT_VERSION = "8.4"', 'agent version')
    agent = single(agent, '"FeedbackExplorer V8.3: start or restart game"', '"FeedbackExplorer V8.4: start or restart game"', 'reset reasoning')
    agent = single(agent, 'f"FeedbackExplorer V8.3: {action_name}; "', 'f"FeedbackExplorer V8.4: {action_name}; "', 'action reasoning')

    before_choose = '''        proposed = None
        if self._ls20_visual_planner is not None:
            proposed = self._ls20_visual_planner.propose(
                latest_frame.frame,
                latest_frame.levels_completed,
                self.policy._candidate_actions(),
            )

        if proposed is not None:
            action_name = self.policy.choose(
                key,
                latest_frame.levels_completed,
                preferred_action=proposed,
            )
        else:
            action_name = self.policy.choose(
                key,
                latest_frame.levels_completed,
            )
'''
    after_choose = '''        # V8.4: only on LS20 level 2, allow a validated pixel-based route
        # to suggest a necessary reverse move. Other levels retain the V8.3
        # reverse guard, and all non-visual choices use the legacy policy.
        allowed_actions = self.policy._candidate_actions()
        level2_visual = (
            self._ls20_visual_planner is not None
            and latest_frame.levels_completed == 1
        )
        planner_candidates = (
            getattr(self.policy, "actions", tuple(allowed_actions))
            if level2_visual else allowed_actions
        )
        proposed = None
        if self._ls20_visual_planner is not None:
            proposed = self._ls20_visual_planner.propose(
                latest_frame.frame,
                latest_frame.levels_completed,
                planner_candidates,
            )

        reverse_override = bool(
            level2_visual
            and proposed is not None
            and proposed not in allowed_actions
            and proposed in planner_candidates
        )
        if proposed is not None:
            # Pass the new option only when actually required, maintaining
            # compatibility with existing policy/test adapter signatures.
            preference_options = (
                {"allow_preferred_reverse": True} if reverse_override else {}
            )
            action_name = self.policy.choose(
                key,
                latest_frame.levels_completed,
                preferred_action=proposed,
                **preference_options,
            )
        else:
            action_name = self.policy.choose(
                key,
                latest_frame.levels_completed,
            )

        if self._ls20_visual_planner is not None:
            report = getattr(self._ls20_visual_planner, "record_choice", None)
            if callable(report):
                report(proposed, action_name, reverse_override=reverse_override)
'''
    agent = single(agent, before_choose, after_choose, 'agent choose_action')

    before_policy = '''    def choose(
        self, key: str, levels_completed: int, *,
        preferred_action: str | None = None,
    ) -> str:
'''
    after_policy = '''    def choose(
        self, key: str, levels_completed: int, *,
        preferred_action: str | None = None,
        allow_preferred_reverse: bool = False,
    ) -> str:
'''
    policy = single(policy, before_policy, after_policy, 'policy method signature')
    before_pref = '''        if preferred_action in candidates:
            # V8: Prefer only an action inferred from a visible LS20 frame.
            action = preferred_action
        elif unseen:
'''
    after_pref = '''        if allow_preferred_reverse and preferred_action in self.actions:
            # V8.4: callers may *explicitly* honor a validated visual route
            # even if V5's immediate-reverse heuristic filtered this move.
            action = preferred_action
        elif preferred_action in candidates:
            # V8: Prefer only an action inferred from a visible LS20 frame.
            action = preferred_action
        elif unseen:
'''
    policy = single(policy, before_pref, after_pref, 'policy preferred action')

    init_anchor = '''        self.level2_proposals = 0
        self.level2_fallbacks = 0
'''
    init_new = '''        self.level2_proposals = 0
        self.level2_fallbacks = 0
        # Run-local counters; selecting a route is NOT proof of progress.
        self.preferred_actions_applied = 0
        self.preferred_actions_rejected = 0
        self.level2_reverse_filter_overrides = 0
'''
    planner = single(planner, init_anchor, init_new, 'planner counters')
    method_anchor = '''    def _fallback(self, reason: str) -> None:
'''
    method_new = '''    def record_choice(
        self,
        proposal: str | None,
        selected: str,
        *,
        reverse_override: bool = False,
    ) -> None:
        """Count choices actually selected; never claim a level was solved."""
        if proposal is None:
            return
        if selected == proposal:
            self.preferred_actions_applied += 1
            if reverse_override:
                self.level2_reverse_filter_overrides += 1
        else:
            self.preferred_actions_rejected += 1

    def _fallback(self, reason: str) -> None:
'''
    planner = single(planner, method_anchor, method_new, 'planner choice telemetry')
    summary_anchor = '''            "level2_fallbacks": self.level2_fallbacks,
            "last_reason": self.last_reason,
'''
    summary_new = '''            "level2_fallbacks": self.level2_fallbacks,
            "preferred_actions_applied": self.preferred_actions_applied,
            "preferred_actions_rejected": self.preferred_actions_rejected,
            "level2_reverse_filter_overrides": self.level2_reverse_filter_overrides,
            "last_reason": self.last_reason,
'''
    planner = single(planner, summary_anchor, summary_new, 'planner diagnostic summary')

    workflow = single(
        workflow,
        '      - feat/feedback-explorer-v2\n',
        '      - feat/feedback-explorer-v2\n      - feat/feedback-explorer-v8-4-visual-route-recovery\n',
        'GitHub Actions feature push trigger',
    )
    return {agent_path: agent, policy_path: policy, planner_path: planner, WORKFLOW: workflow}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Verify V8.3 anchors without modifying code")
    group.add_argument("--apply", action="store_true", help="Apply V8.4 to this checkout")
    args = parser.parse_args()
    changes = updates()  # validate ALL preconditions first
    for path, new_content in changes.items():
        compile(new_content, str(path), "exec") if path.suffix == ".py" else None
    if args.check:
        print("OK: V8.3 kaynak doğrulaması tamamlandı; hiçbir dosya değiştirilmedi.")
        return
    # Backups allow manual rollback without disturbing other source files.
    for path, new_content in changes.items():
        shutil.copy2(path, path.with_suffix(path.suffix + ".v83.bak"))
        path.write_text(new_content, encoding="utf-8")
        print(f"Güncellendi: {path.relative_to(ROOT)}")
    tests_source = Path(__file__).with_name("test_feedback_v8_4_visual_reverse.py")
    tests_target = TEST_DIR / tests_source.name
    shutil.copy2(tests_source, tests_target)
    print(f"Test eklendi: {tests_target.relative_to(ROOT)}")
    print("V8.4 yerel dosyalara uygulandı. GitHub'a gönderme/yayınlama YAPILMADI.")
    print('Testler: cd ARC-AGI-3-Agents && python -m unittest discover -s tests -p "test_feedback_*.py" -v')


if __name__ == "__main__":
    main()
