"""Glue between the JS UI and analyzer.py, for the raw-Pyodide rebuild.

analyzer.py is intentionally untouched - it still expects file-like objects
with .getvalue() and returns pandas.Period-keyed dicts with sets inside,
neither of which cross the JS/Python boundary cleanly. This module wraps
raw bytes from JS file uploads into that expected shape, then flattens the
analysis results into a JSON string the UI can parse directly.
"""

import json
from datetime import datetime

import analyzer


class BytesFile:
    """Wraps raw bytes (from a JS File's arrayBuffer()) as an UploadedFile-alike."""

    def __init__(self, data):
        self._data = bytes(data) if data is not None else b""

    def getvalue(self):
        return self._data


def _parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d")


def _json_default(value):
    """Handles numpy scalar types (e.g. int64 from a pandas .sum()), which
    json.dumps doesn't know how to serialize on its own."""
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def run_client_analysis(
    name,
    sessions_bytes_list,
    hosts_bytes,
    students_bytes,
    kiosk_bytes,
    start_date,
    end_date,
):
    files = {
        "sessions": [BytesFile(b) for b in sessions_bytes_list] if sessions_bytes_list else None,
        "hosts": BytesFile(hosts_bytes) if hosts_bytes is not None else None,
        "students": BytesFile(students_bytes) if students_bytes is not None else None,
        "kiosk": BytesFile(kiosk_bytes) if kiosk_bytes is not None else None,
    }
    date_range = (_parse_date(start_date), _parse_date(end_date))

    client_data = analyzer.process_client_files(files, date_range)
    report_text = analyzer.generate_report(name, client_data)
    annual = analyzer.annual_summary(client_data)

    monthly = []
    for period in sorted(client_data.keys()):
        d = client_data[period]
        online_pct = round(d["online_sessions"] / d["total_sessions"] * 100) if d["total_sessions"] else 0
        monthly.append(
            {
                "period": period.strftime("%Y-%m"),
                "label": period.strftime("%B %Y"),
                "short_label": period.strftime("%b"),
                "total_sessions": d["total_sessions"],
                "online_sessions": d["online_sessions"],
                "online_pct": online_pct,
                "inperson_sessions": d["inperson_sessions"],
                "total_hosts": d["total_hosts"],
                "total_students": d["total_students"],
                "avg_sessions_host": d["avg_sessions_host"],
                "avg_sessions_student": d["avg_sessions_student"],
                "approved_hosts": d["approved_hosts"],
                "approved_students": d["approved_students"],
                "kiosk_sessions": d["kiosk_sessions"],
                "kiosk_host_count": d["kiosk_host_count"],
                "kiosk_student_count": d["kiosk_student_count"],
            }
        )

    annual_json = {}
    for year, y in annual.items():
        online_pct = round(y["online_sessions"] / y["total_sessions"] * 100) if y["total_sessions"] else 0
        annual_json[str(year)] = {
            "months_count": len(y["months"]),
            "unique_hosts": y["unique_hosts"],
            "unique_students": y["unique_students"],
            "total_sessions": y["total_sessions"],
            "online_sessions": y["online_sessions"],
            "inperson_sessions": y["inperson_sessions"],
            "online_pct": online_pct,
            "avg_sessions_per_host": y["avg_sessions_per_host"],
            "avg_sessions_per_student": y["avg_sessions_per_student"],
            "kiosk_sessions": y["kiosk_sessions"],
            "kiosk_hosts": y["kiosk_hosts"],
            "kiosk_students": y["kiosk_students"],
        }

    return json.dumps(
        {"monthly": monthly, "annual": annual_json, "report_text": report_text},
        default=_json_default,
    )
