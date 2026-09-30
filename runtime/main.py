import os
import sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="ARC Analist Agent Runtime", version="0.2.0")

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "ARC-AGI-3-Agents"
TOKEN = os.getenv("ARC_RUNTIME_TOKEN", "")

if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))


class RunRequest(BaseModel):
    agent: str = "random"
    game: str
