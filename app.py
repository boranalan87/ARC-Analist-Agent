import streamlit as st
import numpy as np

st.set_page_config(
    page_title="ARC Analist Agent",
    page_icon="🧠",
    layout="wide"
)

st.title("🧠 ARC Analist Agent")
st.caption("Interactive ARC-AGI-3 development and testing dashboard")

with st.sidebar:
    st.header("Agent Controls")
    game = st.selectbox("Public game", [f"Game {i:02d}" for i in range(1, 26)])
    mode = st.selectbox("Mode", ["Explorer V0", "Manual Test"])
    if st.button("▶ Start agent", use_container_width=True):
        st.session_state["running"] = True
    if st.button("⏹ Stop", use_container_width=True):
        st.session_state["running"] = False
    if st.button("↻ Reset", use_container_width=True):
        st.session_state["steps"] = 0
        st.session_state["running"] = False

if "steps" not in st.session_state:
    st.session_state["steps"] = 0
if "running" not in st.session_state:
    st.session_state["running"] = False

col1, col2 = st.columns([1.35, 1])

with col1:
    st.subheader("ARC Game Grid")
    grid = np.zeros((16, 16), dtype=int)
    grid[2:5, 2:5] = 3
    grid[10:13, 10:13] = 8
    grid[6, 7] = 5

    palette = {
        0: "⬛", 1: "🟦", 2: "🟥", 3: "🟩",
        4: "🟨", 5: "🟪", 6: "🟧", 7: "⬜",
        8: "🟫", 9: "🔵", 10: "🔴", 11: "🟢",
        12: "🟡", 13: "🟣", 14: "🟠", 15: "⚪"
    }
    html = "<div style='font-family:monospace;line-height:1.05;font-size:18px'>"
    for row in grid:
        html += "".join(palette[int(v)] for v in row) + "<br>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

with col2:
    st.subheader("Agent Status")
    status = "RUNNING" if st.session_state["running"] else "IDLE"
    st.metric("Status", status)
    st.metric("Selected game", game)
    st.metric("Steps", st.session_state["steps"])
    st.metric("Completed levels", "0 / 0")

    st.markdown("#### Current reasoning")
    st.info(
        "V0 interface is live. The next version will connect this dashboard "
        "to the official ARC-AGI-3 environment and display real frames, actions, "
        "memory and benchmark results."
    )

st.divider()

c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("ACTION1 ↑", use_container_width=True):
        st.session_state["steps"] += 1
with c2:
    if st.button("ACTION2 ↓", use_container_width=True):
        st.session_state["steps"] += 1
with c3:
    if st.button("ACTION3 ←", use_container_width=True):
        st.session_state["steps"] += 1
with c4:
    if st.button("ACTION4 →", use_container_width=True):
        st.session_state["steps"] += 1

st.caption(
    "ARC Analist Agent V0 — Streamlit interface. "
    "Competition integration and real ARC engine connection will be added next."
)
