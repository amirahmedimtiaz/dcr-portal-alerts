const COLORS = {
  cell_manufactured: "#397f99",
  cell_sold: "#52ad89",
  module_manufactured: "#d69a35",
  module_sold: "#cf685d",
};

const SERIES_META = {
  cell_manufactured: { icon: "CM", short: "Cells manufactured" },
  cell_sold: { icon: "CS", short: "Cells sold" },
  module_manufactured: { icon: "MM", short: "Modules manufactured" },
  module_sold: { icon: "MS", short: "Modules sold" },
};

const CATEGORY_COLORS = ["#248b68", "#d69a35", "#397f99", "#cf685d"];

const STOCK_META = {
  cell_held: {
    icon: "SC",
    title: "Solar cells held",
    cardClass: "cell",
    color: "#397f99",
    unclaimedKey: "cell_unclaimed",
  },
  module_held: {
    icon: "SM",
    title: "Solar modules held",
    cardClass: "module",
    color: "#d69a35",
    unclaimedKey: "module_unclaimed",
  },
};

const FIELD_LABELS = {
  AgencyId: "Portal agency ID",
  AgencyName: "Company name",
  AgencyDistId: "Distribution agency ID",
  AgencyDist: "Distribution agency",
  AgentId: "Agent ID",
  CreditSubAgencyId: "Credit sub-agency ID",
  CompanyType: "Company category",
  CellDCR: "DCR cell stock with manufacturer",
  CellDCRQty: "DCR cell stock with reseller",
  CellDCR1: "DCR cells sold, unclaimed with manufacturer",
  CellDCR1Qty: "DCR cells sold, unclaimed with reseller",
  ModuleDCR: "DCR module stock with manufacturer",
  ModuleDCRQty: "DCR module stock with reseller",
  ModuleDCR1: "DCR modules sold, unclaimed with manufacturer",
  ModuleDCR1Qty: "DCR modules sold, unclaimed with reseller",
  CellNDCR: "NDCR cell stock",
  CellNDCR1: "NDCR cell unclaimed stock",
  ModuleNDCR: "NDCR module stock",
  ModuleNDCR1: "NDCR module unclaimed stock",
  CellProduced: "Cell-produced backend field",
  ModuleProduced: "Module-produced backend field",
  TotalUser: "Registered company users",
  TotalDCRCell: "Total DCR cell backend field",
  TotalDCRModule: "Total DCR module backend field",
  TotalDCR: "Total DCR backend field",
  TotalKWD: "Total DCR kW backend field",
  TotalKw: "Total kW backend field",
  PMSGApply: "PM Surya Ghar application flag",
  ForEndUser: "End-user flag",
  isActive: "Active account flag",
  PanNumber: "PAN number",
  GST: "GST number",
};

const state = {
  summary: null,
  metricSeries: [],
  manufacturers: [],
  filteredManufacturers: [],
  visibleMetrics: new Set(),
  manufacturerById: new Map(),
  manufacturerObservedAt: null,
  manufacturerSortKey: "agency_name",
  manufacturerSortDirection: 1,
  stockView: "cell_held",
  chartRange: 24,
  page: 1,
  pageSize: 25,
};

const STATIC_ENDPOINTS = {
  "/api/summary": "summary.json",
  "/api/metrics": "metrics.json",
  "/api/manufacturers": "manufacturers.json",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const numberFormat = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const integerFormat = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
let toastTimer;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value, suffix = "") {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  return `${numberFormat.format(Number(value))}${suffix}`;
}

function formatInteger(value) {
  return Number.isFinite(Number(value)) ? integerFormat.format(Number(value)) : "—";
}

function formatGrowth(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  const number = Number(value) * 100;
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function formatDelta(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  const number = Number(value);
  return `${number > 0 ? "+" : number < 0 ? "−" : ""}${formatNumber(Math.abs(number))} MW`;
}

function formatPeriod(period, short = false) {
  if (!/^\d{4}-\d{2}$/.test(period || "")) return period || "No data";
  const [year, month] = period.split("-").map(Number);
  return new Intl.DateTimeFormat("en", short
    ? { month: "short", year: "2-digit" }
    : { month: "short", year: "numeric" }).format(new Date(Date.UTC(year, month - 1, 1)));
}

function formatTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en", {
    timeZone: "Asia/Tokyo",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function compactCategory(value) {
  const text = String(value || "Manufacturer");
  if (text.startsWith("Both Solar-Cells")) return "Cells + modules";
  if (text.startsWith("Solar-Cells")) return "Cells only";
  if (text.startsWith("Solar-Panels")) return "Modules only";
  return text;
}

function numericRaw(item, key) {
  const value = Number(item?.raw?.[key]);
  return Number.isFinite(value) ? value : 0;
}

function seriesFor(key) {
  return state.metricSeries.find((series) => series.key === key);
}

function showToast(message) {
  const toast = $("#toast");
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.hidden = false;
  toastTimer = setTimeout(() => { toast.hidden = true; }, 2800);
}

function sparklineMarkup(series, color) {
  const points = (series?.points || []).slice(-12);
  if (points.length < 2) return "";
  const values = points.map((point) => Number(point.value));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const coords = values.map((value, index) => ({
    x: 2 + (index / (values.length - 1)) * 88,
    y: 28 - ((value - min) / range) * 24,
  }));
  const line = coords.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const area = `${line} L${coords.at(-1).x.toFixed(1)},31 L${coords[0].x.toFixed(1)},31 Z`;
  return `<svg class="sparkline" viewBox="0 0 92 32" role="img" aria-label="Recent twelve-month trend">
    <path class="sparkline-area" d="${area}" style="--metric-color:${color}"></path>
    <path class="sparkline-path" d="${line}" style="--metric-color:${color}"></path>
  </svg>`;
}

function renderSnapshot() {
  const states = new Set(state.manufacturers.map((item) => item.state).filter(Boolean));
  $("#snapshot-manufacturers").textContent = formatInteger(state.manufacturers.length);
  $("#snapshot-states").textContent = formatInteger(states.size);
  $("#snapshot-observations").textContent = formatInteger(state.summary?.monthly_value_count || 0);
}

function renderKpis() {
  const container = $("#kpi-grid");
  const metrics = state.summary?.metrics || [];
  if (!metrics.length) {
    container.innerHTML = '<div class="loading-card">No successful portal snapshot is available yet.</div>';
    return;
  }

  container.innerHTML = metrics.map((metric) => {
    const number = Number(metric.delta);
    const changeClass = metric.delta === null || metric.delta === undefined
      ? "flat"
      : metric.period_changed ? "new" : number > 0 ? "up" : number < 0 ? "down" : "flat";
    const arrow = changeClass === "up" ? "↗" : changeClass === "down" ? "↘" : changeClass === "new" ? "◆" : "→";
    const changeText = metric.delta === null || metric.delta === undefined
      ? "No baseline"
      : `${arrow} ${formatGrowth(metric.growth)}`;
    const series = seriesFor(metric.metric);
    const color = COLORS[metric.metric] || "#248b68";
    const meta = SERIES_META[metric.metric] || { icon: "DCR", short: metric.label };
    return `<article class="kpi-card" style="--metric-color:${color}">
      <div class="kpi-top">
        <span class="kpi-icon" aria-hidden="true">${escapeHtml(meta.icon)}</span>
        <span class="kpi-change ${changeClass}" title="${escapeHtml(formatDelta(metric.delta))}">${escapeHtml(changeText)}</span>
      </div>
      <div class="kpi-label">${escapeHtml(metric.label)}</div>
      <div class="kpi-value">${formatNumber(metric.current)}<small>MW</small></div>
      <div class="kpi-bottom">
        <span class="kpi-period">${escapeHtml(formatPeriod(metric.current_period))}<br>${escapeHtml(metric.comparison || "")}</span>
        ${sparklineMarkup(series, color)}
      </div>
      <button class="kpi-focus" type="button" data-focus-metric="${escapeHtml(metric.metric)}" aria-label="Show only ${escapeHtml(metric.label)} in trend chart">↘</button>
    </article>`;
  }).join("");

  container.querySelectorAll("[data-focus-metric]").forEach((button) => {
    button.addEventListener("click", () => {
      state.visibleMetrics = new Set([button.dataset.focusMetric]);
      renderMetricControls();
      renderChart();
      $("#trends").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function stockMetric(key) {
  return (state.summary?.stock_position?.metrics || []).find((metric) => metric.key === key);
}

function stockChange(metric) {
  if (metric?.delta === null || metric?.delta === undefined) {
    return { className: "neutral", text: "No baseline" };
  }
  const delta = Number(metric.delta);
  const arrow = delta > 0 ? "↗" : delta < 0 ? "↘" : "→";
  return {
    className: delta > 0 ? "positive" : delta < 0 ? "negative" : "neutral",
    text: `${arrow} ${formatDelta(delta)}`,
  };
}

function renderStockCards() {
  const container = $("#stock-cards");
  const heldMetrics = [stockMetric("cell_held"), stockMetric("module_held")].filter(Boolean);
  if (!heldMetrics.length) {
    container.innerHTML = '<div class="loading-card">No manufacturer stock snapshot is available yet.</div>';
    return;
  }
  const combinedHeld = heldMetrics.reduce((sum, metric) => sum + Number(metric.current || 0), 0);
  container.innerHTML = heldMetrics.map((metric) => {
    const meta = STOCK_META[metric.key];
    const unclaimed = stockMetric(meta.unclaimedKey);
    const change = stockChange(metric);
    const share = combinedHeld ? (Number(metric.current || 0) / combinedHeld) * 100 : 0;
    const growth = metric.growth === null || metric.growth === undefined
      ? "Previous snapshot unavailable"
      : `${formatGrowth(metric.growth)} since previous snapshot`;
    return `<article class="stock-card ${meta.cardClass}" style="--stock-color:${meta.color}">
      <div class="stock-card-head">
        <div class="stock-card-title">
          <span class="stock-type-icon" aria-hidden="true">${meta.icon}</span>
          <div><h3>${escapeHtml(meta.title)}</h3><p>Stock with manufacturers · current snapshot</p></div>
        </div>
        <span class="stock-change ${change.className}" title="${escapeHtml(growth)}">${escapeHtml(change.text)}</span>
      </div>
      <div class="stock-card-value">${formatNumber(metric.current)}<small>MW</small></div>
      <div class="stock-card-footer">
        <div>
          <div class="stock-share-label"><span>Share of combined held stock</span><strong>${share.toFixed(1)}%</strong></div>
          <div class="stock-share-track"><span style="width:${share.toFixed(2)}%"></span></div>
        </div>
        <div class="stock-unclaimed"><span>Sold · buyer unclaimed</span><strong>${formatNumber(unclaimed?.current)} MW</strong></div>
      </div>
    </article>`;
  }).join("");
}

function rankingItemMarkup(item, index, maximum, color, isHolder = false) {
  const value = Number(item.value || 0);
  const width = maximum > 0 ? Math.max(2, (value / maximum) * 100) : 0;
  const name = item.agency_name || item.state || "Unknown";
  const subtitle = isHolder ? (item.state || "State unavailable") : `${formatNumber(value)} MW held`;
  const content = `<span class="stock-ranking-item">
    <span class="stock-rank">${index + 1}</span>
    <span class="stock-ranking-copy">
      <span class="stock-ranking-name">${escapeHtml(name)}</span>
      <span class="stock-ranking-subtitle">${escapeHtml(subtitle)}</span>
      <span class="stock-ranking-bar"><span style="width:${width.toFixed(2)}%;--ranking-color:${color}"></span></span>
    </span>
    <strong class="stock-ranking-value">${formatNumber(value)}</strong>
  </span>`;
  if (!isHolder) return `<li>${content}</li>`;
  return `<li><button class="stock-holder-button" type="button" data-stock-holder="${escapeHtml(item.agency_id)}" aria-label="Open ${escapeHtml(name)} manufacturer profile">${content}</button></li>`;
}

function renderStockRanking() {
  const stock = state.summary?.stock_position;
  if (!stock) return;
  const key = state.stockView;
  const meta = STOCK_META[key];
  $$("[data-stock-key]").forEach((button) => {
    const active = button.dataset.stockKey === key;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });

  const states = (stock.states || [])
    .map((item) => ({ state: item.state, value: Number(item[key] || 0) }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);
  const holders = stock.top_holders?.[key] || [];
  const stateMaximum = Number(states[0]?.value || 0);
  const holderMaximum = Number(holders[0]?.value || 0);
  $("#stock-state-ranking").innerHTML = states.length
    ? states.map((item, index) => rankingItemMarkup(item, index, stateMaximum, meta.color)).join("")
    : '<li class="loading-card">No state stock totals available.</li>';
  $("#stock-holder-ranking").innerHTML = holders.length
    ? holders.map((item, index) => rankingItemMarkup(item, index, holderMaximum, meta.color, true)).join("")
    : '<li class="loading-card">No manufacturer stock totals available.</li>';
  $("#stock-holder-ranking").querySelectorAll("[data-stock-holder]").forEach((button) => {
    button.addEventListener("click", () => openDetails(state.manufacturerById.get(button.dataset.stockHolder)));
  });
}

function renderStockPosition() {
  renderStockCards();
  renderStockRanking();
}

function renderMetricControls() {
  const controls = $("#metric-controls");
  if (!state.visibleMetrics.size) state.metricSeries.forEach((series) => state.visibleMetrics.add(series.key));
  controls.innerHTML = state.metricSeries.map((series) => {
    const active = state.visibleMetrics.has(series.key);
    const color = COLORS[series.key] || "#248b68";
    return `<button class="series-toggle ${active ? "active" : ""}" data-metric="${escapeHtml(series.key)}" type="button" aria-pressed="${active}" style="--series-color:${color}">
      <span class="series-swatch" aria-hidden="true"></span>${escapeHtml(SERIES_META[series.key]?.short || series.label)}
    </button>`;
  }).join("");

  controls.querySelectorAll("[data-metric]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.metric;
      if (state.visibleMetrics.has(key) && state.visibleMetrics.size === 1) {
        showToast("Keep at least one trend visible.");
        return;
      }
      if (state.visibleMetrics.has(key)) state.visibleMetrics.delete(key);
      else state.visibleMetrics.add(key);
      renderMetricControls();
      renderChart();
    });
  });
}

function niceMaximum(value) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return nice * magnitude;
}

function chartData() {
  const selected = state.metricSeries.filter((series) => state.visibleMetrics.has(series.key));
  const allPeriods = [...new Set(selected.flatMap((series) => series.points.map((point) => point.period)))].sort();
  const periods = state.chartRange === "all" ? allPeriods : allPeriods.slice(-Number(state.chartRange));
  const periodSet = new Set(periods);
  return {
    selected: selected.map((series) => ({ ...series, points: series.points.filter((point) => periodSet.has(point.period)) })),
    periods,
  };
}

function renderChart() {
  const svg = $("#trend-chart");
  const tooltip = $("#chart-tooltip");
  const { selected, periods } = chartData();
  if (!selected.length || !periods.length) {
    svg.innerHTML = '<text x="500" y="215" text-anchor="middle" class="chart-axis-label">No history loaded yet</text>';
    tooltip.hidden = true;
    return;
  }

  const width = 1000;
  const height = 430;
  const margin = { top: 25, right: 24, bottom: 48, left: 66 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const maxValue = Math.max(...selected.flatMap((series) => series.points.map((point) => Number(point.value))), 1);
  const yMaximum = niceMaximum(maxValue * 1.05);
  const xPosition = (index) => margin.left + (periods.length === 1 ? plotWidth / 2 : (index / (periods.length - 1)) * plotWidth);
  const yPosition = (value) => margin.top + plotHeight - (Number(value) / yMaximum) * plotHeight;
  const periodIndex = new Map(periods.map((period, index) => [period, index]));
  const grid = [];

  for (let i = 0; i <= 5; i += 1) {
    const value = (yMaximum / 5) * i;
    const y = yPosition(value);
    grid.push(`<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" class="chart-gridline"/>`);
    grid.push(`<text x="${margin.left - 12}" y="${y + 4}" text-anchor="end" class="chart-axis-label">${formatNumber(value)}</text>`);
  }
  grid.push(`<line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" class="chart-axis-line"/>`);

  const labelEvery = Math.max(1, Math.ceil(periods.length / 7));
  periods.forEach((period, index) => {
    if (index % labelEvery !== 0 && index !== periods.length - 1) return;
    grid.push(`<text x="${xPosition(index)}" y="${height - 17}" text-anchor="middle" class="chart-axis-label">${escapeHtml(formatPeriod(period, true))}</text>`);
  });

  const lines = [];
  selected.forEach((series) => {
    const color = COLORS[series.key] || "#248b68";
    const pointMap = new Map(series.points.map((point) => [point.period, point]));
    const points = periods.map((period, index) => {
      const point = pointMap.get(period);
      return point ? { ...point, x: xPosition(index), y: yPosition(point.value) } : null;
    }).filter(Boolean);
    if (!points.length) return;
    const path = points.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
    lines.push(`<path d="${path}" class="chart-line ${series.key.endsWith("_sold") ? "sold" : ""}" stroke="${color}"/>`);
    points.forEach((point) => lines.push(`<circle cx="${point.x}" cy="${point.y}" r="2.8" class="chart-point" fill="${color}"/>`));
  });

  svg.innerHTML = `${grid.join("")}${lines.join("")}
    <g id="chart-hover-layer" hidden></g>
    <rect x="${margin.left}" y="${margin.top}" width="${plotWidth}" height="${plotHeight}" class="chart-hit-area"/>`;

  const hoverLayer = $("#chart-hover-layer");
  const hitArea = svg.querySelector(".chart-hit-area");
  const showHover = (event) => {
    const bounds = svg.getBoundingClientRect();
    const svgX = ((event.clientX - bounds.left) / bounds.width) * width;
    const normalized = Math.max(0, Math.min(1, (svgX - margin.left) / plotWidth));
    const index = Math.round(normalized * Math.max(periods.length - 1, 0));
    const period = periods[index];
    const x = xPosition(index);
    const rows = [];
    const circles = [];
    selected.forEach((series) => {
      const point = series.points.find((entry) => entry.period === period);
      if (!point) return;
      const color = COLORS[series.key] || "#248b68";
      rows.push(`<div class="tooltip-row"><span class="tooltip-dot" style="--series-color:${color}"></span><span>${escapeHtml(SERIES_META[series.key]?.short || series.label)}</span><strong>${formatNumber(point.value)} MW</strong></div>`);
      circles.push(`<circle cx="${x}" cy="${yPosition(point.value)}" r="5" class="chart-hover-point" fill="${color}"/>`);
    });
    hoverLayer.hidden = false;
    hoverLayer.innerHTML = `<line x1="${x}" y1="${margin.top}" x2="${x}" y2="${margin.top + plotHeight}" class="chart-crosshair"/>${circles.join("")}`;
    tooltip.innerHTML = `<div class="tooltip-period">${escapeHtml(formatPeriod(period))}</div>${rows.join("")}`;
    tooltip.hidden = false;
    const wrap = $("#chart-wrap").getBoundingClientRect();
    const pointerX = event.clientX - wrap.left;
    const pointerY = event.clientY - wrap.top;
    tooltip.style.left = `${Math.max(8, Math.min(wrap.width - 228, pointerX + (pointerX > wrap.width * .7 ? -230 : 16)))}px`;
    tooltip.style.top = `${Math.max(8, Math.min(wrap.height - tooltip.offsetHeight - 8, pointerY - tooltip.offsetHeight / 2))}px`;
  };
  const hideHover = () => {
    hoverLayer.hidden = true;
    tooltip.hidden = true;
  };
  hitArea.addEventListener("pointermove", showHover);
  hitArea.addEventListener("pointerdown", showHover);
  hitArea.addEventListener("pointerleave", hideHover);

  $("#chart-legend").innerHTML = selected.map((series) => {
    const color = COLORS[series.key] || "#248b68";
    return `<span class="legend-item"><span class="series-swatch" style="--series-color:${color}"></span>${escapeHtml(series.label)}${series.key.endsWith("_sold") ? " · dashed" : ""}</span>`;
  }).join("");
}

function renderChanges() {
  const metrics = state.summary?.metrics || [];
  $("#change-summary").innerHTML = metrics.map((metric) => {
    const delta = Number(metric.delta);
    const cls = metric.delta === null || metric.delta === undefined ? "neutral" : delta > 0 ? "positive" : delta < 0 ? "negative" : "neutral";
    return `<div class="change-row">
      <div><div class="change-row-label">${escapeHtml(metric.label)}</div><div class="change-row-detail">${escapeHtml(metric.comparison || "No comparison")} · ${escapeHtml(formatPeriod(metric.current_period))}</div></div>
      <div class="change-value ${cls}">${escapeHtml(formatDelta(metric.delta))}<br><span>${escapeHtml(formatGrowth(metric.growth))}</span></div>
    </div>`;
  }).join("") || '<p class="panel-description">No metric observations yet.</p>';

  const run = state.summary?.latest_run;
  $("#run-meta").textContent = run
    ? `Snapshot #${run.id} · ${run.full_history ? "historical backfill" : "weekly refresh"} · ${formatTimestamp(run.finished_at || run.started_at)} JST`
    : "";
}

function renderCategories() {
  const entries = Object.entries(state.summary?.manufacturer_counts || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
  const total = entries.reduce((sum, [, value]) => sum + Number(value), 0);
  $("#manufacturer-total-badge").textContent = `${formatInteger(total)} total`;
  $("#mix-total").textContent = formatInteger(total);
  const first = total ? (Number(entries[0]?.[1] || 0) / total) * 100 : 0;
  const second = total ? first + (Number(entries[1]?.[1] || 0) / total) * 100 : 0;
  $("#mix-ring").style.setProperty("--mix-a", `${first}%`);
  $("#mix-ring").style.setProperty("--mix-b", `${second}%`);
  $("#category-summary").innerHTML = entries.map(([name, value], index) => `<div class="category-row" title="${escapeHtml(name)}">
    <div class="category-name">${escapeHtml(compactCategory(name))}</div><div class="category-value">${formatInteger(value)}</div>
    <div class="category-bar"><span style="width:${total ? Math.max(3, (Number(value) / total) * 100) : 0}%;--bar-color:${CATEGORY_COLORS[index % CATEGORY_COLORS.length]}"></span></div>
  </div>`).join("") || '<p class="panel-description">No manufacturer list yet.</p>';
}

function renderManufacturerStats() {
  const cellCompanies = state.manufacturers.filter((item) => String(item.company_type).includes("Solar-Cells")).length;
  const moduleCompanies = state.manufacturers.filter((item) => String(item.company_type).includes("Solar-Panels")).length;
  const cellStock = state.manufacturers.reduce((sum, item) => sum + numericRaw(item, "CellDCR"), 0);
  const moduleStock = state.manufacturers.reduce((sum, item) => sum + numericRaw(item, "ModuleDCR"), 0);
  const stats = [
    [cellCompanies, "Cell-capable manufacturers"],
    [moduleCompanies, "Module-capable manufacturers"],
    [formatNumber(cellStock), "DCR cell stock with manufacturers · MW"],
    [formatNumber(moduleStock), "DCR module stock with manufacturers · MW"],
  ];
  $("#manufacturer-stats").innerHTML = stats.map(([value, label]) => `<div class="manufacturer-stat"><span class="manufacturer-stat-value">${escapeHtml(value)}</span><span class="manufacturer-stat-label">${escapeHtml(label)}</span></div>`).join("");
}

function populateManufacturerFilters() {
  const category = $("#manufacturer-category");
  const stateSelect = $("#manufacturer-state");
  const categories = [...new Set(state.manufacturers.map((item) => item.company_type).filter(Boolean))].sort();
  const states = [...new Set(state.manufacturers.map((item) => item.state).filter(Boolean))].sort();
  category.innerHTML = '<option value="">All categories</option>' + categories.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(compactCategory(value))}</option>`).join("");
  stateSelect.innerHTML = '<option value="">All states</option>' + states.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
}

function filteredAndSortedManufacturers() {
  const search = $("#manufacturer-search").value.trim().toLowerCase();
  const category = $("#manufacturer-category").value;
  const selectedState = $("#manufacturer-state").value;
  return state.manufacturers.filter((item) => {
    if (category && item.company_type !== category) return false;
    if (selectedState && item.state !== selectedState) return false;
    if (search) {
      const haystack = [item.agency_name, item.state, item.company_type, item.raw?.Email].filter(Boolean).join(" ").toLowerCase();
      if (!haystack.includes(search)) return false;
    }
    return true;
  }).sort((a, b) => {
    const key = state.manufacturerSortKey;
    if (["agency_name", "State", "CompanyType"].includes(key)) {
      const aValue = key === "agency_name" ? a.agency_name : key === "State" ? a.state : a.company_type;
      const bValue = key === "agency_name" ? b.agency_name : key === "State" ? b.state : b.company_type;
      return String(aValue || "").localeCompare(String(bValue || ""), undefined, { sensitivity: "base" }) * state.manufacturerSortDirection;
    }
    return (numericRaw(a, key) - numericRaw(b, key)) * state.manufacturerSortDirection;
  });
}

function renderFilterSummary(items) {
  const cellStock = items.reduce((sum, item) => sum + numericRaw(item, "CellDCR"), 0);
  const moduleStock = items.reduce((sum, item) => sum + numericRaw(item, "ModuleDCR"), 0);
  const active = [];
  const search = $("#manufacturer-search").value.trim();
  if (search) active.push(`Search: “${search}”`);
  if ($("#manufacturer-category").value) active.push(compactCategory($("#manufacturer-category").value));
  if ($("#manufacturer-state").value) active.push($("#manufacturer-state").value);
  $("#active-filter-summary").innerHTML = `
    <span class="filter-summary-item"><strong>${formatInteger(items.length)}</strong> matches</span>
    <span class="filter-summary-item"><strong>${formatNumber(cellStock)}</strong> MW cell stock</span>
    <span class="filter-summary-item"><strong>${formatNumber(moduleStock)}</strong> MW module stock</span>
    ${active.map((label) => `<span class="filter-summary-item">${escapeHtml(label)}</span>`).join("")}`;
}

function syncSortControls() {
  $$(".sort-button").forEach((button) => {
    const active = button.dataset.sortKey === state.manufacturerSortKey;
    button.classList.toggle("active", active);
    button.closest("th").setAttribute("aria-sort", active ? (state.manufacturerSortDirection === 1 ? "ascending" : "descending") : "none");
    const indicator = button.querySelector(".sort-indicator");
    if (indicator) indicator.textContent = active ? (state.manufacturerSortDirection === 1 ? "↑" : "↓") : "↕";
  });
  const select = $("#manufacturer-sort");
  const desired = `${state.manufacturerSortKey}:${state.manufacturerSortDirection}`;
  if ([...select.options].some((option) => option.value === desired)) select.value = desired;
}

function renderManufacturers() {
  state.filteredManufacturers = filteredAndSortedManufacturers();
  const pageSize = state.pageSize === "all" ? Math.max(state.filteredManufacturers.length, 1) : Number(state.pageSize);
  const totalPages = Math.max(1, Math.ceil(state.filteredManufacturers.length / pageSize));
  state.page = Math.max(1, Math.min(state.page, totalPages));
  const start = (state.page - 1) * pageSize;
  const pageItems = state.filteredManufacturers.slice(start, start + pageSize);
  const tbody = $("#manufacturer-table");

  $("#manufacturer-count").textContent = `${formatInteger(state.manufacturers.length)} records · refreshed ${formatTimestamp(state.manufacturerObservedAt)} JST`;
  $("#manufacturer-visible-count").textContent = state.filteredManufacturers.length
    ? `Showing ${formatInteger(start + 1)}–${formatInteger(Math.min(start + pageItems.length, state.filteredManufacturers.length))} of ${formatInteger(state.filteredManufacturers.length)}`
    : "No matching manufacturers";
  $("#page-indicator").textContent = `Page ${state.page} of ${totalPages}`;
  $("#previous-page").disabled = state.page <= 1;
  $("#next-page").disabled = state.page >= totalPages;

  if (!pageItems.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">No manufacturers match the current filters.</td></tr>';
  } else {
    tbody.innerHTML = pageItems.map((item) => {
      const raw = item.raw || {};
      const cell = numericRaw(item, "CellDCR");
      const module = numericRaw(item, "ModuleDCR");
      return `<tr>
        <td class="company-cell" data-label="Company"><span class="company-name">${escapeHtml(item.agency_name || raw.AgencyName || "Unknown")}</span><span class="company-email">${escapeHtml(raw.Email || "No public email")}</span></td>
        <td data-label="State">${escapeHtml(item.state || raw.State || "—")}</td>
        <td data-label="Category"><span class="category-chip" title="${escapeHtml(item.company_type || raw.CompanyType || "")}">${escapeHtml(compactCategory(item.company_type || raw.CompanyType))}</span></td>
        <td class="numeric" data-label="DCR cell stock · MW"><span class="stock-value ${cell === 0 ? "zero" : ""}">${formatNumber(cell)}</span></td>
        <td class="numeric" data-label="DCR module stock · MW"><span class="stock-value ${module === 0 ? "zero" : ""}">${formatNumber(module)}</span></td>
        <td data-label="Details"><button class="details-button" type="button" data-details-id="${escapeHtml(item.agency_id)}">View profile <span aria-hidden="true">→</span></button></td>
      </tr>`;
    }).join("");
  }

  tbody.querySelectorAll("[data-details-id]").forEach((button) => {
    button.addEventListener("click", () => openDetails(state.manufacturerById.get(button.dataset.detailsId)));
  });
  renderFilterSummary(state.filteredManufacturers);
  syncSortControls();
}

function displayRawValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "number") return formatNumber(value);
  return String(value);
}

function humanizeKey(key) {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/DCR/g, "DCR")
    .replace(/NDCR/g, "NDCR")
    .replace(/Id\b/g, "ID")
    .replace(/Qty\b/g, "quantity");
}

function openDetails(item) {
  if (!item) return;
  const raw = item.raw || {};
  const dialog = $("#manufacturer-dialog");
  $("#details-title").textContent = item.agency_name || raw.AgencyName || "Manufacturer details";
  $("#details-category").textContent = compactCategory(item.company_type || raw.CompanyType);
  $("#details-location").textContent = `${item.state || raw.State || "State unavailable"} · NISE public manufacturer record`;

  const metrics = [
    ["CellDCR", "DCR cell stock", "Currently with manufacturer"],
    ["ModuleDCR", "DCR module stock", "Currently with manufacturer"],
    ["CellDCR1", "Cell sold · unclaimed", "Buyer has not claimed it"],
    ["ModuleDCR1", "Module sold · unclaimed", "Buyer has not claimed it"],
  ];
  $("#detail-metrics").innerHTML = metrics.map(([key, label, help]) => `<div class="detail-metric"><span>${escapeHtml(label)}</span><strong>${formatNumber(raw[key])}<small> MW</small></strong><small>${escapeHtml(help)}</small></div>`).join("");

  const info = [
    ["State", item.state || raw.State],
    ["Company category", item.company_type || raw.CompanyType],
    ["Public email", raw.Email],
    ["Portal agency ID", item.agency_id || raw.AgencyId],
  ];
  $("#company-info").innerHTML = info.map(([label, value]) => {
    const safeValue = escapeHtml(value || "—");
    const renderedValue = label === "Public email" && value
      ? `<a href="mailto:${safeValue}">${safeValue}</a>`
      : safeValue;
    return `<div><dt>${escapeHtml(label)}</dt><dd>${renderedValue}</dd></div>`;
  }).join("");

  $("#details-grid").innerHTML = Object.entries(raw).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => {
    const label = FIELD_LABELS[key] || humanizeKey(key);
    return `<div><dt>${escapeHtml(label)}<span class="raw-key">${escapeHtml(key)}</span></dt><dd>${escapeHtml(displayRawValue(value))}</dd></div>`;
  }).join("");
  dialog.querySelector(".raw-details").open = false;
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "open");
}

function resetFilters() {
  $("#manufacturer-search").value = "";
  $("#manufacturer-category").value = "";
  $("#manufacturer-state").value = "";
  $("#clear-search").hidden = true;
  state.manufacturerSortKey = "agency_name";
  state.manufacturerSortDirection = 1;
  state.page = 1;
  renderManufacturers();
}

function csvCell(value) {
  let text = value === null || value === undefined ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function exportFilteredCsv() {
  const items = state.filteredManufacturers;
  if (!items.length) {
    showToast("There are no matching manufacturers to export.");
    return;
  }
  const rawFields = [...new Set(items.flatMap((item) => Object.keys(item.raw || {})))].sort();
  const headers = ["AgencyName", "State", "CompanyType", ...rawFields.filter((field) => !["AgencyName", "State", "CompanyType"].includes(field))];
  const rows = [headers.map(csvCell).join(",")];
  items.forEach((item) => {
    const record = { ...(item.raw || {}), AgencyName: item.agency_name, State: item.state, CompanyType: item.company_type };
    rows.push(headers.map((field) => csvCell(record[field])).join(","));
  });
  const blob = new Blob([`\ufeff${rows.join("\n")}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `solar-dcr-manufacturers-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  showToast(`Exported ${formatInteger(items.length)} manufacturer records.`);
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const dark = theme === "dark";
  $("#theme-toggle").setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
  $("#theme-toggle").setAttribute("aria-pressed", String(dark));
  document.querySelector('meta[name="theme-color"]').setAttribute("content", dark ? "#08151b" : "#0b1f29");
}

function initializeTheme() {
  let saved;
  try { saved = localStorage.getItem("dcr-theme"); } catch (_) { saved = null; }
  applyTheme(saved || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
}

async function fetchJson(path, requestVersion = Date.now()) {
  const staticMode = window.DCR_STATIC_DATA === true;
  const target = staticMode
    ? `data/${STATIC_ENDPOINTS[path]}?v=${encodeURIComponent(`${window.DCR_DATA_VERSION || "published"}-${requestVersion}`)}`
    : path;
  const response = await fetch(target, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

async function loadDashboard() {
  const status = $("#last-updated");
  const refresh = $("#refresh-button");
  status.innerHTML = '<span class="status-dot"></span>Refreshing…';
  status.classList.remove("error");
  refresh.disabled = true;
  try {
    const requestVersion = Date.now();
    const [summary, metricData, manufacturerData] = await Promise.all([
      fetchJson("/api/summary", requestVersion),
      fetchJson("/api/metrics", requestVersion),
      fetchJson("/api/manufacturers", requestVersion),
    ]);
    state.summary = summary.ready ? summary : null;
    state.metricSeries = metricData.series || [];
    state.manufacturers = manufacturerData.items || [];
    state.manufacturerObservedAt = manufacturerData.observed_at;
    state.manufacturerById = new Map(state.manufacturers.map((item) => [item.agency_id, item]));
    if (!state.visibleMetrics.size) state.metricSeries.forEach((series) => state.visibleMetrics.add(series.key));
    const runDate = summary.latest_run?.finished_at || summary.latest_run?.started_at;
    const checkedAt = formatTimestamp(new Date().toISOString());
    status.innerHTML = `<span class="status-dot"></span><span class="status-copy">${runDate
      ? `<strong>Published ${escapeHtml(formatTimestamp(runDate))} JST</strong><small>Checked ${escapeHtml(checkedAt)} JST</small>`
      : "<strong>Awaiting first snapshot</strong>"}</span>`;
    renderSnapshot();
    renderKpis();
    renderStockPosition();
    renderMetricControls();
    renderChart();
    renderChanges();
    renderCategories();
    renderManufacturerStats();
    populateManufacturerFilters();
    renderManufacturers();
  } catch (error) {
    status.innerHTML = '<span class="status-dot"></span><span class="status-copy"><strong>Data unavailable</strong><small>Try again shortly</small></span>';
    status.classList.add("error");
    $("#kpi-grid").innerHTML = `<div class="loading-card">The published data could not be loaded. ${escapeHtml(error.message)}</div>`;
    $("#stock-cards").innerHTML = '<div class="loading-card">The stock snapshot could not be loaded.</div>';
    console.error(error);
  } finally {
    refresh.disabled = false;
  }
}

function bindEvents() {
  $("#refresh-button").addEventListener("click", loadDashboard);
  $("#theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("dcr-theme", next); } catch (_) { /* Local preferences are optional. */ }
    renderChart();
  });
  $$("[data-stock-key]").forEach((button) => {
    button.addEventListener("click", () => {
      state.stockView = button.dataset.stockKey;
      renderStockRanking();
    });
  });
  $$("[data-range]").forEach((button) => {
    button.addEventListener("click", () => {
      state.chartRange = button.dataset.range === "all" ? "all" : Number(button.dataset.range);
      $$("[data-range]").forEach((item) => item.classList.toggle("active", item === button));
      renderChart();
    });
  });

  const search = $("#manufacturer-search");
  search.addEventListener("input", () => {
    $("#clear-search").hidden = !search.value;
    state.page = 1;
    renderManufacturers();
  });
  $("#clear-search").addEventListener("click", () => {
    search.value = "";
    $("#clear-search").hidden = true;
    search.focus();
    state.page = 1;
    renderManufacturers();
  });
  ["#manufacturer-category", "#manufacturer-state"].forEach((selector) => {
    $(selector).addEventListener("change", () => { state.page = 1; renderManufacturers(); });
  });
  $("#manufacturer-sort").addEventListener("change", (event) => {
    const [key, direction] = event.target.value.split(":");
    state.manufacturerSortKey = key;
    state.manufacturerSortDirection = Number(direction);
    state.page = 1;
    renderManufacturers();
  });
  $$(".sort-button").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.sortKey;
      if (state.manufacturerSortKey === key) state.manufacturerSortDirection *= -1;
      else {
        state.manufacturerSortKey = key;
        state.manufacturerSortDirection = ["CellDCR", "ModuleDCR"].includes(key) ? -1 : 1;
      }
      state.page = 1;
      renderManufacturers();
    });
  });
  $("#page-size").addEventListener("change", (event) => {
    state.pageSize = event.target.value === "all" ? "all" : Number(event.target.value);
    state.page = 1;
    renderManufacturers();
  });
  $("#previous-page").addEventListener("click", () => { state.page -= 1; renderManufacturers(); });
  $("#next-page").addEventListener("click", () => { state.page += 1; renderManufacturers(); });
  $("#reset-filters").addEventListener("click", resetFilters);
  $("#export-csv").addEventListener("click", exportFilteredCsv);

  const dialog = $("#manufacturer-dialog");
  dialog.querySelector(".modal-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
}

initializeTheme();
bindEvents();
loadDashboard();
