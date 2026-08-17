"""Core data-processing logic for the Session Analyzer, ported from the desktop
(customtkinter) version. Framework-agnostic on purpose: no Streamlit imports here,
so this module works the same whether it's called from a browser UI or a test script.
"""

import io
import re

import chardet
import pandas as pd


def detect_encoding(file_bytes: bytes) -> str:
    if not file_bytes:
        return "utf-8"
    result = chardet.detect(file_bytes[:10000])
    encoding = result.get("encoding")
    if not encoding or encoding == "ascii":
        return "ISO-8859-1"
    return encoding


def clean_host_name(host_name) -> str:
    if pd.isna(host_name):
        return ""
    cleaned = re.sub(r"\s?\(.*\)", "", str(host_name)).strip()
    return cleaned


def sanitize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [col.replace("+AC0-", "-").replace("�", "").strip() for col in df.columns]
    return df


def parse_dates(df: pd.DataFrame, date_column: str) -> pd.DataFrame:
    if date_column in df.columns:
        df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
    return df


def filter_by_date_range(df: pd.DataFrame, date_column: str, date_range):
    start, end = date_range
    if not start or not end:
        return df
    return df[(df[date_column] >= start) & (df[date_column] <= end)]


def _fix_row_length(expected_cols):
    def fix(row):
        if len(row) > expected_cols:
            row[expected_cols - 1] = row[expected_cols - 1] + "," + ",".join(row[expected_cols:])
            return row[:expected_cols]
        if len(row) < expected_cols:
            return row + [""] * (expected_cols - len(row))
        return row

    return fix


def read_csv_upload(uploaded_file) -> pd.DataFrame:
    """Read a single uploaded CSV (any object exposing .getvalue() -> bytes) into a
    DataFrame, tolerating ragged rows the same way the original combiner logic did.
    """
    raw_bytes = uploaded_file.getvalue()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors="replace")
    header = text.splitlines()[0] if text else ""
    expected_cols = len(header.split(",")) if header else 0
    return pd.read_csv(
        io.StringIO(text),
        engine="python",
        on_bad_lines=_fix_row_length(expected_cols) if expected_cols else "warn",
    )


def read_sessions_data(session_files) -> pd.DataFrame:
    """Combine one or more uploaded session CSVs into a single DataFrame (auto-combine)."""
    if not session_files:
        return pd.DataFrame()
    frames = []
    for f in session_files:
        try:
            frames.append(read_csv_upload(f))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def empty_metrics() -> dict:
    return {
        "total_sessions": 0,
        "online_sessions": 0,
        "inperson_sessions": 0,
        "hosts": set(),
        "students": set(),
        "sessions_with_hosts": 0,
        "approved_hosts": 0,
        "approved_students": 0,
        "kiosk_sessions": 0,
        "kiosk_hosts": set(),
        "kiosk_students": set(),
        "total_hosts": 0,
        "total_students": 0,
        "kiosk_host_count": 0,
        "kiosk_student_count": 0,
        "avg_sessions_host": 0,
        "avg_sessions_student": 0,
    }


def process_client_files(files: dict, date_range) -> dict:
    """files: {'sessions': [uploads] | None, 'hosts'|'students'|'kiosk': upload | None}
    Returns {pandas.Period: metrics_dict}, one entry per month covered by the data.
    """
    all_data: dict = {}

    if files.get("sessions"):
        sessions_df = read_sessions_data(files["sessions"])
        if not sessions_df.empty:
            sessions_df = parse_dates(sessions_df, "Start Date Time")
            sessions_df = filter_by_date_range(sessions_df, "Start Date Time", date_range)
            sessions_df["month_year"] = sessions_df["Start Date Time"].dt.to_period("M")
            sessions_df["Host"] = sessions_df["Host"].apply(clean_host_name)
            if "Student Number" in sessions_df.columns:
                sessions_df["Student Number"] = sessions_df["Student Number"].astype(str).str.strip()

            for period, group in sessions_df.groupby("month_year"):
                data = all_data.setdefault(period, empty_metrics())
                valid_hosts = group[group["Host"] != ""]

                data["total_sessions"] += len(group)
                data["online_sessions"] += group[group["Type"] == "Online"].shape[0]
                data["inperson_sessions"] += group[group["Type"] == "In-person"].shape[0]
                data["hosts"].update(valid_hosts["Host"].unique())
                data["sessions_with_hosts"] += len(valid_hosts)

                if "Student Number" in group.columns:
                    data["students"].update(group["Student Number"].dropna().unique())
                else:
                    data["students"].update(group["Student"].astype(str).str.strip().str.lower().unique())

    if files.get("kiosk"):
        kiosk_df = read_csv_upload(files["kiosk"])
        kiosk_df = sanitize_columns(kiosk_df)

        required_cols = {"Checked-In Date Time", "Assigned Host", "Student"}
        missing = required_cols - set(kiosk_df.columns)
        if missing:
            raise KeyError(f"Missing required kiosk columns: {missing}")

        kiosk_df = parse_dates(kiosk_df, "Checked-In Date Time")
        kiosk_df = filter_by_date_range(kiosk_df, "Checked-In Date Time", date_range)

        if not kiosk_df.empty:
            kiosk_df["month_year"] = kiosk_df["Checked-In Date Time"].dt.to_period("M")
            kiosk_df["Assigned Host"] = kiosk_df["Assigned Host"].apply(clean_host_name)

            if "Student Number" in kiosk_df.columns:
                kiosk_df["Student Identifier"] = kiosk_df["Student Number"].astype(str).str.strip()
            else:
                kiosk_df["Student Identifier"] = kiosk_df["Student"].astype(str).str.strip().str.lower()

            for period, group in kiosk_df.groupby("month_year"):
                data = all_data.setdefault(period, empty_metrics())
                valid_kiosk = group[group["Assigned Host"] != ""]

                data["total_sessions"] += len(group)
                data["inperson_sessions"] += len(group)
                data["kiosk_sessions"] += len(group)
                data["sessions_with_hosts"] += len(valid_kiosk)
                data["hosts"].update(valid_kiosk["Assigned Host"].unique())
                data["kiosk_hosts"].update(valid_kiosk["Assigned Host"].unique())
                data["students"].update(group["Student Identifier"].dropna().unique())
                data["kiosk_students"].update(group["Student Identifier"].dropna().unique())

    if files.get("hosts"):
        hosts_df = read_csv_upload(files["hosts"])
        hosts_df = parse_dates(hosts_df, "Approved At")
        hosts_df = filter_by_date_range(hosts_df, "Approved At", date_range)
        if not hosts_df.empty:
            hosts_df["month_year"] = hosts_df["Approved At"].dt.to_period("M")
            for period, group in hosts_df.groupby("month_year"):
                data = all_data.setdefault(period, empty_metrics())
                data["approved_hosts"] += group["First Name"].dropna().str.strip().ne("").sum()

    if files.get("students"):
        students_df = read_csv_upload(files["students"])
        students_df = parse_dates(students_df, "Created At")
        students_df = filter_by_date_range(students_df, "Created At", date_range)
        if not students_df.empty:
            students_df["month_year"] = students_df["Created At"].dt.to_period("M")
            for period, group in students_df.groupby("month_year"):
                data = all_data.setdefault(period, empty_metrics())
                data["approved_students"] += group["Email"].dropna().str.strip().ne("").sum()

    for period_data in all_data.values():
        period_data["total_hosts"] = len(period_data["hosts"])
        period_data["total_students"] = len(period_data["students"])
        period_data["kiosk_host_count"] = len(period_data["kiosk_hosts"])
        period_data["kiosk_student_count"] = len(period_data["kiosk_students"])
        period_data["avg_sessions_host"] = (
            round(period_data["sessions_with_hosts"] / period_data["total_hosts"]) if period_data["total_hosts"] else 0
        )
        period_data["avg_sessions_student"] = (
            round(period_data["total_sessions"] / period_data["total_students"]) if period_data["total_students"] else 0
        )

    return all_data


def annual_summary(client_data: dict) -> dict:
    """Roll monthly metrics up into one aggregate per year.

    Used by both generate_report() (the plain-text export) and the UI's
    Annual view, so the two never drift out of sync.
    """
    years: dict = {}
    for period in sorted(client_data.keys()):
        years.setdefault(period.year, []).append(period)

    summary = {}
    for year, periods in years.items():
        year_hosts = set()
        year_students = set()
        totals = {
            "total_sessions": 0,
            "online_sessions": 0,
            "inperson_sessions": 0,
            "sessions_with_hosts": 0,
            "approved_hosts": 0,
            "approved_students": 0,
            "kiosk_sessions": 0,
            "kiosk_hosts": set(),
            "kiosk_students": set(),
        }
        for period in periods:
            data = client_data[period]
            year_hosts.update(data["hosts"])
            year_students.update(data["students"])
            for key in (
                "total_sessions",
                "online_sessions",
                "inperson_sessions",
                "sessions_with_hosts",
                "approved_hosts",
                "approved_students",
                "kiosk_sessions",
            ):
                totals[key] += data[key]
            totals["kiosk_hosts"].update(data["kiosk_hosts"])
            totals["kiosk_students"].update(data["kiosk_students"])

        summary[year] = {
            "months": periods,
            "unique_hosts": len(year_hosts),
            "unique_students": len(year_students),
            "total_sessions": totals["total_sessions"],
            "online_sessions": totals["online_sessions"],
            "inperson_sessions": totals["inperson_sessions"],
            "sessions_with_hosts": totals["sessions_with_hosts"],
            "avg_sessions_per_host": (
                round(totals["sessions_with_hosts"] / len(year_hosts)) if year_hosts else 0
            ),
            "avg_sessions_per_student": (
                round(totals["total_sessions"] / len(year_students)) if year_students else 0
            ),
            "approved_hosts": totals["approved_hosts"],
            "approved_students": totals["approved_students"],
            "kiosk_sessions": totals["kiosk_sessions"],
            "kiosk_hosts": len(totals["kiosk_hosts"]),
            "kiosk_students": len(totals["kiosk_students"]),
        }
    return summary


def generate_report(client_name: str, client_data: dict) -> str:
    report = [f"Client: {client_name}\n"]
    sorted_months = sorted(client_data.keys())
    years: dict = {}
    for period in sorted_months:
        years.setdefault(period.year, []).append(period)
    annual = annual_summary(client_data)

    for year in sorted(years.keys()):
        for period in years[year]:
            data = client_data[period]
            report.append(f"\n--- {period.strftime('%B %Y')} ---")
            report.append(f"Total Sessions: {data['total_sessions']}")
            report.append(f"Online Sessions: {data['online_sessions']}")
            report.append(f"In-person Sessions: {data['inperson_sessions']}")
            report.append(f"Total Hosts: {data['total_hosts']}")
            report.append(f"Avg Sessions/Host: {data['avg_sessions_host']}")
            report.append(f"Total Students: {data['total_students']}")
            report.append(f"Avg Sessions/Student: {data['avg_sessions_student']}")
            report.append(f"Approved Hosts: {data['approved_hosts']}")
            report.append(f"Approved Students: {data['approved_students']}")
            report.append(f"Kiosk Sessions: {data['kiosk_sessions']}")
            report.append(f"Kiosk Hosts: {data['kiosk_host_count']}")
            report.append(f"Kiosk Students: {data['kiosk_student_count']}")

            report.append("\n--- Formatted for data entry ---")
            report.append(f"{data['total_sessions']}")
            report.append(f"{data['online_sessions']}")
            report.append(f"{data['inperson_sessions']}")
            report.append(f"{data['total_hosts']}")
            report.append(f"{data['avg_sessions_host']}")
            report.append(f"{data['total_students']}")
            report.append(f"{data['avg_sessions_student']}")
            report.append(f"{data['approved_hosts']}")
            report.append(f"{data['approved_students']}")

        year_summary = annual[year]
        report.append(f"\n--- Annual Summary {year} ---")
        report.append(f"Unique Hosts: {year_summary['unique_hosts']}")
        report.append(f"Unique Students: {year_summary['unique_students']}")
        report.append(f"Total Valid Sessions: {year_summary['sessions_with_hosts']}")
        if year_summary["unique_hosts"]:
            report.append(f"Avg Annual Sessions/Host: {year_summary['avg_sessions_per_host']}")
        else:
            report.append("Avg Annual Sessions/Host: N/A")

    return "\n".join(report)
