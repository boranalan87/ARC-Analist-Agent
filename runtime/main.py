import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


app = FastAPI(
    title="ARC Analist Agent Runtime",
    version="0.3.0",
)


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "ARC-AGI-3-Agents"

ARC_RUNTIME_TOKEN = os.getenv(
    "ARC_RUNTIME_TOKEN",
    "",
).strip()


if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))


class RunRequest(BaseModel):
    agent: str = Field(
        default="random",
        min_length=1,
    )
    game: str = Field(
        ...,
        min_length=1,
    )


@app.get("/")
def root():
    return {
        "service": "arc-analist-agent-runtime",
        "version": "0.3.0",
        "status": "ok",
    }


def load_agents():
    try:
        from agents import AVAILABLE_AGENTS, Swarm

        return AVAILABLE_AGENTS, Swarm

    except Exception as exc:
        raise RuntimeError(
            f"ARC agent import failed: {exc}"
        ) from exc


@app.get("/health")
def health():
    checks = {
        "agent_sources": (
            (AGENT_ROOT / "main.py").exists()
            and (AGENT_ROOT / "agents").is_dir()
        ),
        "runtime_token": bool(
            ARC_RUNTIME_TOKEN
        ),
        "arc_api_key": bool(
            os.getenv("ARC_API_KEY")
        ),
        "agent_import": False,
    }

    available_agents = []

    try:
        agents, _ = load_agents()

        available_agents = sorted(
            agents.keys()
        )

        checks["agent_import"] = bool(
            available_agents
        )

    except Exception:
        checks["agent_import"] = False

    ready = all(checks.values())

    return {
        "runtime_state": (
            "RUNTIME_READY"
            if ready
            else "RUNTIME_NOT_CONFIGURED"
        ),
        "checks": checks,
        "available_agents": available_agents,
    }


def authorize(
    authorization: Optional[str],
):
    if not ARC_RUNTIME_TOKEN:
        raise HTTPException(
            status_code=503,
            detail=(
                "ARC_RUNTIME_TOKEN "
                "is not configured"
            ),
        )

    expected_token = (
        f"Bearer {ARC_RUNTIME_TOKEN}"
    )

    if authorization != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )


@app.post("/run")
def run(
    req: RunRequest,
    authorization: Optional[str] = Header(
        default=None
    ),
):
    authorize(authorization)

    health_state = health()

    if (
        health_state["runtime_state"]
        != "RUNTIME_READY"
    ):
        return {
            "status": "NOT_EXECUTED",
            **health_state,
            "evidence": (
                "Runtime prerequisites "
                "are not configured."
            ),
        }

    available_agents, Swarm = load_agents()

    agent_name = req.agent.strip()
    game_id = req.game.strip()

    if agent_name not in available_agents:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Unknown ARC agent",
                "agent": agent_name,
                "available_agents": sorted(
                    available_agents.keys()
                ),
            },
        )

    if not game_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "A game_id is required."
            ),
        )

    if "," in game_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Exactly one ARC game_id "
                "is required for each run."
            ),
        )

    scheme = os.getenv(
        "SCHEME",
        "https",
    ).strip()

    host = os.getenv(
        "HOST",
        "three.arcprize.org",
    ).strip()

    port = os.getenv(
        "PORT",
        "443",
    ).strip()

    if not scheme or not host:
        raise HTTPException(
            status_code=503,
            detail=(
                "ARC endpoint configuration "
                "is incomplete."
            ),
        )

    if (
        (scheme == "https" and port == "443")
        or
        (scheme == "http" and port == "80")
        or
        not port
    ):
        root_url = f"{scheme}://{host}"

    else:
        root_url = (
            f"{scheme}://{host}:{port}"
        )

    try:
        swarm = Swarm(
            agent_name,
            root_url,
            [game_id],
            tags=[
                "arc-analist-agent",
                "runtime-validation",
            ],
        )

        scorecard = swarm.main()

        if scorecard is None:
            return {
                "status": "NOT_EXECUTED",
                "runtime_state": "RUNTIME_READY",
                "agent": agent_name,
                "game": game_id,
                "evidence": (
                    "ARC runner returned "
                    "no scorecard. "
                    "No execution metrics "
                    "were persisted."
                ),
            }

        scorecard_data = scorecard.model_dump(
            mode="json"
        )

        game_result = scorecard.get(
            game_id
        )

        return {
            "status": "COMPLETED",
            "runtime_state": "RUNTIME_READY",
            "agent": agent_name,
            "game": game_id,
            "scorecard": scorecard_data,
            "game_result": game_result,
            "evidence": (
                "Result returned directly "
                "by the ARC Swarm/Arcade "
                "scorecard."
            ),
        }

    except HTTPException:
        raise

    except Exception as exc:
        return {
            "status": "NOT_EXECUTED",
            "runtime_state": "RUNTIME_ERROR",
            "agent": agent_name,
            "game": game_id,
            "error_type": type(exc).__name__,
            "evidence": str(exc),
        }
