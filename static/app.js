const COLORS = {
  cell_manufactured: "#176b87",
  cell_sold: "#5d9f8d",
  module_manufactured: "#bd7a2a",
  module_sold: "#c0524b",
};

const state = {
  summary: null,
  metricSeries: [],
  manufacturers: [],
  visibleMetrics: new Set(),
  manufacturerById: new Map(),
  manufacturerSortKey: "agency_name",
  manufacturerSortDirection: 1,
};

const STATIC_ENDPOINTS = {
  "/api/summary": "summary.json",
  "/api/metrics": "metrics.json",
  "/api/manufacturers": "manufacturers.json",
};

const $ = (selector) => document.querySelector(selector);
const numberFormat = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value) {
  return value === null || value === undefined || Number.isNaN(Number(value))
    ? "—"
    : numberFormat.format(Number(value));
}

function formatGrowth(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `${Number(value) >= 0 ? "+" : ""}${(Number(value) * 100).toFixed(2)}%`;
}

function formatDelta(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `${Number(value) >= 0 ? "+" : "−"}${formatNumber(Math.abs(Number(value)))} MW`;
}

function renderKpis() {
  const container = $("#kpi-grid");
  const metrics = state.summary?.metrics || [];
  if (!metrics.length) {
    container.innerHTML = '<div class="loading-card">No successful scrape yet. Run <code>python run.py --no-email</code> first.</div>';
    return;
  }
  container.innerHTML = metrics.map((metric) => {
    const change = metric.delta === null || metric.delta === undefined
      ? "flat"
      : metric.period_changed
        ? "new"
        : Number(metric.delta) > 0
          ? "up"
          : Number(metric.delta) < 0
            ? "down"
            : "flat";
    const changeText = metric.delta === null || metric.delta === undefined
      ? "No baseline"
      : `${formatDelta(metric.delta)} · ${formatGrowth(metric.growth)}`;
    return `<article class="kpi-card">
      <div class="kpi-label">${escapeHtml(metric.label)}</div>
      <div class="kpi-change ${change}">${escapeHtml(changeText)}</div>
      <div class="kpi-value">${formatNumber(metric.current)}<small>MW</small></div>
      <div class="kpi-period">Latest: ${escapeHtml(metric.current_period || "No data")} · ${escapeHtml(metric.comparison || "")}</div>
    </article>`;
  }).join("");
}

function renderMetricControls() {
  const controls = $("#metric-controls");
  if (!state.visibleMetrics.size) state.metricSeries.forEach((series) => state.visibleMetrics.add(series.key));
  controls.innerHTML = state.metricSeries.map((series) => {
    const active = state.visibleMetrics.has(series.key);
    return `<button class="series-toggle ${active ? "active" : ""}" data-metric="${escapeHtml(series.key)}" type="button">
      <span class="series-swatch" style="background:${COLORS[series.key] || "#176b87"}"></span>${escapeHtml(series.label)}
    </button>`;
  }).join("");
  controls.querySelectorAll("[data-metric]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.metric;
      if (state.visibleMetrics.has(key) && state.visibleMetrics.size === 1) return;
      if (state.visibleMetrics.has(key)) state.visibleMetrics.delete(key);
      else state.visibleMetrics.add(key);
      renderMetricControls();
      renderChart();
    });
  });
}

function renderChart() {
  const svg = $("#trend-chart");
  const tooltip = $("#chart-tooltip");
  const selected = state.metricSeries.filter((series) => state.visibleMetrics.has(series.key));
  const periodSet = new Set(selected.flatMap((series) => series.points.map((point) => point.period)));
  const periods = [...periodSet].sort();
  if (!selected.length || !periods.length) {
    svg.innerHTML = '<text x="500" y="190" text-anchor="middle" class="chart-axis-label">No history loaded yet</text>';
    return;
  }
  const width = 1000;
  const height = 380;
  const margin = { top: 22, right: 24, bottom: 44, left: 64 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const maxValue = Math.max(...selected.flatMap((series) => series.points.map((point) => Number(point.value))), 1);
  const xPosition = (index) => margin.left + (periods.length === 1 ? plotWidth / 2 : (index / (periods.length - 1)) * plotWidth);
  const yPosition = (value) => margin.top + plotHeight - (Number(value) / maxValue) * plotHeight;
  const periodIndex = new Map(periods.map((period, index) => [period, index]));
  const grid = [];
  for (let i = 0; i <= 4; i += 1) {
    const value = (maxValue / 4) * i;
    const y = yPosition(value);
    grid.push(`<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" class="chart-gridline"/>`);
    grid.push(`<text x="${margin.left - 10}" y="${y + 4}" text-anchor="end" class="chart-axis-label">${formatNumber(value)}</text>`);
  }
  const labelEvery = Math.max(1, Math.ceil(periods.length / 8));
  periods.forEach((period, index) => {
    if (index % labelEvery !== 0 && index !== periods.length - 1) return;
    const x = xPosition(index);
    grid.push(`<text x="${x}" y="${height - 15}" text-anchor="middle" class="chart-axis-label">${escapeHtml(period)}</text>`);
  });

  const lines = [];
  selected.forEach((series) => {
    const pointMap = new Map(series.points.map((point) => [point.period, point]));
    const points = series.points.map((point) => {
      const index = periodIndex.get(point.period);
      return { ...point, x: xPosition(index), y: yPosition(point.value) };
    });
    if (!points.length) return;
    lines.push(`<polyline points="${points.map((point) => `${point.x},${point.y}`).join(" ")}" class="chart-line" stroke="${COLORS[series.key] || "#176b87"}"/>`);
    points.forEach((point) => {
      const text = `${series.label} · ${point.period}: ${formatNumber(point.value)} MW`;
      lines.push(`<circle cx="${point.x}" cy="${point.y}" r="4.5" class="chart-point" fill="${COLORS[series.key] || "#176b87"}" data-tooltip="${escapeHtml(text)}"/>`);
    });
    // Keep this map construction explicit: it makes gaps in future portal data harmless.
    void pointMap;
  });
  svg.innerHTML = `${grid.join("")}${lines.join("")}`;
  svg.querySelectorAll(".chart-point").forEach((point) => {
    point.addEventListener("mouseenter", (event) => {
      tooltip.hidden = false;
      tooltip.textContent = point.dataset.tooltip || "";
      const wrap = $(".chart-wrap").getBoundingClientRect();
      const target = event.target.getBoundingClientRect();
      tooltip.style.left = `${Math.min(target.left - wrap.left + 8, wrap.width - 175)}px`;
      tooltip.style.top = `${Math.max(8, target.top - wrap.top - 48)}px`;
    });
    point.addEventListener("mouseleave", () => { tooltip.hidden = true; });
  });

  $("#chart-legend").innerHTML = selected.map((series) => `<span class="legend-item"><span class="series-swatch" style="background:${COLORS[series.key] || "#176b87"}"></span>${escapeHtml(series.label)}</span>`).join("");
}

function renderChanges() {
  const container = $("#change-summary");
  const metrics = state.summary?.metrics || [];
  container.innerHTML = metrics.map((metric) => {
    const cls = metric.delta === null || metric.delta === undefined
      ? "neutral"
      : Number(metric.delta) > 0 ? "positive" : Number(metric.delta) < 0 ? "negative" : "neutral";
    return `<div class="change-row">
      <div><div class="change-row-label">${escapeHtml(metric.label)}</div>
      <div class="change-row-detail">${escapeHtml(metric.comparison || "No comparison")} · ${escapeHtml(metric.current_period || "No data")}</div></div>
      <div class="change-value ${cls}">${escapeHtml(formatDelta(metric.delta))}<br><span>${escapeHtml(formatGrowth(metric.growth))}</span></div>
    </div>`;
  }).join("") || '<p class="muted">No metric observations yet.</p>';
  const run = state.summary?.latest_run;
  $("#run-meta").textContent = run
    ? `Run #${run.id} · ${run.full_history ? "historical backfill" : "current-year refresh"} · ${run.finished_at || run.started_at}`
    : "";
}

function renderCategories() {
  const counts = state.summary?.manufacturer_counts || {};
  const total = Object.values(counts).reduce((sum, value) => sum + Number(value), 0) || 1;
  $("#category-summary").innerHTML = Object.entries(counts).map(([name, value]) => `<div class="category-row">
    <div class="category-name">${escapeHtml(name)}</div><div class="category-value">${formatNumber(value)}</div>
    <div class="category-bar"><span style="width:${Math.max(2, (Number(value) / total) * 100)}%"></span></div>
  </div>`).join("") || '<p class="muted">No manufacturer list yet.</p>';
}

function populateManufacturerFilters() {
  const category = $("#manufacturer-category");
  const stateSelect = $("#manufacturer-state");
  const oldCategory = category.value;
  const oldState = stateSelect.value;
  const categories = [...new Set(state.manufacturers.map((item) => item.company_type).filter(Boolean))].sort();
  const states = [...new Set(state.manufacturers.map((item) => item.state).filter(Boolean))].sort();
  category.innerHTML = '<option value="">All categories</option>' + categories.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
  stateSelect.innerHTML = '<option value="">All states</option>' + states.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
  category.value = categories.includes(oldCategory) ? oldCategory : "";
  stateSelect.value = states.includes(oldState) ? oldState : "";
}

function renderManufacturers() {
  const search = $("#manufacturer-search").value.trim().toLowerCase();
  const category = $("#manufacturer-category").value;
  const selectedState = $("#manufacturer-state").value;
  const items = state.manufacturers.filter((item) => {
    if (category && item.company_type !== category) return false;
    if (selectedState && item.state !== selectedState) return false;
    if (search && !JSON.stringify(item.raw).toLowerCase().includes(search)) return false;
    return true;
  }).sort((a, b) => {
    const key = state.manufacturerSortKey;
    if (key === "agency_name" || key === "State" || key === "CompanyType") {
      const aValue = key === "agency_name" ? a.agency_name : key === "State" ? a.state : a.company_type;
      const bValue = key === "agency_name" ? b.agency_name : key === "State" ? b.state : b.company_type;
      return String(aValue || "").localeCompare(String(bValue || "")) * state.manufacturerSortDirection;
    }
    const aNumber = Number(a.raw?.[key]);
    const bNumber = Number(b.raw?.[key]);
    const aMissing = !Number.isFinite(aNumber);
    const bMissing = !Number.isFinite(bNumber);
    if (aMissing !== bMissing) return aMissing ? 1 : -1;
    return (aNumber - bNumber) * state.manufacturerSortDirection;
  });
  $("#manufacturer-count").textContent = `${state.manufacturers.length} records · refreshed ${state.manufacturerObservedAt || "—"}`;
  $("#manufacturer-visible-count").textContent = `Showing ${items.length} of ${state.manufacturers.length}`;
  const tbody = $("#manufacturer-table");
  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-cell">No records match these filters.</td></tr>';
    return;
  }
  tbody.innerHTML = items.map((item) => {
    const raw = item.raw || {};
    return `<tr>
      <td class="company-cell">${escapeHtml(item.agency_name || raw.AgencyName || "Unknown")}</td>
      <td>${escapeHtml(item.state || raw.State)}</td>
      <td>${escapeHtml(item.company_type || raw.CompanyType)}</td>
      <td class="email-cell">${escapeHtml(raw.Email || "")}</td>
      <td class="numeric">${formatNumber(raw.CellDCR)}</td>
      <td class="numeric">${formatNumber(raw.ModuleDCR)}</td>
      <td><button class="details-button" type="button" data-details-id="${escapeHtml(item.agency_id)}">View all</button></td>
    </tr>`;
  }).join("");
  tbody.querySelectorAll("[data-details-id]").forEach((button) => {
    button.addEventListener("click", () => openDetails(state.manufacturerById.get(button.dataset.detailsId)));
  });
  document.querySelectorAll(".sort-button").forEach((button) => {
    const active = button.dataset.sortKey === state.manufacturerSortKey;
    button.classList.toggle("active", active);
    const indicator = button.querySelector(".sort-indicator");
    if (indicator) indicator.textContent = active ? (state.manufacturerSortDirection === 1 ? "↑" : "↓") : "↕";
  });
}

function ensureDialog() {
  let dialog = $("#details-dialog");
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = "details-dialog";
  dialog.innerHTML = '<div class="modal-head"><h2 id="details-title">Manufacturer details</h2><button class="modal-close" type="button" aria-label="Close">×</button></div><dl class="details-grid" id="details-grid"></dl>';
  document.body.appendChild(dialog);
  dialog.querySelector(".modal-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  return dialog;
}

function openDetails(item) {
  if (!item) return;
  const dialog = ensureDialog();
  const raw = item.raw || {};
  $("#details-title").textContent = item.agency_name || raw.AgencyName || "Manufacturer details";
  $("#details-grid").innerHTML = Object.entries(raw).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value === null || value === undefined ? "—" : typeof value === "object" ? JSON.stringify(value) : value)}</dd></div>`).join("");
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "open");
}

async function fetchJson(path) {
  const staticMode = window.DCR_STATIC_DATA === true;
  const target = staticMode ? `data/${STATIC_ENDPOINTS[path]}` : path;
  const response = await fetch(target, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

async function loadDashboard() {
  const status = $("#last-updated");
  status.innerHTML = '<span class="status-dot"></span>Refreshing…';
  status.classList.remove("error");
  try {
    const [summary, metricData, manufacturerData] = await Promise.all([
      fetchJson("/api/summary"), fetchJson("/api/metrics"), fetchJson("/api/manufacturers"),
    ]);
    state.summary = summary.ready ? summary : null;
    state.metricSeries = metricData.series || [];
    state.manufacturers = manufacturerData.items || [];
    state.manufacturerObservedAt = manufacturerData.observed_at;
    state.manufacturerById = new Map(state.manufacturers.map((item) => [item.agency_id, item]));
    const runDate = summary.latest_run?.finished_at || summary.latest_run?.started_at;
    status.innerHTML = `<span class="status-dot"></span>${runDate ? `Updated ${escapeHtml(runDate)} JST` : "Waiting for first scrape"}`;
    renderKpis(); renderMetricControls(); renderChart(); renderChanges(); renderCategories();
    populateManufacturerFilters(); renderManufacturers();
  } catch (error) {
    status.innerHTML = '<span class="status-dot"></span>Dashboard unavailable';
    status.classList.add("error");
    $("#kpi-grid").innerHTML = `<div class="loading-card">Could not load the local database: ${escapeHtml(error.message)}</div>`;
    console.error(error);
  }
}

$("#refresh-button").addEventListener("click", loadDashboard);
$("#manufacturer-search").addEventListener("input", renderManufacturers);
$("#manufacturer-category").addEventListener("change", renderManufacturers);
$("#manufacturer-state").addEventListener("change", renderManufacturers);
document.querySelectorAll(".sort-button").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.sortKey;
    if (state.manufacturerSortKey === key) {
      state.manufacturerSortDirection *= -1;
    } else {
      state.manufacturerSortKey = key;
      state.manufacturerSortDirection = -1;
    }
    renderManufacturers();
  });
});
loadDashboard();
