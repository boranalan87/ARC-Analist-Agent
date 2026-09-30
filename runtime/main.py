import os
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="ARC Analist Agent Runtime", version="0.1.0")
ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "ARC-AGI-3-Agents"
TOKEN = os.getenv("ARC_RUNTIME_TOKEN", "")

class RunRequest(BaseModel):
    agent: str = "random"
    game: str | None = None

@app.get("/")
def root():
    return {"service":"arc-analist-agent-runtime","status":"ok"}

@app.get("/health")
def health():
    checks = {
        "agent_sources": (AGENT_ROOT / "main.py").exists() and (AGENT_ROOT / "agents").is_dir(),
        "arc_api_key": bool(os.getenv("ARC_API_KEY")),
        "runtime_token": bool(TOKEN),
    }
    ready = all(checks.values())
    return {"runtime_state":"RUNTIME_READY" if ready else "RUNTIME_NOT_CONFIGURED", "checks":checks}

def authorize(authorization: str | None):
    if not TOKEN:
        raise HTTPException(status_code=503, detail="ARC_RUNTIME_TOKEN is not configured")
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.post("/run")
def run(req: RunRequest, authorization: str | None = Header(default=None)):
    authorize(authorization)
    health_state = health()
    if health_state["runtime_state"] != "RUNTIME_READY":
        return {"status":"NOT_EXECUTED", **health_state, "evidence":"Runtime prerequisites are not configured."}
    # Deliberately no fabricated ARC result. The official runner adapter is wired in the next validation step.
    return {
        "status":"NOT_EXECUTED",
        "runtime_state":"RUNTIME_READY",
        "agent":req.agent,
        "game":req.game,
        "evidence":"Runtime is ready; official ARC runner result adapter must be validated before execution metrics are persisted."
    }
