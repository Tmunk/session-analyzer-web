import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.5/full/pyodide.mjs";

const state = {
  clients: [], // {id, name, program, status, monthly, annual, reportText, error}
  search: "",
  screen: "dashboard", // 'dashboard' | 'report'
  selectedClientId: null,
  reportTab: "monthly", // 'monthly' | 'annual' | 'export'
};

let bridge = null;

// ---------- Pyodide boot ----------

async function boot() {
  const statusEl = document.getElementById("loading-status");
  statusEl.textContent = "Loading Python runtime…";
  const pyodide = await loadPyodide({
    indexURL: "https://cdn.jsdelivr.net/pyodide/v314.0.5/full/",
  });

  statusEl.textContent = "Installing pandas & chardet…";
  await pyodide.loadPackage("micropip");
  const micropip = pyodide.pyimport("micropip");
  await micropip.install(["pandas", "chardet"]);

  statusEl.textContent = "Starting analysis engine…";
  const [analyzerPy, bridgePy] = await Promise.all([
    fetch("analyzer.py").then((r) => r.text()),
    fetch("bridge.py").then((r) => r.text()),
  ]);
  pyodide.FS.writeFile("analyzer.py", analyzerPy);
  pyodide.FS.writeFile("bridge.py", bridgePy);
  bridge = pyodide.pyimport("bridge");

  document.getElementById("loading").hidden = true;
  document.getElementById("app").hidden = false;
}

// ---------- helpers ----------

function fileToBytes(file) {
  return file.arrayBuffer().then((buf) => new Uint8Array(buf));
}

async function readOptionalFile(inputEl) {
  const file = inputEl.files[0];
  return file ? await fileToBytes(file) : null;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---------- dashboard rendering ----------

function renderDashboard() {
  const grid = document.getElementById("client-grid");
  const empty = document.getElementById("dashboard-empty");
  const filtered = state.clients.filter((c) =>
    c.name.toLowerCase().includes(state.search.toLowerCase())
  );

  if (filtered.length === 0) {
    grid.hidden = true;
    empty.hidden = false;
    const noClientsAtAll = state.clients.length === 0;
    document.getElementById("empty-title").textContent = noClientsAtAll
      ? "Welcome"
      : "No clients match your search";
    document.getElementById("empty-body").textContent = noClientsAtAll
      ? "Add your first client and upload their session export to generate a report."
      : "Try a different name, or add a new client.";
    document.getElementById("empty-add-client").hidden = !noClientsAtAll;
  } else {
    grid.hidden = false;
    empty.hidden = true;
  }

  grid.innerHTML = filtered
    .map((c) => {
      const hasData = c.monthly && c.monthly.length > 0;
      const totalToDate = hasData
        ? c.monthly.reduce((sum, m) => sum + m.total_sessions, 0)
        : 0;
      const monthsLabel = hasData
        ? `${c.monthly.length} ${c.monthly.length === 1 ? "month" : "months"}`
        : "";
      const body = hasData
        ? `${totalToDate} sessions across ${monthsLabel} tracked.`
        : c.error
        ? `Analysis failed: ${escapeHtml(c.error)}`
        : "No analysis run yet - upload session exports to generate a report.";
      const lastMonthLabel = hasData
        ? `Last: ${c.monthly[c.monthly.length - 1].label}`
        : "Awaiting first upload";
      const tagClass = c.status === "new" ? "tag tag-accent" : "tag tag-outline";
      const tagLabel = c.status === "new" ? "New" : "Active";

      return `
        <div class="card elev-sm client-card" data-client-id="${c.id}">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span class="card-kicker">${escapeHtml(c.program)}</span>
            <span class="${tagClass}">${tagLabel}</span>
          </div>
          <div class="card-title">${escapeHtml(c.name)}</div>
          <p class="card-body">${body}</p>
          <div class="card-meta">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V10"></path><path d="M12 20V4"></path><path d="M20 20v-7"></path></svg>
            ${lastMonthLabel}
          </div>
        </div>
      `;
    })
    .join("");

  grid.querySelectorAll(".client-card").forEach((el) => {
    el.addEventListener("click", () => {
      state.selectedClientId = el.dataset.clientId;
      state.screen = "report";
      state.reportTab = "monthly";
      render();
    });
  });
}

// ---------- report rendering ----------

function renderReport() {
  const client = state.clients.find((c) => c.id === state.selectedClientId);
  if (!client) return;

  document.getElementById("report-client-name").textContent = client.name;
  document.getElementById("report-client-program").textContent = client.program;
  const tag = document.getElementById("report-client-tag");
  tag.textContent = client.status === "new" ? "New" : "Active";
  tag.className = client.status === "new" ? "tag tag-accent" : "tag tag-outline";

  document.querySelectorAll(".seg-opt[data-tab]").forEach((el) => {
    el.classList.toggle("active", el.dataset.tab === state.reportTab);
  });

  const hasData = client.monthly && client.monthly.length > 0;
  document.getElementById("report-no-data").hidden = hasData;
  document.getElementById("tab-monthly").hidden = !hasData || state.reportTab !== "monthly";
  document.getElementById("tab-annual").hidden = !hasData || state.reportTab !== "annual";
  document.getElementById("tab-export").hidden = !hasData || state.reportTab !== "export";

  if (!hasData) return;

  if (state.reportTab === "monthly") renderMonthlyTab(client);
  if (state.reportTab === "annual") renderAnnualTab(client);
  if (state.reportTab === "export") renderExportTab(client);
}

function renderMonthlyTab(client) {
  const maxTotal = Math.max(...client.monthly.map((m) => m.total_sessions)) || 1;
  const chart = document.getElementById("chart");
  chart.innerHTML = client.monthly
    .map((m) => {
      const pct = Math.max(6, Math.round((m.total_sessions / maxTotal) * 100));
      return `<div class="chart-bar" title="${m.total_sessions} sessions"><span class="value">${m.total_sessions}</span><div class="fill" style="height:${pct}%;"></div><span class="label">${escapeHtml(m.short_label)}</span></div>`;
    })
    .join("");

  const tbody = document.getElementById("monthly-table-body");
  tbody.innerHTML = client.monthly
    .map(
      (m) => `
        <tr>
          <td style="padding:5.6px;font-weight:500;">${escapeHtml(m.label)}</td>
          <td style="padding:5.6px;">${m.total_sessions}</td>
          <td style="padding:5.6px;">${m.online_sessions} <span class="text-muted">(${m.online_pct}%)</span></td>
          <td style="padding:5.6px;">${m.inperson_sessions}</td>
          <td style="padding:5.6px;">${m.total_hosts}</td>
          <td style="padding:5.6px;">${m.total_students}</td>
          <td style="padding:5.6px;">${m.avg_sessions_host}</td>
          <td style="padding:5.6px;">${m.avg_sessions_student}</td>
          <td style="padding:5.6px;">${m.approved_hosts}</td>
          <td style="padding:5.6px;">${m.approved_students}</td>
          <td style="padding:5.6px;">${m.kiosk_sessions}</td>
          <td style="padding:5.6px;">${m.kiosk_host_count}</td>
          <td style="padding:5.6px;">${m.kiosk_student_count}</td>
        </tr>
      `
    )
    .join("");
}

function statCard(kicker, value, body) {
  return `
    <div class="card elev-sm">
      <span class="card-kicker">${kicker}</span>
      <div class="stat-value">${value}</div>
      <p class="card-body" style="opacity:0.6;">${body}</p>
    </div>
  `;
}

function renderAnnualTab(client) {
  const years = Object.keys(client.annual).sort();
  const html = years
    .map((year) => {
      const y = client.annual[year];
      const cards = [
        statCard("Total sessions", y.total_sessions, `Year to date &middot; ${y.months_count} months`),
        statCard(
          "Online / in-person",
          `${y.online_pct}%`,
          `${y.online_sessions} online &middot; ${y.inperson_sessions} in-person`
        ),
        statCard("Unique hosts", y.unique_hosts, `${y.avg_sessions_per_host} sessions / host`),
        statCard("Unique students", y.unique_students, `${y.avg_sessions_per_student} sessions / student`),
        statCard(
          "Kiosk activity",
          y.kiosk_sessions,
          `${y.kiosk_hosts} hosts &middot; ${y.kiosk_students} students`
        ),
      ].join("");
      return `
        <h4>${year}</h4>
        <div class="stat-grid">${cards}</div>
        <p class="text-muted" style="font-size:12px;margin-top:8.4px;">Annual figures are year-to-date across the months analyzed above; unique host/student counts are deduplicated across the period.</p>
      `;
    })
    .join("<div class=\"hr\"></div>");
  document.getElementById("tab-annual").innerHTML = html;
}

function renderExportTab(client) {
  document.getElementById("export-text").textContent = client.reportText;
}

// ---------- render dispatch ----------

function render() {
  document.getElementById("view-dashboard").hidden = state.screen !== "dashboard";
  document.getElementById("view-report").hidden = state.screen !== "report";
  if (state.screen === "dashboard") renderDashboard();
  if (state.screen === "report") renderReport();
}

// ---------- add-client dialog ----------

function resetDialog() {
  document.getElementById("new-client-name").value = "";
  document.getElementById("new-client-program").value = "";
  document.getElementById("form-error").hidden = true;
  ["sessions", "hosts", "students", "kiosk"].forEach((key) => {
    document.getElementById(`${key}-file-input`).value = "";
    document.getElementById(`${key}-file-label`).textContent =
      key === "sessions" ? "Choose file(s)…" : "Choose file…";
  });
  const submitBtn = document.getElementById("submit-dialog");
  submitBtn.disabled = false;
  submitBtn.textContent = "Add client & analyze";
}

function openDialog() {
  resetDialog();
  document.getElementById("dialog-backdrop").hidden = false;
}

function closeDialog() {
  document.getElementById("dialog-backdrop").hidden = true;
}

async function submitDialog(event) {
  event.preventDefault();
  const name = document.getElementById("new-client-name").value.trim();
  const errorEl = document.getElementById("form-error");
  if (!name) {
    errorEl.textContent = "Enter a client name to continue";
    errorEl.hidden = false;
    return;
  }

  const submitBtn = document.getElementById("submit-dialog");
  submitBtn.disabled = true;
  submitBtn.textContent = "Analyzing…";

  const program = document.getElementById("new-client-program").value.trim() || "Tutoring program";
  const sessionsFiles = [...document.getElementById("sessions-file-input").files];
  const sessionsBytes = await Promise.all(sessionsFiles.map(fileToBytes));
  const hostsBytes = await readOptionalFile(document.getElementById("hosts-file-input"));
  const studentsBytes = await readOptionalFile(document.getElementById("students-file-input"));
  const kioskBytes = await readOptionalFile(document.getElementById("kiosk-file-input"));

  const client = {
    id: "c" + Date.now(),
    name,
    program,
    status: "new",
    monthly: [],
    annual: {},
    reportText: "",
    error: null,
  };

  try {
    const resultJson = bridge.run_client_analysis(
      name,
      sessionsBytes.length ? sessionsBytes : null,
      hostsBytes,
      studentsBytes,
      kioskBytes,
      null,
      null
    );
    const result = JSON.parse(resultJson);
    client.monthly = result.monthly;
    client.annual = result.annual;
    client.reportText = result.report_text;
    client.status = result.monthly.length > 0 ? "active" : "new";
  } catch (err) {
    client.error = String(err.message || err);
  }

  state.clients.unshift(client);
  closeDialog();
  render();
}

// ---------- export tab actions ----------

function copyExportText() {
  const client = state.clients.find((c) => c.id === state.selectedClientId);
  if (!client) return;
  navigator.clipboard?.writeText(client.reportText).catch(() => {});
  const label = document.getElementById("copy-label");
  label.textContent = "Copied";
  setTimeout(() => (label.textContent = "Copy"), 1500);
}

function downloadExportText() {
  const client = state.clients.find((c) => c.id === state.selectedClientId);
  if (!client) return;
  const blob = new Blob([client.reportText], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${client.name.replace(/\s+/g, "_")}_report.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------- wire up static event listeners ----------

function attachEventListeners() {
  document.getElementById("open-add-dialog").addEventListener("click", openDialog);
  document.getElementById("empty-add-client").addEventListener("click", openDialog);
  document.getElementById("close-dialog").addEventListener("click", closeDialog);
  document.getElementById("cancel-dialog").addEventListener("click", closeDialog);
  document.getElementById("dialog-backdrop").addEventListener("click", (e) => {
    if (e.target.id === "dialog-backdrop") closeDialog();
  });
  document.getElementById("add-client-form").addEventListener("submit", submitDialog);

  document.getElementById("search-input").addEventListener("input", (e) => {
    state.search = e.target.value;
    renderDashboard();
  });

  document.getElementById("back-to-dashboard").addEventListener("click", () => {
    state.screen = "dashboard";
    render();
  });

  document.querySelectorAll(".seg-opt[data-tab]").forEach((el) => {
    el.addEventListener("click", () => {
      state.reportTab = el.dataset.tab;
      render();
    });
  });

  ["sessions", "hosts", "students", "kiosk"].forEach((key) => {
    document.getElementById(`${key}-file-input`).addEventListener("change", (e) => {
      const files = [...e.target.files];
      const label = document.getElementById(`${key}-file-label`);
      if (files.length === 0) {
        label.textContent = key === "sessions" ? "Choose file(s)…" : "Choose file…";
      } else if (files.length === 1) {
        label.textContent = files[0].name;
      } else {
        label.textContent = `${files.length} files selected`;
      }
    });
  });

  document.getElementById("copy-export").addEventListener("click", copyExportText);
  document.getElementById("download-export").addEventListener("click", downloadExportText);
}

// ---------- go ----------

attachEventListeners();
render();
boot();
