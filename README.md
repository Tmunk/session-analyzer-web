# Session Analyzer (Web)

A browser-based tool for turning raw tutoring-session export CSVs (sessions, kiosk check-ins, host approvals, student signups) into monthly and annual per-client reports: total sessions, online vs. in-person split, unique hosts/students, average sessions per host/student, and kiosk-specific breakdowns.

Try it live: *(link added once deployed)* — click "Add client," upload the files from `sample_data/`, and click "Run Analysis."

## Why this exists

Built as a follow-up to a real internal tool from a B2B SaaS EdTech platform, where CS staff needed a recurring monthly/annual breakdown of tutoring session activity per institutional client, pulled from several different CSV exports that didn't share a common format. At a small company, engineering bandwidth was consistently spoken for by higher-priority product work, so building reporting tools for day-to-day CS/ops use often fell to whoever on the team could do it. This tool replaced hours of manual spreadsheet work each reporting cycle with one script run.

This is a sanitized rebuild: no real client names, student records, or company data are in this repo — only synthetic example CSVs (`sample_data/`) matching the real column structure.

## Why a web app instead of a desktop app

The original version of this tool was a Python desktop app (`customtkinter` GUI, `pandas` for analysis) — it still exists as a private, unlisted repo and isn't part of this rebuild. It worked well, but had two real drawbacks: it only ran on whatever OS it was built/packaged for, and distributing it to non-technical teammates meant sharing an executable rather than a link.

A typical web app would fix the OS problem but introduce a worse one for this use case: uploading files containing student names and IDs to a server, even briefly and even without persisting them, is a real trust boundary crossed for no good reason.

The fix here is **[stlite](https://github.com/whitphx/stlite)** — a WebAssembly build of Streamlit (via Pyodide) that runs an entire Python + pandas app inside the visitor's browser tab. There is no backend: `index.html` loads the Python runtime and mounts `app.py`/`analyzer.py` client-side, and every CSV a user uploads is parsed and analyzed locally in that tab. Nothing is ever transmitted anywhere. That preserves the actual property the original desktop app was built for (sensitive session/student data never leaves the user's machine) while dropping the OS dependency — anyone with a modern browser can use it, and hosting is just static files (GitHub Pages, Vercel, Netlify — no server to run or pay for).

## What it does, end to end

1. **Add one or more clients**, each with its own set of files: one or more session export CSVs (multiple files auto-combine, handling minor column-count mismatches between exports), plus optional hosts/students/kiosk CSVs.
2. **Optionally set a date range** to scope the analysis to a specific window; otherwise all dates are included.
3. **Run analysis** — for each client, session rows are grouped by month, host names are cleaned (stripping parenthetical tags like `(Volunteer)`), and students/hosts are deduplicated by ID where available (falling back to name matching if not).
4. **View a per-client report** (tabbed) with monthly breakdowns plus an annual summary, and a "formatted for data entry" block — a plain list of the same numbers in report order, meant for quickly pasting into an external tracking sheet without reformatting.
5. **Export all reports** as a single `.txt` file.

## Architecture differences from the desktop original (documented honestly, not hidden)

- **UI model**: the desktop app used separate `Toplevel` dialog windows for adding clients, setting dates, and viewing the report. Streamlit's reactive single-page model replaces those with an in-page form, an expandable "Add client" section, and tabs — a real UI paradigm shift, not a 1:1 port. `analyzer.py` (the actual data-processing logic) is unchanged in behavior from the original `DataProcessor` class; only the file-input mechanism changed, from file paths to in-memory uploaded bytes.
- **First-load cost**: stlite downloads a WebAssembly Python runtime and packages (pandas, chardet) on first visit, which takes several seconds longer than launching a native executable. It's cached by the browser after that.
- **No persistence**: closing or reloading the tab clears everything. This is intentional — nothing should be saved anywhere by default, given the privacy goal.
- **200MB per-file upload limit** (Streamlit's default): a non-issue for CSV session exports, but worth noting since the desktop app had no such cap.

## Sample data

`sample_data/` contains small, fully synthetic CSVs (fake names, emails, and IDs) matching the real column schema for each file type, so the app can be demoed end-to-end without any real data.

## Run it locally

No build step or install required — it's static files that fetch a CDN-hosted runtime at load time.

```bash
python -m http.server 8000
```

Then open `http://localhost:8000` in a browser. (Opening `index.html` directly via `file://` won't work — the page fetches `app.py`/`analyzer.py` at runtime, which requires a real HTTP server.)

## Built with

Python, pandas, chardet, [Streamlit](https://streamlit.io/), [stlite](https://github.com/whitphx/stlite) (Pyodide/WebAssembly — runs Python entirely client-side, no backend).
