"""Streamlit UI for the Session Analyzer, styled with the Nocturne theme
(nocturne.css) adapted from the project's design handoff.

This is the browser-facing replacement for the desktop app's customtkinter
windows. It only handles client management, file selection, and report
display/export - all the actual analysis lives in analyzer.py.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import analyzer

st.set_page_config(page_title="Session Analyzer", page_icon="\U0001F4CA", layout="wide")

css_path = Path(__file__).parent / "nocturne.css"
st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

if "clients" not in st.session_state:
    st.session_state.clients = []  # [{'name': str, 'program': str, 'files': {...}}]
if "date_range" not in st.session_state:
    st.session_state.date_range = (None, None)
if "reports" not in st.session_state:
    st.session_state.reports = None  # [(name, client_data, report_text)]

st.markdown(
    """
    <div class="nocturne-brand">
      <div class="mark"><div class="dot"></div></div>
      <div class="wordmark">Session Analyzer</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(
    "Runs entirely in your browser (via stlite/Pyodide). Files you upload are "
    "processed locally and are never sent to a server - nothing leaves your machine."
)

# --- Add client ---
with st.expander("Add client", expanded=not st.session_state.clients):
    with st.form("add_client_form", clear_on_submit=True):
        name = st.text_input("Client name", placeholder="e.g. Willowbrook Learning Center")
        program = st.text_input("Program type (optional)", placeholder="e.g. Online + in-person tutoring")
        sessions_files = st.file_uploader(
            "Sessions file(s) - select multiple to auto-combine",
            type="csv",
            accept_multiple_files=True,
        )
        hosts_file = st.file_uploader("Hosts file (optional)", type="csv")
        students_file = st.file_uploader("Students file (optional)", type="csv")
        kiosk_file = st.file_uploader("Kiosk file (optional)", type="csv")

        submitted = st.form_submit_button("Add client", type="primary")
        if submitted:
            if not name.strip():
                st.error("Enter a client name to continue.")
            else:
                st.session_state.clients.append(
                    {
                        "name": name.strip(),
                        "program": program.strip() or "Tutoring program",
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
        with st.container(border=True):
            cols = st.columns([6, 1])
            file_labels = {"sessions": "Sessions", "hosts": "Hosts", "students": "Students", "kiosk": "Kiosk"}
            file_summary = " &middot; ".join(
                f"{file_labels[k]}: {len(v) if isinstance(v, list) else 1} file"
                + ("s" if (len(v) if isinstance(v, list) else 1) != 1 else "")
                for k, v in client["files"].items()
                if v
            ) or "No files selected"
            cols[0].markdown(
                f'<div class="nocturne-client-card">'
                f'<span class="nocturne-card-kicker">{client["program"]}</span>'
                f'<span class="nocturne-card-title">{client["name"]}</span>'
                f'<p class="nocturne-card-body">{file_summary}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if cols[1].button("Remove", key=f"remove_{i}"):
                st.session_state.clients.pop(i)
                st.session_state.reports = None
                st.rerun()

# --- Date range ---
with st.container(border=True):
    st.subheader("Date range")
    use_range = st.checkbox("Filter by date range", value=st.session_state.date_range != (None, None))
    if use_range:
        date_cols = st.columns(2)
        start = date_cols[0].date_input("Start date")
        end = date_cols[1].date_input("End date")
        st.session_state.date_range = (
            datetime.combine(start, datetime.min.time()),
            datetime.combine(end, datetime.min.time()),
        )
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
                report_text = analyzer.generate_report(client["name"], client_data)
                reports.append((client["name"], client_data, report_text))
            except Exception as e:
                st.error(f"Processing failed for {client['name']}: {e}")
                reports = None
                break
        st.session_state.reports = reports


def render_monthly_tab(client_data: dict) -> None:
    if not client_data:
        st.info("No sessions analyzed yet for this date range.")
        return

    periods = sorted(client_data.keys())
    max_total = max(client_data[p]["total_sessions"] for p in periods) or 1

    def bar_html(period) -> str:
        total = client_data[period]["total_sessions"]
        pct = max(6, round(total / max_total * 100))
        return (
            f'<div class="nocturne-chart-bar" title="{total} sessions">'
            f'<span class="value">{total}</span>'
            f'<div class="fill" style="height:{pct}%;"></div>'
            f'<span class="label">{period.strftime("%b")}</span>'
            f'</div>'
        )

    bars = "".join(bar_html(p) for p in periods)
    with st.container(border=True):
        st.markdown('<span class="nocturne-card-kicker">Sessions per month</span>', unsafe_allow_html=True)
        st.markdown(f'<div class="nocturne-chart">{bars}</div>', unsafe_allow_html=True)

    rows = []
    for p in periods:
        d = client_data[p]
        online_pct = round(d["online_sessions"] / d["total_sessions"] * 100) if d["total_sessions"] else 0
        rows.append(
            {
                "Month": p.strftime("%B %Y"),
                "Total": d["total_sessions"],
                "Online": f"{d['online_sessions']} ({online_pct}%)",
                "In-person": d["inperson_sessions"],
                "Hosts": d["total_hosts"],
                "Students": d["total_students"],
                "Avg / host": d["avg_sessions_host"],
                "Avg / student": d["avg_sessions_student"],
                "Approved hosts": d["approved_hosts"],
                "Approved students": d["approved_students"],
                "Kiosk sessions": d["kiosk_sessions"],
                "Kiosk hosts": d["kiosk_host_count"],
                "Kiosk students": d["kiosk_student_count"],
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_annual_tab(client_data: dict) -> None:
    if not client_data:
        st.info("No sessions analyzed yet for this date range.")
        return

    def stat_card(kicker: str, value, body: str) -> str:
        return (
            f'<div class="nocturne-client-card" '
            f'style="background:var(--color-surface);padding:8.4px;border-radius:8px;">'
            f'<span class="nocturne-card-kicker">{kicker}</span>'
            f'<div class="nocturne-stat-value">{value}</div>'
            f'<p class="nocturne-card-body" style="opacity:0.6;">{body}</p>'
            f'</div>'
        )

    summary = analyzer.annual_summary(client_data)
    for year in sorted(summary.keys()):
        y = summary[year]
        online_pct = round(y["online_sessions"] / y["total_sessions"] * 100) if y["total_sessions"] else 0
        cards = "".join(
            [
                stat_card("Total sessions", y["total_sessions"], f"Year to date &middot; {len(y['months'])} months"),
                stat_card("Online / in-person", f"{online_pct}%", f"{y['online_sessions']} online &middot; {y['inperson_sessions']} in-person"),
                stat_card("Unique hosts", y["unique_hosts"], f"{y['avg_sessions_per_host']} sessions / host"),
                stat_card("Unique students", y["unique_students"], f"{y['avg_sessions_per_student']} sessions / student"),
                stat_card("Kiosk activity", y["kiosk_sessions"], f"{y['kiosk_hosts']} hosts &middot; {y['kiosk_students']} students"),
            ]
        )
        st.markdown(f"#### {year}")
        st.markdown(f'<div class="nocturne-stat-grid">{cards}</div>', unsafe_allow_html=True)
        st.caption("Annual figures are year-to-date across the months analyzed above; unique host/student counts are deduplicated across the period.")


def render_export_tab(client_name: str, report_text: str) -> None:
    if not report_text.strip():
        st.info("No sessions analyzed yet for this date range.")
        return
    st.caption("Plain list, in report order - paste straight into an external tracking sheet. Use the copy icon in the top-right of the box below.")
    st.code(report_text, language=None)
    st.download_button(
        "Export .txt",
        data=report_text,
        file_name=f"{client_name.replace(' ', '_')}_report.txt",
        mime="text/plain",
        type="primary",
    )


# --- Results ---
if st.session_state.reports:
    st.subheader("Results")
    tabs = st.tabs([name for name, _, _ in st.session_state.reports])
    for tab, (name, client_data, report_text) in zip(tabs, st.session_state.reports):
        with tab:
            monthly_tab, annual_tab, export_tab = st.tabs(["Monthly", "Annual", "Data-entry export"])
            with monthly_tab:
                render_monthly_tab(client_data)
            with annual_tab:
                render_annual_tab(client_data)
            with export_tab:
                render_export_tab(name, report_text)

    combined = "\n\n".join(text for _, _, text in st.session_state.reports)
    st.divider()
    st.download_button(
        "Export all reports (.txt)",
        data=combined,
        file_name="session_analysis_report.txt",
        mime="text/plain",
    )
