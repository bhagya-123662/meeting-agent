"""
Streamlit UI for the Meeting Notes -> Action Items Agent.

This is a thin visual layer on top of agent.py — it reuses the exact same
call_gemini() / render_markdown() functions as the CLI, so what you see here
is exactly what `python agent.py` produces, just with a nicer front end.

Run with:
    streamlit run app.py
"""

import json
import os

import streamlit as st

from agent import call_gemini, render_markdown

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

st.set_page_config(page_title="Meeting Notes → Action Items", page_icon="📝", layout="wide")

st.title("📝 Meeting Notes → Action Items")
st.caption("Paste a meeting transcript and get a structured summary + assigned, dated action items.")

# --- Sidebar: config ---
with st.sidebar:
    st.header("Settings")
    default_key = os.getenv("GEMINI_API_KEY", "")
    api_key = st.text_input(
        "Gemini API Key",
        value=default_key,
        type="password",
        help="Loaded from .env if present. Get a free key at https://aistudio.google.com/apikey",
    )
    model = st.text_input("Model", value=os.getenv("GEMINI_MODEL", "gemini-3.7-flash"))
    st.markdown("---")
    st.markdown(
        "This UI calls the same `call_gemini()` function used by the CLI "
        "(`agent.py`) — no separate logic path."
    )

# --- Input area ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Provide a transcript")
    uploaded_file = st.file_uploader("Upload a .txt transcript", type=["txt"])
    sample_button = st.button("Or load the sample transcript")

    default_text = ""
    if uploaded_file is not None:
        default_text = uploaded_file.read().decode("utf-8")
    elif sample_button:
        sample_path = os.path.join("sample_data", "sample_transcript.txt")
        if os.path.exists(sample_path):
            with open(sample_path, "r", encoding="utf-8") as f:
                default_text = f.read()
        else:
            st.warning("sample_data/sample_transcript.txt not found.")

    transcript_text = st.text_area(
        "Transcript text",
        value=default_text,
        height=400,
        placeholder="Paste your meeting transcript here, or upload / load the sample above...",
    )

    run_button = st.button("Analyze Transcript", type="primary", use_container_width=True)

with col2:
    st.subheader("2. Results")

    if run_button:
        if not api_key:
            st.error("Please provide a Gemini API key in the sidebar (or set GEMINI_API_KEY in .env).")
        elif not transcript_text.strip():
            st.error("Please provide a transcript first.")
        else:
            with st.spinner(f"Calling {model}..."):
                try:
                    data = call_gemini(transcript_text, model=model, api_key=api_key)
                except Exception as e:
                    st.error(f"Error calling the model: {e}")
                    data = None

            if data:
                st.session_state["last_result"] = data

    data = st.session_state.get("last_result")

    if data:
        st.markdown(f"### {data.get('meeting_title', 'Untitled Meeting')}")
        meta_bits = []
        if data.get("meeting_date"):
            meta_bits.append(f"**Date:** {data['meeting_date']}")
        if data.get("attendees"):
            meta_bits.append(f"**Attendees:** {', '.join(data['attendees'])}")
        if meta_bits:
            st.markdown(" | ".join(meta_bits))

        st.markdown("**Summary**")
        st.write(data.get("summary", ""))

        if data.get("key_decisions"):
            st.markdown("**Key Decisions**")
            for d in data["key_decisions"]:
                st.markdown(f"- {d}")

        if data.get("discussion_points"):
            st.markdown("**Discussion Points**")
            for d in data["discussion_points"]:
                st.markdown(f"- {d}")

        st.markdown("**Action Items**")
        items = data.get("action_items", [])
        if items:
            st.table(
                [
                    {
                        "Task": item.get("task", ""),
                        "Owner": item.get("owner") or "Unassigned",
                        "Due Date": item.get("due_date") or "Not stated",
                        "Priority": item.get("priority", "medium"),
                        "Status": item.get("status", "open"),
                    }
                    for item in items
                ]
            )
        else:
            st.info("No action items extracted.")

        with st.expander("Raw JSON"):
            st.json(data)

        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button(
                "Download JSON",
                data=json.dumps(data, indent=2),
                file_name="meeting_output.json",
                mime="application/json",
            )
        with col_b:
            st.download_button(
                "Download Markdown",
                data=render_markdown(data),
                file_name="meeting_output.md",
                mime="text/markdown",
            )
    else:
        st.info("Results will appear here after you click **Analyze Transcript**.")
