"""LS20 offline replay proof of the first three levels.

Does not submit Kaggle competition entries, access live ARC servers, or alter
an existing FeedbackExplorer agent. Designed for the repository's own venv.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path

# Actions are mapped only at runtime to keep this module importable without ARC.
ROUTES = {
    "level1": "UUUULLLDURRRUUU",
    "level2": "UR" + "U"*5 + "RRDR" + "D"*6 + "DLL" + "RRUDU" + "U"*6 + "LU" + "L"*5 + "DL" + "D"*5,
    "level3": "U"*8 + "LD" + "D"*4 + "LLRR" + "D"*3 + "U"*6 + "R" + "DD" + "R"*4 + "U"*3 + "L" + "RLR" + "D"*8,
}
# Level 1 ending leaves completed level result; next level must be loaded by L.
LEVEL2_ENTRY = "L"
EXPECTED_LEVELS = 3


def load_environment(game_dir: Path):
    path = game_dir / "ls20.py"
    if not path.is_file():
        raise FileNotFoundError(f"ls20.py not found: {path}")
    spec = importlib.util.spec_from_file_location("ls20_local", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load LS20 module")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def replay(game_dir: Path, extended: str = "") -> dict:
    from arcengine import ActionInput, GameAction
    mod = load_environment(game_dir)
    action_map = {
        "U": GameAction.ACTION1,
        "D": GameAction.ACTION2,
        "L": GameAction.ACTION3,
        "R": GameAction.ACTION4,
    }
    if any(c not in action_map for c in extended):
        raise ValueError("Extended path must contain only U,D,L,R")
    game = mod.Ls20()
    result = game.perform_action(ActionInput(id=GameAction.RESET))
    checkpoints = []
    for level_number in (1, 2, 3):
        if level_number == 2:
            result = game.perform_action(ActionInput(id=action_map[LEVEL2_ENTRY]))
        actions = ROUTES[f"level{level_number}"]
        for letter in actions:
            result = game.perform_action(ActionInput(id=action_map[letter]))
            if result.levels_completed >= level_number:
                break
        passed = int(result.levels_completed) >= level_number
        checkpoints.append({"level": level_number, "passed": passed,
                            "levels_completed": int(result.levels_completed),
                            "route": actions})
        if not passed:
            return {"status": "FAILED", "checkpoints": checkpoints,
                    "levels_completed": int(result.levels_completed),
                    "source": "LOCAL_LS20_REPLAY", "competition_verified": False}
    for letter in extended:
        result = game.perform_action(ActionInput(id=action_map[letter]))
    return {
        "status": "PASSED" if result.levels_completed >= EXPECTED_LEVELS else "FAILED",
        "checkpoints": checkpoints,
        "levels_completed": int(result.levels_completed),
        "position": [int(game.gudziatsk.x), int(game.gudziatsk.y)],
        "shape": int(game.fwckfzsyc),
        "color": int(game.hiaauhahz),
        "extended_actions": extended,
        "source": "LOCAL_LS20_REPLAY",
        "competition_verified": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", type=Path, default=Path("environment_files/ls20/9607627b"))
    parser.add_argument("--extended", default="", help="Optional verified Level 4 path (UDLR)")
    parser.add_argument("--output", type=Path, default=Path("artifacts/ls20-local-replay.json"))
    args = parser.parse_args()
    os.environ.setdefault("MPLBACKEND", "Agg")
    proof = replay(args.game_dir.resolve(), args.extended)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(proof, ensure_ascii=False))
    return 0 if proof["status"] == "PASSED" else 1

if __name__ == "__main__":
    raise SystemExit(main())
