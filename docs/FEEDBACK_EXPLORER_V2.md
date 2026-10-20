# FeedbackExplorer V2

V2 adds bounded action-level diagnostics while preserving all existing V1 fields
under the runtime response's `diagnostics` object. New fields are grouped in
`diagnostics.v2`.

## Results

- Outcomes: progressed (observed level gain), changed (new visible screen
  without progress), unchanged. These categories are mutually exclusive.
- Per-action trials, level-progress rate, frame-change rate, and longest
  unchanged streak.
- Last 100 events: action, outcome, level delta, optional terminal state and
  hashed destination screen ID. No raw frames are retained.
- Policy memory: state/action visits and average observed heuristic reward.
  This memory is for **the current run**, not persisted across runs.
- Aggregate counts remain full-run values, even if event history is truncated.

## Run

An ARC environment and runtime token must be configured. Then:

```bash
curl -sS -X POST "$RUNTIME_URL/run" \
  -H "Authorization: Bearer $ARC_RUNTIME_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent":"feedbackexplorer","game":"YOUR_REAL_GAME_ID"}' \
  > feedback-run.json
```

Only `status: COMPLETED` plus `diagnostics.v2` represents a measured V2 run.
`NOT_EXECUTED` and errors must not be shown as success. Never share your token.

Start the local dashboard with:

```bash
streamlit run app.py
```

Open the **FeedbackExplorer V2** page and upload `feedback-run.json`.
This page uses only uploaded real-run JSON; it does not execute an agent.
Vercel currently deploys FastAPI, not the Streamlit dashboard.

## Tests

```bash
cd ARC-AGI-3-Agents
python -m unittest discover -s tests -p "test_feedback_*.py" -v
```

GitHub Actions runs this suite on V2 branch pushes and PRs to `main`.

## Limitations

No cross-run memory store, replay of raw video frames, or automatic benchmark
comparison is implemented. Policy reward is heuristic and is not proof of
solving a level.
