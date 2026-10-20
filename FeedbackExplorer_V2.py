"""Explore actual FeedbackExplorer V2 /run results."""

import json
import streamlit as st

st.set_page_config(page_title="FeedbackExplorer V2", page_icon="📊", layout="wide")
st.title("📊 FeedbackExplorer V2")
st.caption("Only measured ARC-AGI-3 results; never simulated.")
uploaded = st.file_uploader("Upload a saved POST /run JSON response", type=["json"])
if uploaded is None:
    st.info("Execute feedbackexplorer in a configured ARC runtime and upload the returned JSON. No runtime token is needed on this page.")
    st.stop()
try:
    report = json.load(uploaded)
except (ValueError, UnicodeDecodeError):
    st.error("Invalid JSON file.")
    st.stop()
if not isinstance(report, dict):
    st.error("Expected an object containing a /run response.")
    st.stop()
if report.get("status") != "COMPLETED":
    st.warning("Execution did not complete; no measured results to show.")
    st.write("Run status:", str(report.get("status", "unknown")))
    st.stop()
if report.get("agent") != "feedbackexplorer":
    st.error("The run must use the feedbackexplorer agent.")
    st.stop()
diagnostics = report.get("diagnostics")
if not isinstance(diagnostics, dict) or not isinstance(diagnostics.get("v2"), dict):
    st.error("The runtime response does not contain FeedbackExplorer V2 telemetry.")
    st.stop()
v2 = diagnostics["v2"]
if v2.get("version") != 2:
    st.error("Unsupported telemetry version.")
    st.stop()

st.subheader("Run summary")
st.write("Game:", str(report.get("game", "unknown")))
a, b, c, d = st.columns(4)
a.metric("Recorded actions", diagnostics.get("recorded_actions", 0))
b.metric("Changed frames", diagnostics.get("changed_frames", 0))
c.metric("Levels gained", diagnostics.get("levels_gained", 0))
d.metric("Frame change rate", f"{100 * float(v2.get('frame_change_rate', 0)):.1f}%")

st.subheader("Action counts")
counts = diagnostics.get("actions_by_type", {})
if isinstance(counts, dict) and counts:
    st.bar_chart(
        {"action": list(counts), "count": [counts[action] for action in counts]},
        x="action", y="count",
    )
else:
    st.info("No actions recorded.")

st.subheader("Observed action effectiveness")
effectiveness = v2.get("action_effectiveness", {})
if isinstance(effectiveness, dict) and effectiveness:
    st.dataframe(
        [{"action": name, **values} for name, values in effectiveness.items()],
        hide_index=True, use_container_width=True,
    )
st.metric("Longest unchanged streak", v2.get("longest_unchanged_streak", 0))
st.caption("Progress = actual level gain. A changed frame alone is not a successful level.")

st.subheader("Recent action history")
events = v2.get("recent_actions", [])
if isinstance(events, list) and events:
    st.dataframe(list(reversed(events)), hide_index=True, use_container_width=True)
else:
    st.info("No measured transitions.")
if v2.get("history_truncated"):
    st.caption("History is capped; totals include all recorded actions.")

st.subheader("Policy memory (current run)")
memory = v2.get("policy_memory")
if isinstance(memory, dict):
    x, y, z = st.columns(3)
    x.metric("Known states", memory.get("known_states", 0))
    y.metric("State observations", memory.get("state_observations", 0))
    z.metric("Tried state/action pairs", memory.get("tried_state_action_pairs", 0))
    st.write("Action trials:", memory.get("action_trials", {}))
    st.write("Mean observed policy reward:", memory.get("mean_reward_by_action", {}))
    st.caption("Per-run policy table only; cross-run persistence is not implemented.")
else:
    st.info("Policy memory was not captured.")
