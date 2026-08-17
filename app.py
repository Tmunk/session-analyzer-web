"""Streamlit UI for the Session Analyzer.

This is the browser-facing replacement for the desktop app's customtkinter
windows. It only handles client management, file selection, and report
display/export - all the actual analysis lives in analyzer.py.
"""

from datetime import datetime

import streamlit as st

import analyzer

st.set_page_config(page_title="Session Analyzer", page_icon="\U0001F4CA", layout="wide")

if "clients" not in st.session_state:
    st.session_state.clients = []  # [{'name': str, 'files': {...}}]
if "date_range" not in st.session_state:
    st.session_state.date_range = (None, None)
if "reports" not in st.session_state:
    st.session_state.reports = None  # [(name, report_text)]

st.title("Session Analyzer")
st.caption(
    "Runs entirely in your browser (via stlite/Pyodide). Files you upload are "
    "processed locally and are never sent to a server - nothing leaves your machine."
)

# --- Add client ---
with st.expander("Add client", expanded=not st.session_state.clients):
    with st.form("add_client_form", clear_on_submit=True):
        name = st.text_input("Client name")
        sessions_files = st.file_uploader(
            "Sessions file(s) - select multiple to auto-combine",
            type="csv",
            accept_multiple_files=True,
        )
        hosts_file = st.file_uploader("Hosts file", type="csv")
        students_file = st.file_uploader("Students file", type="csv")
        kiosk_file = st.file_uploader("Kiosk file", type="csv")

        submitted = st.form_submit_button("Add client")
        if submitted:
            if not name.strip():
                st.error("Client name is required.")
            else:
                st.session_state.clients.append(
                    {
                        "name": name.strip(),
                        "files": {
                            "sessions": sessions_files or None,
                            "hosts": hosts_file,
                            "students": students_file,
                            "kiosk": kiosk_file,
                        },
                    }
                )
                st.session_state.reports = None
                st.rerun()

# --- Client list ---
st.subheader("Clients")
if not st.session_state.clients:
    st.info("No clients added yet.")
else:
    for i, client in enumerate(st.session_state.clients):
        cols = st.columns([6, 1])
        file_summary = ", ".join(
            f"{k}: {len(v) if isinstance(v, list) else 1}"
            for k, v in client["files"].items()
            if v
        ) or "no files selected"
        cols[0].markdown(f"**{client['name']}** &nbsp;·&nbsp; {file_summary}")
        if cols[1].button("Remove", key=f"remove_{i}"):
            st.session_state.clients.pop(i)
            st.session_state.reports = None
            st.rerun()

# --- Date range ---
st.subheader("Date range")
use_range = st.checkbox("Filter by date range", value=st.session_state.date_range != (None, None))
if use_range:
    date_cols = st.columns(2)
    start = date_cols[0].date_input("Start date")
    end = date_cols[1].date_input("End date")
    st.session_state.date_range = (datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.min.time()))
else:
    st.session_state.date_range = (None, None)

# --- Run analysis ---
st.divider()
if st.button("Run Analysis", type="primary"):
    if not st.session_state.clients:
        st.warning("Add at least one client first.")
    else:
        reports = []
        for client in st.session_state.clients:
            try:
                client_data = analyzer.process_client_files(client["files"], st.session_state.date_range)
                reports.append((client["name"], analyzer.generate_report(client["name"], client_data)))
            except Exception as e:
                st.error(f"Processing failed for {client['name']}: {e}")
                reports = None
                break
        st.session_state.reports = reports

# --- Results ---
if st.session_state.reports:
    st.subheader("Results")
    tabs = st.tabs([name for name, _ in st.session_state.reports])
    for tab, (name, report_text) in zip(tabs, st.session_state.reports):
        with tab:
            st.text(report_text)

    combined = "\n\n".join(text for _, text in st.session_state.reports)
    st.download_button(
        "Export all reports (.txt)",
        data=combined,
        file_name="session_analysis_report.txt",
        mime="text/plain",
    )
