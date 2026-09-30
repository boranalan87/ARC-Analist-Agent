@app.get("/")
def root():
    return {
        "service": "arc-analist-agent-runtime",
        "status": "ok",
    }


def _load_agents():
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
        "arc_api_key": bool(os.getenv("ARC_API_KEY")),
        "runtime_token": bool(TOKEN),
    }

    try:
        available_agents, _ = _load_agents()
        checks["agent_import"] = bool(available_agents)
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
    }


def authorize(authorization: str | None):
    if not TOKEN:
        raise HTTPException(
            status_code=503,
            detail="ARC_RUNTIME_TOKEN is not configured",
        )

    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )


@app.post("/run")
def run(
    req: RunRequest,
    authorization: str | None = Header(default=None),
):
    authorize(authorization)

    health_state = health()

    if health_state["runtime_state"] != "RUNTIME_READY":
        return {
            "status": "NOT_EXECUTED",
            **health_state,
            "evidence": "Runtime prerequisites are not configured.",
        }

    available_agents, Swarm = _load_agents()

    if req.agent not in available_agents:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Unknown ARC agent",
                "agent": req.agent,
                "available_agents": sorted(
                    available_agents.keys()
                ),
            },
        )

    game = req.game.strip()

    if not game or "," in game:
        raise HTTPException(
            status_code=400,
            detail=(
                "Exactly one ARC game_id is required "
                "for each validation run."
            ),
        )

    try:
        scheme = os.getenv("SCHEME", "https")
        host = os.getenv("HOST", "three.arcprize.org")
        port = os.getenv("PORT", "443")

        if (
            (scheme == "https" and port == "443")
            or (scheme == "http" and port == "80")
        ):
            root_url = f"{scheme}://{host}"
        else:
            root_url = f"{scheme}://{host}:{port}"

        swarm = Swarm(
            req.agent,
            root_url,
            [game],
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
                "agent": req.agent,
                "game": game,
                "evidence": (
                    "ARC runner returned no scorecard; "
                    "no metrics were persisted."
                ),
            }

        scorecard_data = scorecard.model_dump(mode="json")
        game_result = scorecard.get(game)

        return {
            "status": "COMPLETED",
            "runtime_state": "RUNTIME_READY",
            "agent": req.agent,
            "game": game,
            "scorecard": scorecard_data,
            "game_result": game_result,
            "evidence": (
                "Result returned directly by the "
                "ARC Swarm/Arcade scorecard."
            ),
        }

    except HTTPException:
        raise

    except Exception as exc:
        return {
            "status": "NOT_EXECUTED",
            "runtime_state": "RUNTIME_ERROR",
            "agent": req.agent,
            "game": game,
            "error_type": type(exc).__name__,
            "evidence": str(exc),
        }
