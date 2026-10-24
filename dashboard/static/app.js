// ============================================================================
// ALPHATERMINAL v2.0 — FRONTEND SPA ENGINE
// ============================================================================

window.overviewData = null;
window.moatStudioStocks = [];
window.filteredMoatStocks = [];
window.lastScreenerResults = [];
window.moonshotData = [];
window.filteredMoonshots = [];
window.megaCapData = [];
window.currentDeepDiveData = null;
window.currentDeepDiveTicker = "TSM";
window.currentSimulatedTimeline = [];

const PLOTLY_DARK_LAYOUT = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(15,23,42,0.45)",
  font: { family: "Inter, sans-serif", color: "#cbd5e1", size: 11 },
  margin: { l: 48, r: 22, t: 28, b: 42 },
  xaxis: { gridcolor: "#1e293b", zerolinecolor: "#334155" },
  yaxis: { gridcolor: "#1e293b", zerolinecolor: "#334155" },
};

const PLOTLY_CONFIG = { responsive: true, displayModeBar: false };

function fmtNum(v, decimals = 2, prefix = "", suffix = "") {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return `${prefix}${Number(v).toFixed(decimals)}${suffix}`;
}

function fmtSigned(v, decimals = 1, suffix = "%") {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(decimals)}${suffix}`;
}

function badgeColorClass(badge) {
  const b = String(badge || "");
  if (b.includes("Dual-Survivor") || b.includes("Unicorn")) {
    return "bg-amber-500/20 text-amber-300 border-amber-500/40";
  }
  if (b.includes("Mega-Cap")) {
    return "bg-indigo-500/20 text-indigo-300 border-indigo-500/40";
  }
  if (b.includes("Elite Moat")) {
    return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
  }
  if (b.includes("Moonshot")) {
    return "bg-rose-500/20 text-rose-300 border-rose-500/40";
  }
  if (b.includes("Compounder")) {
    return "bg-sky-500/20 text-sky-300 border-sky-500/40";
  }
  return "bg-slate-800 text-slate-300 border-slate-700";
}

// ============================================================================
// NAVIGATION & DEEP-DIVE JUMP
// ============================================================================
function switchTab(tabId) {
  document.querySelectorAll(".tab-panel").forEach((el) => el.classList.add("hidden"));
  const target = document.getElementById(tabId);
  if (target) target.classList.remove("hidden");

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    if (btn.getAttribute("data-tab") === tabId) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // Trigger Plotly resize so hidden charts expand cleanly
  setTimeout(() => {
    window.dispatchEvent(new Event("resize"));
  }, 60);
}

function openStockDeepDive(ticker) {
  if (!ticker) return;
  switchTab("tab-valuation");
  loadCompanyDeepDive(ticker);
}

// ============================================================================
// CSV EXPORT HELPER
// ============================================================================
function exportTableArrayToCSV(rows, filename = "export.csv") {
  if (!rows || !rows.length) {
    alert("No rows to export.");
    return;
  }
  const headers = Object.keys(rows[0]);
  const csvLines = [
    headers.map((h) => `"${String(h).replace(/"/g, '""')}"`).join(","),
    ...rows.map((row) =>
      headers
        .map((h) => {
          const val = row[h];
          if (val === null || val === undefined) return "";
          return `"${String(val).replace(/"/g, '""')}"`;
        })
        .join(",")
    ),
  ];
  const blob = new Blob([csvLines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ============================================================================
// GLOBAL SEARCH ('/' SHORTCUT ACROSS ALL 8,768 TICKERS)
// ============================================================================
let searchDebounceTimer = null;

function setupGlobalSearch() {
  const input = document.getElementById("globalSearchInput");
  const dropdown = document.getElementById("globalSearchResults");

  window.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== input && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) {
      e.preventDefault();
      input.focus();
      input.select();
    } else if (e.key === "Escape") {
      dropdown.classList.add("hidden");
    }
  });

  input.addEventListener("input", () => {
    const q = input.value.trim();
    clearTimeout(searchDebounceTimer);
    if (!q) {
      dropdown.classList.add("hidden");
      return;
    }
    searchDebounceTimer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=20`);
        const data = await res.json();
        const items = data.results || [];
        if (!items.length) {
          dropdown.innerHTML = `<div class="p-3 text-xs text-slate-400 font-mono">No matching tickers in market_data.db</div>`;
        } else {
          dropdown.innerHTML = items
            .map(
              (item) => `
              <div onclick="selectGlobalSearchTicker('${item.ticker}')" class="px-3.5 py-2.5 hover:bg-slate-800/90 cursor-pointer flex items-center justify-between gap-2 transition">
                <div>
                  <div class="flex items-center gap-2">
                    <span class="font-mono font-bold text-emerald-400 text-xs">${item.ticker}</span>
                    <span class="text-xs text-white font-medium truncate max-w-[210px]">${item.company_name}</span>
                  </div>
                  <div class="text-[10px] text-slate-400 font-mono">${item.sector} • $${fmtNum(item.market_cap_b, 2)}B • P/E: ${fmtNum(item.forward_pe, 1)}x • ROIC: ${fmtNum(item.roic_pct, 1)}%</div>
                </div>
                <div class="flex flex-wrap gap-1 justify-end">
                  ${(item.badges || [])
                    .map(
                      (b) =>
                        `<span class="px-1.5 py-0.5 text-[10px] font-mono rounded border ${badgeColorClass(b)}">${b}</span>`
                    )
                    .join("")}
                </div>
              </div>
            `
            )
            .join("");
        }
        dropdown.classList.remove("hidden");
      } catch (err) {
        console.error("Search error:", err);
      }
    }, 140);
  });

  document.addEventListener("click", (e) => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.classList.add("hidden");
    }
  });
}

function selectGlobalSearchTicker(ticker) {
  document.getElementById("globalSearchResults").classList.add("hidden");
  document.getElementById("globalSearchInput").value = "";
  openStockDeepDive(ticker);
}

// ============================================================================
// TAB 1: EXECUTIVE COMMAND CENTER
// ============================================================================
async function loadOverviewTab() {
  const res = await fetch("/api/overview");
  const data = await res.json();
  window.overviewData = data;

  const k = data.kpis;
  document.getElementById("headerDbStatus").textContent = `${k.total_tickers.toLocaleString()} DB / ${k.active_tickers.toLocaleString()} Active`;

  const kpiCards = [
    { label: "Total SEC / Yahoo DB", val: k.total_tickers.toLocaleString(), sub: `${k.active_tickers.toLocaleString()} Active Tradable`, accent: "text-white" },
    { label: "Compounder Screener", val: k.compounders_count, sub: `Med 5Y CAGR: ${fmtSigned(k.median_compounder_cagr_pct, 2)}`, accent: "text-sky-400" },
    { label: "Elite Moat Survivors", val: k.elite_moat_count, sub: `Med Moat Score: ${fmtNum(k.median_elite_moat_score, 1)}/100`, accent: "text-emerald-400" },
    { label: "Asymmetric Moonshots", val: k.moonshots_count, sub: `Med 3Y Upside: ${fmtSigned(k.median_moonshot_3y_return_pct, 1)}`, accent: "text-rose-400" },
    { label: "Dual-Survivor Unicorns", val: k.dual_survivors_count, sub: "Passed Both Pipelines", accent: "text-amber-300" },
    { label: "Mega-Cap Club ($1T+)", val: k.mega_caps_count, sub: "Anchor & Swing Watch", accent: "text-indigo-400" },
    { label: "SQLite Connection", val: "READ-ONLY", sub: "Zero Lock (?mode=ro)", accent: "text-cyan-400" },
  ];

  document.getElementById("overviewKpiGrid").innerHTML = kpiCards
    .map(
      (c) => `
      <div class="glass-card p-3.5 flex flex-col justify-between">
        <span class="text-[11px] text-slate-400 font-medium">${c.label}</span>
        <div class="text-xl font-bold font-mono my-1 ${c.accent}">${c.val}</div>
        <span class="text-[10px] font-mono text-slate-400">${c.sub}</span>
      </div>
    `
    )
    .join("");

  // Market Cap Tier Table
  const tierBody = document.getElementById("overviewTierTableBody");
  tierBody.innerHTML = (data.tier_summary || [])
    .map(
      (t) => `
      <tr class="row-hover">
        <td class="py-2 pr-2 font-sans text-slate-200 font-medium">${t.tier}</td>
        <td class="py-2 px-2 text-right text-slate-300">${t.active_universe.toLocaleString()}</td>
        <td class="py-2 px-2 text-right text-sky-400 font-semibold">${t.compounder_shortlist} <span class="text-[10px] text-slate-500">(${t.compounder_pass_rate_pct}%)</span></td>
        <td class="py-2 px-2 text-right text-emerald-400 font-semibold">${t.elite_moat_survivors}</td>
        <td class="py-2 pl-2 text-right text-amber-400 font-semibold">${t.asymmetric_moonshots}</td>
      </tr>
    `
    )
    .join("");

  // Tier Grouped Bar Chart
  const tiers = (data.tier_summary || []).map((t) => t.tier.split(" ")[0]);
  Plotly.newPlot(
    "overviewTierBarChart",
    [
      {
        name: "Compounder Screener (204)",
        x: tiers,
        y: data.tier_summary.map((t) => t.compounder_shortlist),
        type: "bar",
        marker: { color: "#38bdf8" },
      },
      {
        name: "Elite Moat (136)",
        x: tiers,
        y: data.tier_summary.map((t) => t.elite_moat_survivors),
        type: "bar",
        marker: { color: "#10b981" },
      },
      {
        name: "Moonshots (60)",
        x: tiers,
        y: data.tier_summary.map((t) => t.asymmetric_moonshots),
        type: "bar",
        marker: { color: "#f59e0b" },
      },
    ],
    {
      ...PLOTLY_DARK_LAYOUT,
      barmode: "group",
      margin: { l: 36, r: 12, t: 24, b: 32 },
      legend: { orientation: "h", y: 1.16, x: 0, font: { size: 10 } },
    },
    PLOTLY_CONFIG
  );

  // Dual-Survivor Unicorn Table
  const dualBody = document.getElementById("dualSurvivorTableBody");
  dualBody.innerHTML = (data.dual_survivors || [])
    .map((r) => {
      const passedMoat = String(r["Passed Elite Moat Gate"]) === "YES";
      return `
        <tr onclick="openStockDeepDive('${r.Ticker}')" class="row-hover cursor-pointer transition">
          <td class="py-2 px-2 font-bold text-amber-300">${r.Ticker}</td>
          <td class="py-2 px-2 font-sans text-white font-medium">${r["Company Name"]}</td>
          <td class="py-2 px-2 font-sans text-slate-400 text-[11px]">${r.Sector} • ${r["Market Cap Tier"]}</td>
          <td class="py-2 px-2 text-center">
            <span class="px-2 py-0.5 rounded text-[10px] border ${passedMoat ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-slate-800 text-slate-400 border-slate-700"}">
              ${passedMoat ? "ELITE MOAT ★" : "Screener Pass"}
            </span>
          </td>
          <td class="py-2 px-2 text-right text-slate-200">$${fmtNum(r["Current Price ($)"])}</td>
          <td class="py-2 px-2 text-right text-amber-300 font-semibold">$${fmtNum(r["3Y Inflection Target ($)"])}</td>
          <td class="py-2 px-2 text-right text-amber-400 font-bold">${fmtSigned(r["3Y Moonshot Return (%)"])}</td>
          <td class="py-2 px-2 text-right text-emerald-300 font-semibold">$${fmtNum(r["5Y Compounder Target ($)"])}</td>
          <td class="py-2 px-2 text-right text-emerald-400 font-bold">${fmtSigned(r["5Y Compounder CAGR (%)"])}/yr</td>
          <td class="py-2 px-2 text-right text-cyan-300 font-semibold">${fmtNum(r["Compounder Moat Score (100)"], 1)}</td>
          <td class="py-2 px-2 text-right text-amber-300 font-semibold">${fmtNum(r["Moonshot Inflection Score (100)"], 1)}</td>
          <td class="py-2 px-2 text-right text-slate-200">${fmtSigned(r["Revenue Growth (%)"])}</td>
          <td class="py-2 px-2 text-right text-slate-200">${fmtNum(r["ROIC (%)"], 1)}%</td>
          <td class="py-2 px-2 text-right ${Number(r["3Y Share Dilution CAGR (%)"]) <= 0 ? "text-emerald-400" : "text-slate-300"}">${fmtSigned(r["3Y Share Dilution CAGR (%)"], 2)}</td>
        </tr>
      `;
    })
    .join("");

  // Sector Comparison Chart
  const topSectors = (data.sector_summary || []).slice(0, 10);
  Plotly.newPlot(
    "overviewSectorChart",
    [
      {
        name: "Elite Moat (136)",
        y: topSectors.map((s) => s.sector),
        x: topSectors.map((s) => s.elite_moat_survivors),
        type: "bar",
        orientation: "h",
        marker: { color: "#10b981" },
      },
      {
        name: "Compounder Shortlist (204)",
        y: topSectors.map((s) => s.sector),
        x: topSectors.map((s) => s.compounder_shortlist),
        type: "bar",
        orientation: "h",
        marker: { color: "#38bdf8" },
      },
      {
        name: "Asymmetric Moonshots (60)",
        y: topSectors.map((s) => s.sector),
        x: topSectors.map((s) => s.asymmetric_moonshots),
        type: "bar",
        orientation: "h",
        marker: { color: "#f59e0b" },
      },
    ],
    {
      ...PLOTLY_DARK_LAYOUT,
      barmode: "group",
      margin: { l: 135, r: 16, t: 24, b: 34 },
      yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, autorange: "reversed" },
      legend: { orientation: "h", y: 1.12, x: 0, font: { size: 10 } },
    },
    PLOTLY_CONFIG
  );

  // Top 20 Elite Moat Table
  document.getElementById("overviewTopMoatBody").innerHTML = (data.top_compounders || [])
    .map(
      (r) => `
      <tr onclick="openStockDeepDive('${r.Ticker}')" class="row-hover cursor-pointer transition">
        <td class="py-2 px-2 font-bold text-emerald-400">${r.Ticker}</td>
        <td class="py-2 px-2 font-sans text-white truncate max-w-[190px]">${r["Company Name"]}</td>
        <td class="py-2 px-2 text-slate-400 text-[11px]">${r["Market Cap Tier"]}</td>
        <td class="py-2 px-2 text-right text-slate-200">$${fmtNum(r["Current Price ($)"])}</td>
        <td class="py-2 px-2 text-right text-cyan-300 font-semibold">$${fmtNum(r["5Y Target Price ($)"])}</td>
        <td class="py-2 px-2 text-right text-emerald-400 font-bold">${fmtSigned(r["5Y Projected CAGR (%)"])}/yr</td>
        <td class="py-2 px-2 text-right text-cyan-400 font-bold">${fmtNum(r["Total Moat Score (100)"], 1)}</td>
        <td class="py-2 px-2 text-right ${Number(r["3Y Share Dilution CAGR (%)"]) <= 0 ? "text-emerald-400" : "text-slate-300"}">${fmtSigned(r["3Y Share Dilution CAGR (%)"], 2)}</td>
      </tr>
    `
    )
    .join("");

  renderOverviewScatter();
}

function renderOverviewScatter() {
  if (!window.overviewData) return;
  const colorMode = document.getElementById("overviewScatterColorMode").value;
  const includeMoon = document.getElementById("overviewIncludeMoonshots").checked;

  let pts = window.overviewData.scatter_points || [];
  if (!includeMoon) {
    pts = pts.filter((p) => p.category !== "Asymmetric Moonshot");
  }

  const groups = {};
  pts.forEach((p) => {
    const key = p[colorMode] || "Other";
    if (!groups[key]) groups[key] = [];
    groups[key].push(p);
  });

  const palette = {
    "Dual-Survivor Unicorn": "#fbbf24",
    "Elite Moat Compounder": "#10b981",
    "Mega-Cap Anchor ($1T+)": "#818cf8",
    "Compounder Shortlist": "#38bdf8",
    "Asymmetric Moonshot": "#f43f5e",
  };

  const traces = Object.entries(groups).map(([grpName, list]) => ({
    name: `${grpName} (${list.length})`,
    x: list.map((d) => d.moat_score),
    y: list.map((d) => d.cagr_5y_pct),
    text: list.map(
      (d) =>
        `<b>${d.ticker}</b> — ${d.company_name}<br>` +
        `Category: ${d.category}<br>` +
        `Mkt Cap: $${fmtNum(d.market_cap_b, 2)}B (${d.market_cap_tier})<br>` +
        `Score: ${fmtNum(d.moat_score, 1)} | 5Y CAGR: ${fmtSigned(d.cagr_5y_pct, 2)}/yr<br>` +
        `Price: $${fmtNum(d.current_price)} → 5Y Target: $${fmtNum(d.target_price_5y || d.target_price_3y)}<br>` +
        `ROIC: ${fmtNum(d.roic_pct, 1)}% | Fwd P/E: ${fmtNum(d.forward_pe, 1)}x`
    ),
    customdata: list.map((d) => d.ticker),
    hoverinfo: "text",
    mode: "markers+text",
    textposition: "top center",
    textfont: { size: 9, color: "#94a3b8" },
    marker: {
      size: list.map((d) => Math.max(9, Math.min(34, Math.log10(Math.max(0.3, d.market_cap_b) * 10) * 9))),
      color: palette[grpName] || undefined,
      opacity: 0.86,
      line: { width: 1, color: "#0f172a" },
    },
  }));

  // Render labels only on notable outliers to keep plot crisp
  traces.forEach((tr, i) => {
    const grpList = Object.values(groups)[i];
    tr.text = grpList.map((d) =>
      d.category === "Dual-Survivor Unicorn" || d.category === "Mega-Cap Anchor ($1T+)" || d.cagr_5y_pct >= 24 || d.moat_score >= 92
        ? d.ticker
        : ""
    );
    tr.hovertext = grpList.map(
      (d) =>
        `<b>${d.ticker} — ${d.company_name}</b><br>` +
        `${d.category} • ${d.sector}<br>` +
        `Market Cap: $${fmtNum(d.market_cap_b, 2)}B (${d.market_cap_tier})<br>` +
        `Moat/Inflection Score: <b>${fmtNum(d.moat_score, 1)}</b><br>` +
        `Projected Annualized Return: <b>${fmtSigned(d.cagr_5y_pct, 2)}/yr</b><br>` +
        `ROIC: ${fmtNum(d.roic_pct, 1)}% | Rev Growth: ${fmtSigned(d.revenue_growth_pct, 1)} | Fwd P/E: ${fmtNum(d.forward_pe, 1)}x`
    );
    tr.hoverinfo = "text";
  });

  Plotly.newPlot(
    "overviewScatterChart",
    traces,
    {
      ...PLOTLY_DARK_LAYOUT,
      xaxis: { ...PLOTLY_DARK_LAYOUT.xaxis, title: "Qualitative Moat / Inflection Score (0–100)" },
      yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, title: "Projected Annualized Return CAGR (%)" },
      legend: { orientation: "h", y: 1.11, x: 0, font: { size: 10 } },
      shapes: [
        { type: "line", x0: 70, x1: 70, y0: -15, y1: 60, line: { color: "#10b981", width: 1, dash: "dot" } },
        { type: "line", x0: 40, x1: 100, y0: 8, y1: 8, line: { color: "#38bdf8", width: 1, dash: "dot" } },
      ],
    },
    PLOTLY_CONFIG
  );

  const chartEl = document.getElementById("overviewScatterChart");
  chartEl.on("plotly_click", (ev) => {
    const pt = ev?.points?.[0];
    if (pt && pt.customdata) {
      openStockDeepDive(pt.customdata);
    }
  });
}

// ============================================================================
// TAB 2: LIVE CUSTOM SCREENER SANDBOX ("WHAT-IF FILTER LAB")
// ============================================================================
function applyScreenerPreset(preset) {
  const setChk = (id, v) => (document.getElementById(id).checked = v);
  const setVal = (id, v, lblId = null, suffix = "") => {
    const el = document.getElementById(id);
    if (el) el.value = v;
    if (lblId && document.getElementById(lblId)) {
      document.getElementById(lblId).textContent = `${v}${suffix}`;
    }
  };

  if (preset === "compounder") {
    setChk("scr_enable_mcap", true);
    setVal("scr_min_mcap", 500);
    setVal("scr_max_mcap", "");
    setChk("scr_enable_fcf", true);
    setChk("scr_enable_roic", true);
    setVal("scr_min_roic", 10, "scr_roic_val", ".0%");
    setChk("scr_enable_opm", true);
    setVal("scr_min_opm", 10, "scr_opm_val", ".0%");
    setChk("scr_enable_gm", false);
    setChk("scr_enable_revg", true);
    setVal("scr_min_revg", 5, "scr_revg_val", ".0%");
    setVal("scr_max_revg", "");
    setChk("scr_enable_epsg", true);
    setVal("scr_min_epsg", 5, "scr_epsg_val", ".0%");
    setChk("scr_enable_accel", false);
    setChk("scr_enable_cr", true);
    setVal("scr_min_cr", 0.5, "scr_cr_val", "0x");
    setChk("scr_enable_dte", true);
    setVal("scr_max_dte", 2.0, "scr_dte_val", "0x");
    setChk("scr_allow_null_dte", false);
    setChk("scr_enable_pe", true);
    setVal("scr_min_pe", 5.0);
    setVal("scr_max_pe", "");
    setChk("scr_enable_beta", true);
    setVal("scr_min_beta", 0.7, "scr_beta_val", "");
  } else if (preset === "moonshot") {
    setChk("scr_enable_mcap", true);
    setVal("scr_min_mcap", 300);
    setVal("scr_max_mcap", 10000);
    setChk("scr_enable_fcf", false);
    setChk("scr_enable_roic", false);
    setChk("scr_enable_opm", true);
    setVal("scr_min_opm", -15, "scr_opm_val", ".0%");
    setChk("scr_enable_gm", false);
    setChk("scr_enable_revg", true);
    setVal("scr_min_revg", 25, "scr_revg_val", ".0%");
    setVal("scr_max_revg", 300);
    setChk("scr_enable_epsg", false);
    setChk("scr_enable_accel", true);
    setVal("scr_min_accel", 30, "scr_accel_val", "%");
    setChk("scr_enable_cr", true);
    setVal("scr_min_cr", 1.5, "scr_cr_val", "0x");
    setChk("scr_enable_dte", true);
    setVal("scr_max_dte", 1.0, "scr_dte_val", "0x");
    setChk("scr_allow_null_dte", true);
    setChk("scr_enable_pe", true);
    setVal("scr_min_pe", 0.1);
    setVal("scr_max_pe", "");
    setChk("scr_enable_beta", true);
    setVal("scr_min_beta", 1.15, "scr_beta_val", "");
  } else if (preset === "rule40") {
    setChk("scr_enable_mcap", true);
    setVal("scr_min_mcap", 1000);
    setVal("scr_max_mcap", "");
    setChk("scr_enable_fcf", true);
    setChk("scr_enable_roic", true);
    setVal("scr_min_roic", 12, "scr_roic_val", ".0%");
    setChk("scr_enable_opm", true);
    setVal("scr_min_opm", 18, "scr_opm_val", ".0%");
    setChk("scr_enable_gm", true);
    setVal("scr_min_gm", 50, "scr_gm_val", ".0%");
    setChk("scr_enable_revg", true);
    setVal("scr_min_revg", 20, "scr_revg_val", ".0%");
    setChk("scr_enable_epsg", false);
    setChk("scr_enable_accel", false);
    setChk("scr_enable_cr", false);
    setChk("scr_enable_dte", true);
    setVal("scr_max_dte", 1.5, "scr_dte_val", "0x");
    setChk("scr_enable_pe", true);
    setVal("scr_min_pe", 5.0);
    setChk("scr_enable_beta", false);
  } else if (preset === "deepvalue") {
    setChk("scr_enable_mcap", true);
    setVal("scr_min_mcap", 500);
    setVal("scr_max_mcap", "");
    setChk("scr_enable_fcf", true);
    setChk("scr_enable_roic", true);
    setVal("scr_min_roic", 15, "scr_roic_val", ".0%");
    setChk("scr_enable_opm", true);
    setVal("scr_min_opm", 12, "scr_opm_val", ".0%");
    setChk("scr_enable_gm", false);
    setChk("scr_enable_revg", true);
    setVal("scr_min_revg", 3, "scr_revg_val", ".0%");
    setChk("scr_enable_epsg", false);
    setChk("scr_enable_accel", false);
    setChk("scr_enable_cr", false);
    setChk("scr_enable_dte", true);
    setVal("scr_max_dte", 1.5, "scr_dte_val", "0x");
    setChk("scr_enable_pe", true);
    setVal("scr_min_pe", 4.0);
    setVal("scr_max_pe", 15.0);
    setChk("scr_enable_beta", false);
  } else if (preset === "unfiltered") {
    [
      "scr_enable_mcap",
      "scr_enable_fcf",
      "scr_enable_roic",
      "scr_enable_opm",
      "scr_enable_gm",
      "scr_enable_revg",
      "scr_enable_epsg",
      "scr_enable_accel",
      "scr_enable_cr",
      "scr_enable_dte",
      "scr_enable_pe",
      "scr_enable_beta",
    ].forEach((id) => setChk(id, false));
  }

  runCustomScreener();
}

async function runCustomScreener() {
  const minMcap = parseFloat(document.getElementById("scr_min_mcap").value);
  const maxMcap = parseFloat(document.getElementById("scr_max_mcap").value);
  const maxRevg = parseFloat(document.getElementById("scr_max_revg").value);
  const minPe = parseFloat(document.getElementById("scr_min_pe").value);
  const maxPe = parseFloat(document.getElementById("scr_max_pe").value);
  const sortBy = document.getElementById("scr_sort_by").value;

  const payload = {
    active_only: true,
    enable_market_cap: document.getElementById("scr_enable_mcap").checked,
    min_market_cap_m: Number.isNaN(minMcap) ? null : minMcap,
    max_market_cap_m: Number.isNaN(maxMcap) ? null : maxMcap,
    enable_fcf_positive: document.getElementById("scr_enable_fcf").checked,
    enable_roic: document.getElementById("scr_enable_roic").checked,
    min_roic_pct: parseFloat(document.getElementById("scr_min_roic").value) || 0,
    enable_operating_margin: document.getElementById("scr_enable_opm").checked,
    min_operating_margin_pct: parseFloat(document.getElementById("scr_min_opm").value) || 0,
    enable_gross_margin: document.getElementById("scr_enable_gm").checked,
    min_gross_margin_pct: parseFloat(document.getElementById("scr_min_gm").value) || 0,
    enable_revenue_growth: document.getElementById("scr_enable_revg").checked,
    min_revenue_growth_pct: parseFloat(document.getElementById("scr_min_revg").value) || 0,
    max_revenue_growth_pct: Number.isNaN(maxRevg) ? null : maxRevg,
    enable_earnings_growth: document.getElementById("scr_enable_epsg").checked,
    min_earnings_growth_pct: parseFloat(document.getElementById("scr_min_epsg").value) || 0,
    enable_accel_rule: document.getElementById("scr_enable_accel").checked,
    min_accel_pct: parseFloat(document.getElementById("scr_min_accel").value) || 30,
    enable_current_ratio: document.getElementById("scr_enable_cr").checked,
    min_current_ratio: parseFloat(document.getElementById("scr_min_cr").value) || 0,
    enable_debt_to_equity: document.getElementById("scr_enable_dte").checked,
    max_debt_to_equity: parseFloat(document.getElementById("scr_max_dte").value) || 2.0,
    allow_null_debt: document.getElementById("scr_allow_null_dte").checked,
    enable_forward_pe: document.getElementById("scr_enable_pe").checked,
    min_forward_pe: Number.isNaN(minPe) ? 0 : minPe,
    max_forward_pe: Number.isNaN(maxPe) ? null : maxPe,
    enable_beta: document.getElementById("scr_enable_beta").checked,
    min_beta: parseFloat(document.getElementById("scr_min_beta").value) || 0,
    search_query: document.getElementById("scr_search").value || null,
    sort_by: sortBy,
    sort_desc: sortBy !== "forward_pe",
    limit: 500,
  };

  const res = await fetch("/api/screener", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  window.lastScreenerResults = data.results || [];

  const st = data.summary_stats || {};
  document.getElementById("screenerResultCount").textContent = st.total_survivors?.toLocaleString() || "0";
  document.getElementById("screenerSummaryBadges").innerHTML = `
    <span class="px-2.5 py-1 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">Survivors: <b>${st.total_survivors}</b></span>
    <span class="px-2.5 py-1 rounded bg-slate-900 text-slate-300 border border-slate-800">Med ROIC: <b>${fmtNum(st.median_roic_pct, 1)}%</b></span>
    <span class="px-2.5 py-1 rounded bg-slate-900 text-slate-300 border border-slate-800">Med Fwd P/E: <b>${fmtNum(st.median_forward_pe, 1)}x</b></span>
    <span class="px-2.5 py-1 rounded bg-slate-900 text-slate-300 border border-slate-800">Med RevG: <b>${fmtSigned(st.median_rev_growth_pct, 1)}</b></span>
  `;

  // Funnel Chart
  const funnel = data.funnel || [];
  Plotly.newPlot(
    "screenerFunnelChart",
    [
      {
        x: funnel.map((f) => f.stage),
        y: funnel.map((f) => f.count),
        text: funnel.map((f, i) => (i === 0 ? `${f.count.toLocaleString()}` : `${f.count.toLocaleString()} (-${f.dropped.toLocaleString()})`)),
        textposition: "auto",
        type: "bar",
        marker: {
          color: funnel.map((_, idx) => (idx === funnel.length - 1 ? "#10b981" : "#38bdf8")),
        },
      },
    ],
    {
      ...PLOTLY_DARK_LAYOUT,
      margin: { l: 48, r: 16, t: 18, b: 68 },
      xaxis: { ...PLOTLY_DARK_LAYOUT.xaxis, tickangle: -20 },
      yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, title: "Surviving Tickers" },
    },
    PLOTLY_CONFIG
  );

  // Table Body
  document.getElementById("screenerTableBody").innerHTML = (data.results || [])
    .map(
      (r) => `
      <tr onclick="openStockDeepDive('${r.ticker}')" class="row-hover cursor-pointer transition">
        <td class="py-2 px-2 font-bold text-emerald-400">${r.ticker}</td>
        <td class="py-2 px-2 font-sans text-white truncate max-w-[200px]">${r.company_name || r.ticker}</td>
        <td class="py-2 px-2 font-sans text-slate-400 text-[11px]">${r.sector || "—"} • ${r.market_cap_tier}</td>
        <td class="py-2 px-2 text-center">
          <span class="px-2 py-0.5 rounded text-[10px] border ${badgeColorClass(r.pipeline_badge)}">${r.pipeline_badge}</span>
        </td>
        <td class="py-2 px-2 text-right text-slate-200">$${fmtNum(r.market_cap_b, 2)}B</td>
        <td class="py-2 px-2 text-right text-slate-200">$${fmtNum(r.current_price, 2)}</td>
        <td class="py-2 px-2 text-right text-slate-200">${fmtNum(r.forward_pe, 1)}x</td>
        <td class="py-2 px-2 text-right text-emerald-400 font-semibold">${fmtNum(r.roic_pct, 1)}%</td>
        <td class="py-2 px-2 text-right text-slate-200">${fmtNum(r.operating_margin_pct, 1)}%</td>
        <td class="py-2 px-2 text-right text-cyan-300 font-semibold">${fmtSigned(r.revenue_growth_pct, 1)}</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(r.current_ratio, 2)}x</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(r.debt_to_equity, 2)}x</td>
        <td class="py-2 px-2 text-right text-amber-300">
          ${r.moat_score ? `Moat ${fmtNum(r.moat_score, 0)}` : "—"}
          ${r.cagr_5y_pct !== null && r.cagr_5y_pct !== undefined ? ` / ${fmtSigned(r.cagr_5y_pct, 1)}` : ""}
        </td>
      </tr>
    `
    )
    .join("");
}

// ============================================================================
// TAB 3: 7-PILLAR QUALITATIVE MOAT STUDIO & EQUATION WEIGHTER
// ============================================================================
async function loadMoatStudioTab() {
  const res = await fetch("/api/moat-studio");
  const data = await res.json();
  window.moatStudioStocks = data.stocks || [];
  recomputeMoatStudio();

  // Populate Valuation Time-Machine quick-select dropdown with all 204 compounders
  const selectEl = document.getElementById("valTickerSelect");
  if (selectEl && window.moatStudioStocks.length) {
    const sorted = [...window.moatStudioStocks].sort((a, b) => String(a.Ticker).localeCompare(String(b.Ticker)));
    selectEl.innerHTML = sorted
      .map(
        (s) =>
          `<option value="${s.Ticker}" ${s.Ticker === "TSM" ? "selected" : ""}>${s.Ticker} — ${s["Company Name"]} (${s["Market Cap Tier"]})</option>`
      )
      .join("");
  }
}

function resetMoatWeights() {
  const defaults = [
    ["moat_p1_on", "moat_p1_w", 15],
    ["moat_p2_on", "moat_p2_w", 10],
    ["moat_p3_on", "moat_p3_w", 15],
    ["moat_p4_on", "moat_p4_w", 10],
    ["moat_p5_on", "moat_p5_w", 20],
    ["moat_p6_on", "moat_p6_w", 15],
    ["moat_p7_on", "moat_p7_w", 15],
  ];
  defaults.forEach(([chk, sld, w]) => {
    document.getElementById(chk).checked = true;
    document.getElementById(sld).value = w;
  });
  document.getElementById("moat_gate_min").value = 70;
  document.getElementById("moat_gate_dil").value = 3.5;
  document.getElementById("moat_gate_cagr").value = 8.0;
  document.getElementById("moat_blend_slider").value = 60;
  recomputeMoatStudio();
}

function recomputeMoatStudio() {
  const pConfig = [
    { key: "Pillar 1: Form 4 Insider Alignment (15)", maxOrig: 15, on: document.getElementById("moat_p1_on").checked, w: parseFloat(document.getElementById("moat_p1_w").value), lbl: "moat_p1_w_lbl" },
    { key: "Pillar 2: CEO Ownership & Alignment (10)", maxOrig: 10, on: document.getElementById("moat_p2_on").checked, w: parseFloat(document.getElementById("moat_p2_w").value), lbl: "moat_p2_w_lbl" },
    { key: "Pillar 3: Capital Allocation & ROIC (15)", maxOrig: 15, on: document.getElementById("moat_p3_on").checked, w: parseFloat(document.getElementById("moat_p3_w").value), lbl: "moat_p3_w_lbl" },
    { key: "Pillar 4: Culture & Leadership (10)", maxOrig: 10, on: document.getElementById("moat_p4_on").checked, w: parseFloat(document.getElementById("moat_p4_w").value), lbl: "moat_p4_w_lbl" },
    { key: "Pillar 5: Pricing Power (20)", maxOrig: 20, on: document.getElementById("moat_p5_on").checked, w: parseFloat(document.getElementById("moat_p5_w").value), lbl: "moat_p5_w_lbl" },
    { key: "Pillar 6: SG&A Brand Leverage (15)", maxOrig: 15, on: document.getElementById("moat_p6_on").checked, w: parseFloat(document.getElementById("moat_p6_w").value), lbl: "moat_p6_w_lbl" },
    { key: "Pillar 7: Brand Recognition Index (15)", maxOrig: 15, on: document.getElementById("moat_p7_on").checked, w: parseFloat(document.getElementById("moat_p7_w").value), lbl: "moat_p7_w_lbl" },
  ];

  let activeWeightSum = 0;
  pConfig.forEach((p) => {
    document.getElementById(p.lbl).textContent = p.on ? `${p.w} pts` : "OFF";
    if (p.on) activeWeightSum += p.w;
  });

  const minMoat = parseFloat(document.getElementById("moat_gate_min").value);
  const maxDil = parseFloat(document.getElementById("moat_gate_dil").value);
  const minCagr = parseFloat(document.getElementById("moat_gate_cagr").value);
  const moatBlendPct = parseFloat(document.getElementById("moat_blend_slider").value);

  document.getElementById("moat_gate_min_lbl").textContent = minMoat.toFixed(1);
  document.getElementById("moat_gate_dil_lbl").textContent = `${maxDil.toFixed(1)}%`;
  document.getElementById("moat_gate_cagr_lbl").textContent = `${minCagr.toFixed(1)}%`;
  document.getElementById("moat_blend_lbl").textContent = `${moatBlendPct}% Moat / ${100 - moatBlendPct}% CAGR`;

  const tierFilter = document.getElementById("moatTierFilter").value;
  const q = (document.getElementById("moatSearchInput").value || "").trim().toLowerCase();

  const wMoat = moatBlendPct / 100.0;
  const wCagr = 1.0 - wMoat;

  const computed = (window.moatStudioStocks || []).map((s) => {
    let weightedEarned = 0;
    pConfig.forEach((p) => {
      if (p.on && p.w > 0) {
        const rawScore = Number(s[p.key] || 0);
        const pctOfPillar = Math.min(1.0, Math.max(0.0, rawScore / p.maxOrig));
        weightedEarned += pctOfPillar * p.w;
      }
    });
    const customMoat = activeWeightSum > 0 ? (weightedEarned / activeWeightSum) * 100.0 : 0.0;
    const cagr5y = Number(s["5Y Projected CAGR (%)"] || 0);
    // Normalize 5Y CAGR onto a 0-100 scale (where 25% CAGR = 100 pts) for conviction blend
    const cagrScore100 = Math.min(100, Math.max(0, (cagr5y / 25.0) * 100.0));
    const convictionScore = wMoat * customMoat + wCagr * cagrScore100;

    return {
      ...s,
      Custom_Moat_Score: Number(customMoat.toFixed(1)),
      Conviction_Score: Number(convictionScore.toFixed(1)),
    };
  });

  const survivors = computed
    .filter((s) => {
      if (s.Custom_Moat_Score < minMoat) return false;
      if (Number(s["3Y Share Dilution CAGR (%)"] || 0) > maxDil) return false;
      if (Number(s["5Y Projected CAGR (%)"] || 0) < minCagr) return false;
      if (tierFilter !== "ALL" && s["Market Cap Tier"] !== tierFilter) return false;
      if (q && !String(s.Ticker).toLowerCase().includes(q) && !String(s["Company Name"]).toLowerCase().includes(q)) return false;
      return true;
    })
    .sort((a, b) => b.Conviction_Score - a.Conviction_Score || b.Custom_Moat_Score - a.Custom_Moat_Score);

  window.filteredMoatStocks = survivors;
  document.getElementById("moatSurvivorCount").textContent = survivors.length;

  document.getElementById("moatStudioTableBody").innerHTML = survivors
    .map(
      (s, idx) => `
      <tr onclick="openStockDeepDive('${s.Ticker}')" class="row-hover cursor-pointer transition">
        <td class="py-2 px-2 text-slate-500">#${idx + 1}</td>
        <td class="py-2 px-2 font-bold text-emerald-400">
          ${s.Ticker}
          ${s.in_dual_survivor ? '<span class="ml-1 text-[10px] text-amber-300">★</span>' : ""}
        </td>
        <td class="py-2 px-2 font-sans text-white truncate max-w-[190px]">${s["Company Name"]}</td>
        <td class="py-2 px-2 text-slate-400 text-[11px]">${s["Market Cap Tier"]}</td>
        <td class="py-2 px-2 text-right font-bold text-amber-300">${fmtNum(s.Conviction_Score, 1)}</td>
        <td class="py-2 px-2 text-right font-bold text-emerald-400">${fmtNum(s.Custom_Moat_Score, 1)}</td>
        <td class="py-2 px-2 text-right text-slate-400">${fmtNum(s["Total Moat Score (100)"], 1)}</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(s["Pillar 1: Form 4 Insider Alignment (15)"], 1)}</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(s["Pillar 2: CEO Ownership & Alignment (10)"], 1)}</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(s["Pillar 3: Capital Allocation & ROIC (15)"], 1)}</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(s["Pillar 4: Culture & Leadership (10)"], 1)}</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(s["Pillar 5: Pricing Power (20)"], 1)}</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(s["Pillar 6: SG&A Brand Leverage (15)"], 1)}</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(s["Pillar 7: Brand Recognition Index (15)"], 1)}</td>
        <td class="py-2 px-2 text-right text-slate-200">$${fmtNum(s["Current Price ($)"])}</td>
        <td class="py-2 px-2 text-right text-cyan-300 font-semibold">$${fmtNum(s["5Y Target Price ($)"])}</td>
        <td class="py-2 px-2 text-right text-emerald-400 font-bold">${fmtSigned(s["5Y Projected CAGR (%)"])}/yr</td>
        <td class="py-2 px-2 text-right ${Number(s["3Y Share Dilution CAGR (%)"]) <= 0 ? "text-emerald-400" : "text-slate-300"}">${fmtSigned(s["3Y Share Dilution CAGR (%)"], 2)}</td>
      </tr>
    `
    )
    .join("");
}

// ============================================================================
// TAB 4: 15-YEAR VALUATION TIME-MACHINE & 4-METHOD EQUATION BUILDER
// ============================================================================
async function loadCompanyDeepDive(ticker = "TSM") {
  try {
    const res = await fetch(`/api/company/${encodeURIComponent(ticker)}`);
    if (!res.ok) throw new Error(`Ticker ${ticker} not found`);
    const data = await res.json();
    window.currentDeepDiveData = data;
    window.currentDeepDiveTicker = data.ticker;

    const sel = document.getElementById("valTickerSelect");
    if (sel) {
      const exists = Array.from(sel.options).some((o) => o.value === data.ticker);
      if (!exists) {
        const opt = document.createElement("option");
        opt.value = data.ticker;
        opt.textContent = `${data.ticker} — ${data.overview.company_name} (${data.overview.market_cap_tier})`;
        sel.prepend(opt);
      }
      sel.value = data.ticker;
    }

    resetValuationSimulation();
  } catch (err) {
    console.error("Error loading company deep dive:", err);
  }
}

function resetValuationSimulation() {
  if (!window.currentDeepDiveData) return;
  const eq = window.currentDeepDiveData.equation_defaults || {};

  document.getElementById("val_m1_on").checked = true;
  document.getElementById("val_m2_on").checked = true;
  document.getElementById("val_m3_on").checked = true;
  document.getElementById("val_m4_on").checked = true;
  document.getElementById("val_dilution_on").checked = true;

  document.getElementById("val_m1_rate").value = eq.m1_eps_cagr_pct ?? 10;
  document.getElementById("val_m2_rate").value = eq.m2_rev_cagr_pct ?? 10;
  document.getElementById("val_m2_margin").value = eq.m2_net_margin_pct ?? 15;
  document.getElementById("val_m3_rate").value = eq.m3_yahoo_lt_pct ?? 12;
  document.getElementById("val_m4_rate").value = eq.m4_finviz_5y_pct ?? 12;
  document.getElementById("val_start_pe").value = eq.starting_pe_2027 ?? 20;
  document.getElementById("val_term_pe").value = eq.terminal_pe_2031 ?? 18;
  document.getElementById("val_dilution_rate").value = eq.share_dilution_cagr_pct ?? 0;

  recomputeValuationTimeline();
}

function compoundedGrowthFactor(annualRateDecimal, steps) {
  if (steps <= 0) return 1.0;
  let factor = 1.0;
  for (let s = 1; s <= steps; s++) {
    let stepR = annualRateDecimal;
    if (annualRateDecimal > 0.18) {
      stepR = 0.18 + (annualRateDecimal - 0.18) * Math.pow(0.88, s - 1);
    }
    factor *= 1.0 + stepR;
  }
  return factor;
}

function recomputeValuationTimeline() {
  const data = window.currentDeepDiveData;
  if (!data) return;

  const ov = data.overview || {};
  const eq = data.equation_defaults || {};
  const mp = data.moat_pillars || {};

  const m1On = document.getElementById("val_m1_on").checked;
  const m2On = document.getElementById("val_m2_on").checked;
  const m3On = document.getElementById("val_m3_on").checked;
  const m4On = document.getElementById("val_m4_on").checked;
  const dilOn = document.getElementById("val_dilution_on").checked;

  const m1Rate = parseFloat(document.getElementById("val_m1_rate").value) || 0;
  const m2Rate = parseFloat(document.getElementById("val_m2_rate").value) || 0;
  const m2Margin = parseFloat(document.getElementById("val_m2_margin").value) || 15;
  const m3Rate = parseFloat(document.getElementById("val_m3_rate").value) || 0;
  const m4Rate = parseFloat(document.getElementById("val_m4_rate").value) || 0;
  const startPe = parseFloat(document.getElementById("val_start_pe").value) || 18;
  const termPe = parseFloat(document.getElementById("val_term_pe").value) || 16;
  const dilRate = dilOn ? parseFloat(document.getElementById("val_dilution_rate").value) || 0 : 0.0;

  document.getElementById("val_m1_rate_lbl").textContent = m1On ? `${m1Rate.toFixed(1)}%/yr` : "EXCLUDED";
  document.getElementById("val_m2_rate_lbl").textContent = m2On ? `${m2Rate.toFixed(1)}%/yr` : "EXCLUDED";
  document.getElementById("val_m2_margin_lbl").textContent = `${m2Margin.toFixed(1)}%`;
  document.getElementById("val_m3_rate_lbl").textContent = m3On ? `${m3Rate.toFixed(1)}%/yr` : "EXCLUDED";
  document.getElementById("val_m4_rate_lbl").textContent = m4On ? `${m4Rate.toFixed(1)}%/yr` : "EXCLUDED";
  document.getElementById("val_start_pe_lbl").textContent = `${startPe.toFixed(1)}x`;
  document.getElementById("val_term_pe_lbl").textContent = `${termPe.toFixed(1)}x`;
  document.getElementById("val_dilution_lbl").textContent = dilOn ? `${fmtSigned(dilRate, 2)}/yr` : "0.0% (Ignored)";

  const currPrice = Number(eq.current_price || ov.current_price || 50);
  const baseEps27 = Number(eq.base_2027_eps || 3.0);
  const baseRev27 = Number(eq.base_2027_rev_m || 1000.0);
  const baseSharesM = Number(eq.base_shares_m || 100.0);

  // Check if user kept exact defaults so 2027 uses the exact baseline target_2027_price
  const isDefaultStartPe = Math.abs(startPe - Number(eq.starting_pe_2027 || startPe)) < 0.05;
  const price2027 = isDefaultStartPe ? Number(eq.target_2027_price || baseEps27 * startPe) : Number((baseEps27 * startPe).toFixed(2));

  // Separate historical/current rows (<= 2026) from forecast years (2027..2031)
  const rawTimeline = data.timeline || [];
  const histAndCurr = rawTimeline
    .filter((r) => Number(r.Year) <= 2026)
    .sort((a, b) => Number(a.Year) - Number(b.Year));

  // Simulate 2027..2031 dynamically
  const forecastRows = [];
  let prevBlendedPrice = price2027;
  let prevMethodPrices = [price2027, price2027, price2027, price2027];

  for (let yr = 2027; yr <= 2031; yr++) {
    const k = yr - 2027; // 0..4
    const peK = k === 0 ? startPe : Math.max(termPe, startPe - (k / 4.0) * (startPe - termPe));
    const projShares = baseSharesM * Math.pow(1.0 + dilRate / 100.0, k);

    // Diluted EPS under M1, M3, M4 also adjusts if user toggles dilution drift relative to baseline!
    const epsDilutionFactor = dilOn ? Math.pow(1.0 / (1.0 + dilRate / 100.0), k) : 1.0;

    const epsM1 = k === 0 ? baseEps27 : baseEps27 * compoundedGrowthFactor(m1Rate / 100.0, k) * epsDilutionFactor;
    const pM1 = k === 0 ? price2027 : Math.max(0.01, epsM1 * peK);

    const revM2 = k === 0 ? baseRev27 : baseRev27 * compoundedGrowthFactor(m2Rate / 100.0, k);
    const niM2 = revM2 * (m2Margin / 100.0);
    const epsM2 = k === 0 ? baseEps27 : projShares > 0 ? niM2 / projShares : baseEps27;
    const pM2 = k === 0 ? price2027 : Math.max(0.01, epsM2 * peK);

    const epsM3 = k === 0 ? baseEps27 : baseEps27 * compoundedGrowthFactor(m3Rate / 100.0, k) * epsDilutionFactor;
    const pM3 = k === 0 ? price2027 : Math.max(0.01, epsM3 * peK);

    const epsM4 = k === 0 ? baseEps27 : baseEps27 * compoundedGrowthFactor(m4Rate / 100.0, k) * epsDilutionFactor;
    const pM4 = k === 0 ? price2027 : Math.max(0.01, epsM4 * peK);

    const activePrices = [];
    const activePrev = [];
    if (m1On) { activePrices.push(pM1); activePrev.push(prevMethodPrices[0]); }
    if (m2On) { activePrices.push(pM2); activePrev.push(prevMethodPrices[1]); }
    if (m3On) { activePrices.push(pM3); activePrev.push(prevMethodPrices[2]); }
    if (m4On) { activePrices.push(pM4); activePrev.push(prevMethodPrices[3]); }

    let blendedPrice = price2027;
    if (k === 0) {
      blendedPrice = price2027;
    } else if (activePrices.length === 0) {
      blendedPrice = prevBlendedPrice;
    } else if (k === 1) {
      const sorted = [...activePrices].sort((a, b) => a - b);
      const mid = Math.floor(sorted.length / 2);
      blendedPrice = sorted.length % 2 !== 0 ? sorted[mid] : 0.5 * (sorted[mid - 1] + sorted[mid]);
    } else {
      const stepGrowths = activePrices.map((pCurr, idx) => {
        const pPrev = activePrev[idx];
        return pPrev > 0 ? (pCurr - pPrev) / pPrev : 0.08;
      });
      stepGrowths.sort((a, b) => a - b);
      const mid = Math.floor(stepGrowths.length / 2);
      const medG = stepGrowths.length % 2 !== 0 ? stepGrowths[mid] : 0.5 * (stepGrowths[mid - 1] + stepGrowths[mid]);
      blendedPrice = prevBlendedPrice * (1.0 + medG);
    }

    prevBlendedPrice = blendedPrice;
    prevMethodPrices = [pM1, pM2, pM3, pM4];

    const blendedEps = peK > 0 ? blendedPrice / peK : epsM1;
    const blendedNi = blendedEps * projShares;

    forecastRows.push({
      Ticker: data.ticker,
      Year: yr,
      "Period Type": "Projected",
      "Price ($)": Number(blendedPrice.toFixed(2)),
      "Target Price ($)": Number(blendedPrice.toFixed(2)),
      "Target P/E Multiple": Number(peK.toFixed(2)),
      "P/E Ratio": Number(peK.toFixed(2)),
      "M1: Projected Price ($)": Number(pM1.toFixed(2)),
      "M2: Projected Price ($)": Number(pM2.toFixed(2)),
      "M3: Projected Price ($)": Number(pM3.toFixed(2)),
      "M4: Projected Price ($)": Number(pM4.toFixed(2)),
      "Revenue ($M)": Number(revM2.toFixed(2)),
      "Net Income ($M)": Number(blendedNi.toFixed(2)),
      "Net Profit Margin (%)": Number(m2Margin.toFixed(2)),
      "Diluted EPS ($)": Number(blendedEps.toFixed(2)),
      "Shares Outstanding (M)": Number(projShares.toFixed(2)),
    });
  }

  const target3Y = forecastRows.find((r) => r.Year === 2029)?.["Target Price ($)"] || price2027;
  const target5Y = forecastRows.find((r) => r.Year === 2031)?.["Target Price ($)"] || price2027;
  const return3YPct = currPrice > 0 ? ((target3Y - currPrice) / currPrice) * 100.0 : 0;
  const return5YPct = currPrice > 0 ? ((target5Y - currPrice) / currPrice) * 100.0 : 0;
  const cagr5YPct = currPrice > 0 && target5Y > 0 ? (Math.pow(target5Y / currPrice, 1.0 / 5.0) - 1.0) * 100.0 : 0;

  // Render Company Header & Simulated Target KPI Strip
  document.getElementById("valCompanyHeader").innerHTML = `
    <div>
      <div class="flex items-center gap-2">
        <span class="text-lg font-bold font-mono text-emerald-400">${data.ticker}</span>
        <span class="text-sm font-bold text-white">${ov.company_name || data.ticker}</span>
        <span class="px-2 py-0.5 text-[10px] font-mono rounded border bg-slate-800 text-slate-300 border-slate-700">${ov.market_cap_tier}</span>
      </div>
      <div class="text-xs text-slate-400 font-mono">
        ${ov.sector || "—"} • ${ov.industry || "—"} • Mkt Cap: $${fmtNum(ov.market_cap_b, 2)}B • ROIC: ${fmtNum(ov.roic_pct, 1)}% • Fwd P/E: ${fmtNum(ov.forward_pe, 1)}x
      </div>
    </div>
  `;

  document.getElementById("valTargetKpiStrip").innerHTML = `
    <div class="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800">
      <span class="text-[10px] text-slate-400 block">Current Price</span>
      <span class="text-sm font-bold text-white">$${fmtNum(currPrice, 2)}</span>
    </div>
    <div class="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800">
      <span class="text-[10px] text-slate-400 block">Simulated 3Y Target (2029)</span>
      <span class="text-sm font-bold text-cyan-300">$${fmtNum(target3Y, 2)} <span class="text-xs">(${fmtSigned(return3YPct, 1)})</span></span>
    </div>
    <div class="px-3 py-1.5 rounded-lg bg-emerald-500/15 border border-emerald-500/40">
      <span class="text-[10px] text-emerald-300 block">Simulated 5Y Target (2031)</span>
      <span class="text-sm font-bold text-emerald-400">$${fmtNum(target5Y, 2)} <span class="text-xs">(${fmtSigned(return5YPct, 1)})</span></span>
    </div>
    <div class="px-3 py-1.5 rounded-lg bg-indigo-500/15 border border-indigo-500/40">
      <span class="text-[10px] text-indigo-300 block">Simulated 5Y CAGR</span>
      <span class="text-sm font-bold text-indigo-300">${fmtSigned(cagr5YPct, 2)}/yr</span>
    </div>
    <div class="px-3 py-1.5 rounded-lg bg-amber-500/15 border border-amber-500/40">
      <span class="text-[10px] text-amber-300 block">Total Moat Score</span>
      <span class="text-sm font-bold text-amber-300">${fmtNum(mp["Total Moat Score (100)"], 1)} / 100</span>
    </div>
  `;

  // Build 15-Year Fan Chart (2016..2031)
  const histPlotRows = histAndCurr.filter((r) => r["Period Type"] === "Historical" && r["Price ($)"] !== null);
  const histYears = histPlotRows.map((r) => r.Year);
  const histPrices = histPlotRows.map((r) => r["Price ($)"]);
  // Add 2026 Current Price anchor
  if (!histYears.includes(2026)) {
    histYears.push(2026);
    histPrices.push(currPrice);
  }

  const fanYears = [2026, ...forecastRows.map((r) => r.Year)];
  const fanBlended = [currPrice, ...forecastRows.map((r) => r["Target Price ($)"])];
  const fanM1 = [currPrice, ...forecastRows.map((r) => r["M1: Projected Price ($)"])];
  const fanM2 = [currPrice, ...forecastRows.map((r) => r["M2: Projected Price ($)"])];
  const fanM3 = [currPrice, ...forecastRows.map((r) => r["M3: Projected Price ($)"])];
  const fanM4 = [currPrice, ...forecastRows.map((r) => r["M4: Projected Price ($)"])];

  const fanTraces = [
    {
      name: "Historical Year-End Price",
      x: histYears,
      y: histPrices,
      mode: "lines+markers",
      line: { color: "#f8fafc", width: 3 },
      marker: { size: 6, color: "#f8fafc" },
    },
  ];
  if (m1On) {
    fanTraces.push({
      name: "M1: Hist EPS CAGR",
      x: fanYears,
      y: fanM1,
      mode: "lines+markers",
      line: { color: "#38bdf8", width: 1.8, dash: "dot" },
    });
  }
  if (m2On) {
    fanTraces.push({
      name: "M2: Rev CAGR × Margin",
      x: fanYears,
      y: fanM2,
      mode: "lines+markers",
      line: { color: "#c084fc", width: 1.8, dash: "dot" },
    });
  }
  if (m3On) {
    fanTraces.push({
      name: "M3: Yahoo LT Consensus",
      x: fanYears,
      y: fanM3,
      mode: "lines+markers",
      line: { color: "#fbbf24", width: 1.8, dash: "dot" },
    });
  }
  if (m4On) {
    fanTraces.push({
      name: "M4: Finviz 5Y EPS Growth",
      x: fanYears,
      y: fanM4,
      mode: "lines+markers",
      line: { color: "#f472b6", width: 1.8, dash: "dot" },
    });
  }
  fanTraces.push({
    name: "Blended Target Trajectory",
    x: fanYears,
    y: fanBlended,
    mode: "lines+markers",
    line: { color: "#10b981", width: 3.5 },
    marker: { size: 8, color: "#10b981" },
  });

  Plotly.newPlot(
    "valFanChart",
    fanTraces,
    {
      ...PLOTLY_DARK_LAYOUT,
      xaxis: { ...PLOTLY_DARK_LAYOUT.xaxis, title: "Timeline Year (2016–2031)", dtick: 1 },
      yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, title: "Share Price ($ USD)", tickprefix: "$" },
      legend: { orientation: "h", y: 1.12, x: 0, font: { size: 10 } },
    },
    PLOTLY_CONFIG
  );

  // 7-Pillar Moat Radar Chart
  const radarLabels = [
    "P1: Form 4 (15)",
    "P2: CEO Skin (10)",
    "P3: ROIC (15)",
    "P4: Culture (10)",
    "P5: Pricing (20)",
    "P6: SG&A (15)",
    "P7: Brand/Buyback (15)",
  ];
  const radarPct = [
    ((mp["Pillar 1: Form 4 Insider Alignment (15)"] || 0) / 15) * 100,
    ((mp["Pillar 2: CEO Ownership & Alignment (10)"] || 0) / 10) * 100,
    ((mp["Pillar 3: Capital Allocation & ROIC (15)"] || 0) / 15) * 100,
    ((mp["Pillar 4: Culture & Leadership (10)"] || 0) / 10) * 100,
    ((mp["Pillar 5: Pricing Power (20)"] || 0) / 20) * 100,
    ((mp["Pillar 6: SG&A Brand Leverage (15)"] || 0) / 15) * 100,
    ((mp["Pillar 7: Brand Recognition Index (15)"] || 0) / 15) * 100,
  ];
  Plotly.newPlot(
    "valMoatRadarChart",
    [
      {
        type: "scatterpolar",
        r: [...radarPct, radarPct[0]],
        theta: [...radarLabels, radarLabels[0]],
        fill: "toself",
        fillcolor: "rgba(16, 185, 129, 0.25)",
        line: { color: "#10b981", width: 2 },
      },
    ],
    {
      paper_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#cbd5e1", size: 9 },
      margin: { l: 28, r: 28, t: 18, b: 18 },
      polar: {
        bgcolor: "rgba(15,23,42,0.5)",
        radialaxis: { visible: true, range: [0, 100], gridcolor: "#1e293b", tickfont: { size: 8 } },
        angularaxis: { gridcolor: "#1e293b" },
      },
      showlegend: false,
    },
    PLOTLY_CONFIG
  );

  // Revenue, Gross Profit, Net Income & FCF Chart
  const gaap = data.gaap_history || [];
  const allFinYears = [...gaap.map((g) => g.year), ...forecastRows.map((f) => f.Year)];
  const allRev = [...gaap.map((g) => g.revenue_m), ...forecastRows.map((f) => f["Revenue ($M)"])];
  const allNi = [...gaap.map((g) => g.net_income_m), ...forecastRows.map((f) => f["Net Income ($M)"])];

  Plotly.newPlot(
    "valRevNiChart",
    [
      { name: "Revenue ($M)", x: allFinYears, y: allRev, type: "bar", marker: { color: "#38bdf8" } },
      { name: "Net Income ($M)", x: allFinYears, y: allNi, type: "bar", marker: { color: "#10b981" } },
      { name: "Hist Free Cash Flow ($M)", x: gaap.map((g) => g.year), y: gaap.map((g) => g.free_cash_flow_m), mode: "lines+markers", line: { color: "#fbbf24", width: 2 } },
    ],
    {
      ...PLOTLY_DARK_LAYOUT,
      barmode: "group",
      margin: { l: 48, r: 16, t: 24, b: 32 },
      legend: { orientation: "h", y: 1.15, x: 0, font: { size: 10 } },
    },
    PLOTLY_CONFIG
  );

  // Margin & ROIC Evolution Chart
  Plotly.newPlot(
    "valMarginChart",
    [
      { name: "Gross Margin %", x: gaap.map((g) => g.year), y: gaap.map((g) => g.gross_margin_pct), mode: "lines+markers", line: { color: "#10b981", width: 2.5 } },
      { name: "Net Margin %", x: allFinYears, y: [...gaap.map((g) => g.net_margin_pct), ...forecastRows.map((f) => f["Net Profit Margin (%)"])], mode: "lines+markers", line: { color: "#38bdf8", width: 2 } },
      { name: "SG&A / Rev %", x: gaap.map((g) => g.year), y: gaap.map((g) => g.sga_to_rev_pct), mode: "lines+markers", line: { color: "#f43f5e", width: 2, dash: "dot" } },
      { name: "ROIC %", x: gaap.map((g) => g.year), y: gaap.map((g) => g.roic_pct), mode: "lines+markers", line: { color: "#fbbf24", width: 2 } },
    ],
    {
      ...PLOTLY_DARK_LAYOUT,
      margin: { l: 44, r: 16, t: 24, b: 32 },
      yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, ticksuffix: "%" },
      legend: { orientation: "h", y: 1.15, x: 0, font: { size: 10 } },
    },
    PLOTLY_CONFIG
  );

  // Combine Historical + Simulated Forecast rows for the 15-Year Table (descending by year)
  const combinedTable = [...histAndCurr, ...forecastRows].sort((a, b) => Number(b.Year) - Number(a.Year));
  window.currentSimulatedTimeline = combinedTable;

  document.getElementById("valTimelineTableBody").innerHTML = combinedTable
    .map((r) => {
      const isProj = r["Period Type"] === "Projected" && Number(r.Year) >= 2027;
      return `
        <tr class="row-hover ${isProj ? "bg-emerald-950/10" : ""}">
          <td class="py-2 px-2 font-bold text-white">${r.Year}</td>
          <td class="py-2 px-2">
            <span class="px-1.5 py-0.5 rounded text-[10px] ${isProj ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-800 text-slate-300"}">${r["Period Type"]}</span>
          </td>
          <td class="py-2 px-2 text-right text-slate-200">${!isProj && r["Price ($)"] ? "$" + fmtNum(r["Price ($)"]) : "—"}</td>
          <td class="py-2 px-2 text-right font-bold text-emerald-400">${r["Target Price ($)"] ? "$" + fmtNum(r["Target Price ($)"]) : "—"}</td>
          <td class="py-2 px-2 text-right text-sky-300">${r["M1: Projected Price ($)"] ? "$" + fmtNum(r["M1: Projected Price ($)"]) : "—"}</td>
          <td class="py-2 px-2 text-right text-purple-300">${r["M2: Projected Price ($)"] ? "$" + fmtNum(r["M2: Projected Price ($)"]) : "—"}</td>
          <td class="py-2 px-2 text-right text-amber-300">${r["M3: Projected Price ($)"] ? "$" + fmtNum(r["M3: Projected Price ($)"]) : "—"}</td>
          <td class="py-2 px-2 text-right text-pink-300">${r["M4: Projected Price ($)"] ? "$" + fmtNum(r["M4: Projected Price ($)"]) : "—"}</td>
          <td class="py-2 px-2 text-right text-slate-300">${fmtNum(r["Target P/E Multiple"] || r["P/E Ratio"], 1)}x</td>
          <td class="py-2 px-2 text-right text-slate-200">${r["Revenue ($M)"] ? "$" + Number(r["Revenue ($M)"]).toLocaleString() : "—"}</td>
          <td class="py-2 px-2 text-right text-slate-200">${r["Net Income ($M)"] ? "$" + Number(r["Net Income ($M)"]).toLocaleString() : "—"}</td>
          <td class="py-2 px-2 text-right text-slate-300">${fmtNum(r["Net Profit Margin (%)"], 1)}%</td>
          <td class="py-2 px-2 text-right text-cyan-300">${r["Diluted EPS ($)"] ? "$" + fmtNum(r["Diluted EPS ($)"]) : "—"}</td>
          <td class="py-2 px-2 text-right text-slate-400">${fmtNum(r["Shares Outstanding (M)"], 1)}M</td>
        </tr>
      `;
    })
    .join("");
}

// ============================================================================
// TAB 5: ASYMMETRIC 5x MOONSHOT LAB ($300M–$10B)
// ============================================================================
async function loadMoonshotsTab() {
  const res = await fetch("/api/moonshots");
  const data = await res.json();
  window.moonshotData = data.moonshots || [];
  recomputeMoonshotLab();
}

function resetMoonshotWeights() {
  document.getElementById("moon_p1_w").value = 20;
  document.getElementById("moon_p2_w").value = 25;
  document.getElementById("moon_p3_w").value = 20;
  document.getElementById("moon_p4_w").value = 20;
  document.getElementById("moon_p5_w").value = 15;
  document.getElementById("moonOnlyDual").checked = false;
  recomputeMoonshotLab();
}

function recomputeMoonshotLab() {
  const w1 = parseFloat(document.getElementById("moon_p1_w").value) || 0;
  const w2 = parseFloat(document.getElementById("moon_p2_w").value) || 0;
  const w3 = parseFloat(document.getElementById("moon_p3_w").value) || 0;
  const w4 = parseFloat(document.getElementById("moon_p4_w").value) || 0;
  const w5 = parseFloat(document.getElementById("moon_p5_w").value) || 0;
  const onlyDual = document.getElementById("moonOnlyDual").checked;

  document.getElementById("moon_p1_lbl").textContent = `${w1} pts`;
  document.getElementById("moon_p2_lbl").textContent = `${w2} pts`;
  document.getElementById("moon_p3_lbl").textContent = `${w3} pts`;
  document.getElementById("moon_p4_lbl").textContent = `${w4} pts`;
  document.getElementById("moon_p5_lbl").textContent = `${w5} pts`;

  const wSum = w1 + w2 + w3 + w4 + w5;

  let list = (window.moonshotData || []).map((m) => {
    const p1 = (Number(m["Pillar 1: Survival Runway (20)"] || 0) / 20.0) * w1;
    const p2 = (Number(m["Pillar 2: Growth Velocity (25)"] || 0) / 25.0) * w2;
    const p3 = (Number(m["Pillar 3: Operating Torque (20)"] || 0) / 20.0) * w3;
    const p4 = (Number(m["Pillar 4: 3Y Re-Rating Upside (20)"] || 0) / 20.0) * w4;
    const p5 = (Number(m["Pillar 5: Insider & Size Torque (15)"] || 0) / 15.0) * w5;
    const customScore = wSum > 0 ? ((p1 + p2 + p3 + p4 + p5) / wSum) * 100.0 : 0;
    return { ...m, Custom_Inflection_Score: Number(customScore.toFixed(1)) };
  });

  if (onlyDual) {
    list = list.filter((m) => String(m["Survived Both Lists"]) === "YES");
  }
  list.sort((a, b) => b.Custom_Inflection_Score - a.Custom_Inflection_Score || Number(b["3Y Projected Return (%)"]) - Number(a["3Y Projected Return (%)"]));
  window.filteredMoonshots = list;
  document.getElementById("moonshotCountLbl").textContent = list.length;

  // Scatter Chart
  Plotly.newPlot(
    "moonshotScatterChart",
    [
      {
        name: "Moonshot Candidates",
        x: list.map((m) => m["Operating Margin (%)"]),
        y: list.map((m) => m["Revenue Growth (%)"]),
        text: list.map((m) => m.Ticker),
        customdata: list.map((m) => m.Ticker),
        hovertext: list.map(
          (m) =>
            `<b>${m.Ticker} — ${m["Company Name"]}</b><br>` +
            `Custom Inflection Score: ${m.Custom_Inflection_Score}<br>` +
            `Rev Growth: ${fmtSigned(m["Revenue Growth (%)"])} | Op Margin: ${fmtNum(m["Operating Margin (%)"], 1)}%<br>` +
            `3Y Target: $${fmtNum(m["3Y Inflection Target ($)"])} (${fmtSigned(m["3Y Projected Return (%)"])})`
        ),
        hoverinfo: "text",
        mode: "markers+text",
        textposition: "top center",
        textfont: { size: 9, color: "#cbd5e1" },
        marker: {
          size: list.map((m) => (String(m["Survived Both Lists"]) === "YES" ? 15 : 10)),
          symbol: list.map((m) => (String(m["Survived Both Lists"]) === "YES" ? "star" : "circle")),
          color: list.map((m) => m.Custom_Inflection_Score),
          colorscale: "YlOrRd",
          showscale: true,
        },
      },
    ],
    {
      ...PLOTLY_DARK_LAYOUT,
      xaxis: { ...PLOTLY_DARK_LAYOUT.xaxis, title: "Operating Margin (%)" },
      yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, title: "YoY Revenue Growth (%)" },
      shapes: [{ type: "line", x0: 0, x1: 0, y0: 20, y1: 300, line: { color: "#10b981", width: 1, dash: "dot" } }],
    },
    PLOTLY_CONFIG
  );

  document.getElementById("moonshotScatterChart").on("plotly_click", (ev) => {
    const t = ev?.points?.[0]?.customdata;
    if (t) openStockDeepDive(t);
  });

  // Table
  document.getElementById("moonshotTableBody").innerHTML = list
    .map(
      (m) => `
      <tr onclick="openStockDeepDive('${m.Ticker}')" class="row-hover cursor-pointer transition">
        <td class="py-2 px-2 font-bold text-amber-400">${m.Ticker}</td>
        <td class="py-2 px-2 font-sans text-white truncate max-w-[175px]">${m["Company Name"]}</td>
        <td class="py-2 px-2 text-center">
          ${String(m["Survived Both Lists"]) === "YES" ? '<span class="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[10px]">DUAL ★</span>' : "—"}
        </td>
        <td class="py-2 px-2 text-right text-slate-300">$${fmtNum(m["Market Cap ($B)"], 2)}B</td>
        <td class="py-2 px-2 text-right font-bold text-amber-300">${fmtNum(m.Custom_Inflection_Score, 1)}</td>
        <td class="py-2 px-2 text-right text-slate-200">$${fmtNum(m["Current Price ($)"])}</td>
        <td class="py-2 px-2 text-right text-emerald-300 font-semibold">$${fmtNum(m["3Y Inflection Target ($)"])}</td>
        <td class="py-2 px-2 text-right text-emerald-400 font-bold">${fmtSigned(m["3Y Projected Return (%)"])} (${fmtNum(m["3Y Implied Multiple (x)"], 2)}x)</td>
        <td class="py-2 px-2 text-right text-cyan-300 font-semibold">${fmtSigned(m["Revenue Growth (%)"])}</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(m["Gross Margin (%)"], 1)}%</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(m["Operating Margin (%)"], 1)}%</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(m["Current Ratio"], 2)}x</td>
      </tr>
    `
    )
    .join("");
}

// ============================================================================
// TAB 6: MEGA-CAP SWING-TRADE & ANCHOR DESK ($1T+)
// ============================================================================
async function loadMegaCapsTab() {
  const res = await fetch("/api/mega-caps");
  const data = await res.json();
  const list = data.mega_caps || [];
  window.megaCapData = list;

  document.getElementById("megaCapCardsGrid").innerHTML = list
    .map((m) => {
      const cagr = Number(m["5Y Projected CAGR (%)"] || 0);
      const isPositive = cagr >= 8.0;
      return `
        <div onclick="openStockDeepDive('${m.Ticker}')" class="glass-card p-4 cursor-pointer hover:border-indigo-500/60 transition space-y-3">
          <div class="flex items-start justify-between">
            <div>
              <div class="flex items-center gap-2">
                <span class="text-base font-bold font-mono text-indigo-400">${m.Ticker}</span>
                <span class="px-2 py-0.5 text-[10px] font-mono rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">Moat ${fmtNum(m["Total Moat Score (100)"], 1)}</span>
              </div>
              <p class="text-xs text-white font-medium mt-0.5">${m["Company Name"]}</p>
            </div>
            <span class="font-mono text-xs text-slate-400">$${fmtNum(m["Market Cap ($B)"], 0)}B</span>
          </div>

          <div class="grid grid-cols-3 gap-2 text-center bg-slate-900/80 rounded-lg p-2 font-mono text-xs">
            <div>
              <span class="text-[10px] text-slate-400 block">Current</span>
              <span class="text-white font-bold">$${fmtNum(m["Current Price ($)"])}</span>
            </div>
            <div>
              <span class="text-[10px] text-slate-400 block">3Y Target</span>
              <span class="text-cyan-300 font-bold">$${fmtNum(m["3Y Target Price ($)"])}</span>
            </div>
            <div>
              <span class="text-[10px] text-slate-400 block">5Y Target</span>
              <span class="${isPositive ? "text-emerald-400" : "text-amber-300"} font-bold">$${fmtNum(m["5Y Target Price ($)"])}</span>
            </div>
          </div>

          <div class="flex items-center justify-between text-xs font-mono pt-1 border-t border-slate-800/80">
            <span class="text-slate-400">5Y CAGR: <b class="${isPositive ? "text-emerald-400" : "text-rose-400"}">${fmtSigned(cagr, 2)}/yr</b></span>
            <span class="text-slate-400">Term P/E: <b class="text-slate-200">${fmtNum(m["Terminal Target P/E Multiple"], 1)}x</b></span>
          </div>
          <div class="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>5Y Ago: $${fmtNum(m["5Y Ago Price ($)"])}</span>
            <span>1Y Ago: $${fmtNum(m["1Y Ago Price ($)"])}</span>
            <span>3Y Dil: ${fmtSigned(m["3Y Share Dilution CAGR (%)"], 2)}</span>
          </div>
        </div>
      `;
    })
    .join("");

  Plotly.newPlot(
    "megaCapReturnChart",
    [
      {
        name: "3Y Projected Total Return (%)",
        x: list.map((m) => m.Ticker),
        y: list.map((m) => m["3Y Projected Return (%)"]),
        type: "bar",
        marker: { color: "#38bdf8" },
      },
      {
        name: "5Y Projected Total Return (%)",
        x: list.map((m) => m.Ticker),
        y: list.map((m) => m["5Y Projected Total Return (%)"]),
        type: "bar",
        marker: { color: "#10b981" },
      },
    ],
    {
      ...PLOTLY_DARK_LAYOUT,
      barmode: "group",
      yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, title: "Projected Cumulative Return (%)", ticksuffix: "%" },
      legend: { orientation: "h", y: 1.12, x: 0 },
    },
    PLOTLY_CONFIG
  );

  const pCols = [
    ["Pillar 1: Form 4 Insider Alignment (15)", "#38bdf8"],
    ["Pillar 2: CEO Ownership & Alignment (10)", "#818cf8"],
    ["Pillar 3: Capital Allocation & ROIC (15)", "#10b981"],
    ["Pillar 4: Culture & Leadership (10)", "#f472b6"],
    ["Pillar 5: Pricing Power (20)", "#fbbf24"],
    ["Pillar 6: SG&A Brand Leverage (15)", "#2dd4bf"],
    ["Pillar 7: Brand Recognition Index (15)", "#a78bfa"],
  ];

  Plotly.newPlot(
    "megaCapPillarChart",
    pCols.map(([col, color]) => ({
      name: col.split(":")[0],
      x: list.map((m) => m.Ticker),
      y: list.map((m) => m[col]),
      type: "bar",
      marker: { color },
    })),
    {
      ...PLOTLY_DARK_LAYOUT,
      barmode: "stack",
      yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, title: "Total Moat Score (100)", range: [0, 105] },
      legend: { orientation: "h", y: 1.14, x: 0, font: { size: 9 } },
    },
    PLOTLY_CONFIG
  );
}

// ============================================================================
// TAB 7: HEAD-TO-HEAD ARENA & BARBELL PORTFOLIO BUILDER
// ============================================================================
async function runArenaComparison() {
  const raw = document.getElementById("arenaTickersInput").value || "TSM, FIX, LLY, APP";
  const tickers = raw
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 6);

  const res = await fetch("/api/arena", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tickers }),
  });
  const data = await res.json();
  const stocks = data.stocks || [];
  if (!stocks.length) return;

  const colors = ["#10b981", "#38bdf8", "#fbbf24", "#f472b6", "#a78bfa", "#fb7185"];
  const radarLabels = [
    "P1: Form 4",
    "P2: CEO Skin",
    "P3: ROIC",
    "P4: Culture",
    "P5: Pricing",
    "P6: SG&A",
    "P7: Brand",
  ];

  // Radar Chart
  const radarTraces = stocks.map((s, idx) => {
    const mp = s.moat_pillars || {};
    const vals = [
      ((mp["Pillar 1: Form 4 Insider Alignment (15)"] || 0) / 15) * 100,
      ((mp["Pillar 2: CEO Ownership & Alignment (10)"] || 0) / 10) * 100,
      ((mp["Pillar 3: Capital Allocation & ROIC (15)"] || 0) / 15) * 100,
      ((mp["Pillar 4: Culture & Leadership (10)"] || 0) / 10) * 100,
      ((mp["Pillar 5: Pricing Power (20)"] || 0) / 20) * 100,
      ((mp["Pillar 6: SG&A Brand Leverage (15)"] || 0) / 15) * 100,
      ((mp["Pillar 7: Brand Recognition Index (15)"] || 0) / 15) * 100,
    ];
    return {
      name: s.ticker,
      type: "scatterpolar",
      r: [...vals, vals[0]],
      theta: [...radarLabels, radarLabels[0]],
      line: { color: colors[idx % colors.length], width: 2 },
      fill: "toself",
      opacity: 0.55,
    };
  });

  Plotly.newPlot(
    "arenaRadarChart",
    radarTraces,
    {
      paper_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#cbd5e1", size: 10 },
      margin: { l: 35, r: 35, t: 28, b: 28 },
      polar: {
        bgcolor: "rgba(15,23,42,0.5)",
        radialaxis: { visible: true, range: [0, 100], gridcolor: "#1e293b" },
        angularaxis: { gridcolor: "#1e293b" },
      },
      legend: { orientation: "h", y: 1.12, x: 0 },
    },
    PLOTLY_CONFIG
  );

  // Normalized Trajectory Chart
  const trajTraces = stocks.map((s, idx) => {
    const tl = (s.timeline || [])
      .filter((r) => (r["Period Type"] === "Historical" && r["Price ($)"]) || (r["Period Type"] === "Projected" && r["Target Price ($)"]))
      .sort((a, b) => Number(a.Year) - Number(b.Year));
    const yrs = tl.map((r) => r.Year);
    const rawP = tl.map((r) => (r["Period Type"] === "Projected" && Number(r.Year) >= 2027 ? r["Target Price ($)"] : r["Price ($)"]));
    const baseP = rawP.find((p) => p && p > 0) || 1;
    const normP = rawP.map((p) => (p ? Number(((p / baseP) * 100).toFixed(1)) : null));
    return {
      name: s.ticker,
      x: yrs,
      y: normP,
      mode: "lines+markers",
      line: { color: colors[idx % colors.length], width: 2.5 },
    };
  });

  Plotly.newPlot(
    "arenaTrajectoryChart",
    trajTraces,
    {
      ...PLOTLY_DARK_LAYOUT,
      xaxis: { ...PLOTLY_DARK_LAYOUT.xaxis, title: "Year (Historical + 5Y Model Trajectory)" },
      yaxis: { ...PLOTLY_DARK_LAYOUT.yaxis, title: "Indexed Price Trajectory (Base = 100)" },
      legend: { orientation: "h", y: 1.12, x: 0 },
    },
    PLOTLY_CONFIG
  );

  // Side-by-Side Comparison Matrix
  document.getElementById("arenaMatrixHead").innerHTML = `
    <tr class="border-b border-slate-800 text-slate-400 font-mono text-xs">
      <th class="py-2 px-3">Metric</th>
      ${stocks.map((s) => `<th class="py-2 px-3 text-right text-emerald-400">${s.ticker} — ${s.overview?.company_name || ""}</th>`).join("")}
    </tr>
  `;

  const metrics = [
    ["Sector / Size Tier", (s) => `${s.overview?.sector || "—"} (${s.overview?.market_cap_tier || ""})`],
    ["Market Cap ($B)", (s) => `$${fmtNum(s.overview?.market_cap_b, 2)}B`],
    ["Current Share Price ($)", (s) => `$${fmtNum(s.overview?.current_price, 2)}`],
    ["5Y Model Target Price ($)", (s) => `$${fmtNum(s.leaderboard_summary?.["5Y Target Price ($)"], 2)}`],
    ["5Y Projected CAGR (%)", (s) => `${fmtSigned(s.leaderboard_summary?.["5Y Projected CAGR (%)"], 2)}/yr`],
    ["Total Moat Score (100)", (s) => `${fmtNum(s.moat_pillars?.["Total Moat Score (100)"], 1)} / 100`],
    ["ROIC (%)", (s) => `${fmtNum(s.overview?.roic_pct, 1)}%`],
    ["Operating Margin (%)", (s) => `${fmtNum(s.overview?.operating_margin_pct, 1)}%`],
    ["Revenue Growth YoY (%)", (s) => `${fmtSigned(s.overview?.revenue_growth_pct, 1)}`],
    ["Forward P/E Multiple", (s) => `${fmtNum(s.overview?.forward_pe, 1)}x`],
    ["3Y Share Dilution CAGR (%)", (s) => `${fmtSigned(s.equation_defaults?.share_dilution_cagr_pct, 2)}/yr`],
    ["Moonshot Inflection Score", (s) => (s.moonshot_summary ? `${fmtNum(s.moonshot_summary["Moonshot Inflection Score (100)"], 1)} / 100` : "—")],
  ];

  document.getElementById("arenaMatrixBody").innerHTML = metrics
    .map(
      ([label, fn]) => `
      <tr class="row-hover">
        <td class="py-2 px-3 font-sans text-slate-300 font-medium">${label}</td>
        ${stocks.map((s) => `<td class="py-2 px-3 text-right text-slate-100">${fn(s)}</td>`).join("")}
      </tr>
    `
    )
    .join("");
}

// ============================================================================
// BARBELL PORTFOLIO BUILDER (CORE COMPOUNDERS + 1% MOONSHOTS)
// ============================================================================
const DEFAULT_BARBELL_PORTFOLIO = [
  { ticker: "TSM", weight: 18, sleeve: "Core Compounder" },
  { ticker: "FIX", weight: 15, sleeve: "Core Compounder" },
  { ticker: "LLY", weight: 14, sleeve: "Core Compounder" },
  { ticker: "URI", weight: 14, sleeve: "Core Compounder" },
  { ticker: "PH", weight: 14, sleeve: "Core Compounder" },
  { ticker: "GOOG", weight: 15, sleeve: "Core Compounder" },
  { ticker: "APP", weight: 4, sleeve: "Dual-Survivor Unicorn" },
  { ticker: "POWL", weight: 3, sleeve: "1% Moonshot Sleeve" },
  { ticker: "VITL", weight: 3, sleeve: "1% Moonshot Sleeve" },
];

function getSavedPortfolio() {
  try {
    const raw = localStorage.getItem("alphaterminal_barbell_portfolio");
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  return [...DEFAULT_BARBELL_PORTFOLIO];
}

function savePortfolio(list) {
  localStorage.setItem("alphaterminal_barbell_portfolio", JSON.stringify(list));
}

function resetDefaultPortfolio() {
  savePortfolio([...DEFAULT_BARBELL_PORTFOLIO]);
  renderBarbellPortfolio();
}

function addTickerToPortfolio() {
  const inp = document.getElementById("portAddTickerInput");
  const t = (inp.value || "").trim().toUpperCase();
  if (!t) return;
  const list = getSavedPortfolio();
  if (!list.some((x) => x.ticker === t)) {
    const isMoon = (window.moonshotData || []).some((m) => m.Ticker === t);
    list.push({ ticker: t, weight: isMoon ? 2 : 10, sleeve: isMoon ? "1% Moonshot Sleeve" : "Core Compounder" });
    savePortfolio(list);
  }
  inp.value = "";
  renderBarbellPortfolio();
}

function updatePortfolioWeight(ticker, newWeight) {
  const list = getSavedPortfolio().map((item) =>
    item.ticker === ticker ? { ...item, weight: Math.max(0, parseFloat(newWeight) || 0) } : item
  );
  savePortfolio(list);
  renderBarbellPortfolio();
}

function removePortfolioTicker(ticker) {
  const list = getSavedPortfolio().filter((item) => item.ticker !== ticker);
  savePortfolio(list);
  renderBarbellPortfolio();
}

function renderBarbellPortfolio() {
  const list = getSavedPortfolio();
  const moatMap = {};
  (window.moatStudioStocks || []).forEach((s) => (moatMap[s.Ticker] = s));
  const moonMap = {};
  (window.moonshotData || []).forEach((m) => (moonMap[m.Ticker] = m));

  const totalRawWeight = list.reduce((acc, x) => acc + (Number(x.weight) || 0), 0) || 1;

  let weightedCagr = 0;
  let weightedMoat = 0;
  let weightedRoic = 0;
  let weightedBeta = 0;
  let moonshotWeightPct = 0;

  const enriched = list.map((item) => {
    const normW = ((Number(item.weight) || 0) / totalRawWeight) * 100.0;
    const ms = moatMap[item.ticker];
    const mn = moonMap[item.ticker];

    const name = ms?.["Company Name"] || mn?.["Company Name"] || item.ticker;
    const price = ms?.["Current Price ($)"] || mn?.["Current Price ($)"] || 0;
    const cagr =
      ms?.["5Y Projected CAGR (%)"] ??
      (mn ? ((Math.pow(1 + Number(mn["3Y Projected Return (%)"] || 100) / 100, 1 / 3) - 1) * 100) : 12.0);
    const moat = ms?.["Total Moat Score (100)"] || mn?.["Moonshot Inflection Score (100)"] || 75.0;
    const roic = ms?.["ROIC (%)"] || mn?.["ROIC (%)"] || 15.0;
    const beta = ms?.Beta || mn?.Beta || 1.1;

    weightedCagr += (normW / 100.0) * Number(cagr);
    weightedMoat += (normW / 100.0) * Number(moat);
    weightedRoic += (normW / 100.0) * Number(roic);
    weightedBeta += (normW / 100.0) * Number(beta);
    if (item.sleeve.includes("Moonshot") || item.sleeve.includes("Unicorn")) {
      moonshotWeightPct += normW;
    }

    return { ...item, normW, name, price, cagr, moat, roic, beta };
  });

  document.getElementById("portfolioKpiStrip").innerHTML = `
    <div class="p-3 rounded-lg bg-slate-900 border border-slate-800">
      <span class="text-[10px] text-slate-400 block">Portfolio Weighted 5Y CAGR</span>
      <span class="text-lg font-bold font-mono text-emerald-400">${fmtSigned(weightedCagr, 2)}/yr</span>
    </div>
    <div class="p-3 rounded-lg bg-slate-900 border border-slate-800">
      <span class="text-[10px] text-slate-400 block">Weighted Moat / Quality Score</span>
      <span class="text-lg font-bold font-mono text-cyan-400">${fmtNum(weightedMoat, 1)} / 100</span>
    </div>
    <div class="p-3 rounded-lg bg-slate-900 border border-slate-800">
      <span class="text-[10px] text-slate-400 block">Weighted Portfolio ROIC</span>
      <span class="text-lg font-bold font-mono text-white">${fmtNum(weightedRoic, 1)}%</span>
    </div>
    <div class="p-3 rounded-lg bg-slate-900 border border-slate-800">
      <span class="text-[10px] text-slate-400 block">Portfolio Beta</span>
      <span class="text-lg font-bold font-mono text-indigo-300">${fmtNum(weightedBeta, 2)}</span>
    </div>
    <div class="p-3 rounded-lg bg-slate-900 border border-slate-800">
      <span class="text-[10px] text-slate-400 block">Core vs. Moonshot Split</span>
      <span class="text-lg font-bold font-mono text-amber-300">${fmtNum(100 - moonshotWeightPct, 0)}% / ${fmtNum(moonshotWeightPct, 0)}%</span>
    </div>
  `;

  document.getElementById("portfolioTableBody").innerHTML = enriched
    .map(
      (r) => `
      <tr class="row-hover">
        <td onclick="openStockDeepDive('${r.ticker}')" class="py-2 px-2 font-bold text-emerald-400 cursor-pointer">${r.ticker}</td>
        <td class="py-2 px-2 font-sans text-white">${r.name}</td>
        <td class="py-2 px-2"><span class="px-2 py-0.5 rounded text-[10px] border ${badgeColorClass(r.sleeve)}">${r.sleeve}</span></td>
        <td class="py-2 px-2 text-right">
          <input type="number" value="${r.weight}" min="0" max="100" step="1" onchange="updatePortfolioWeight('${r.ticker}', this.value)" class="w-16 bg-slate-950 border border-slate-700 rounded px-1.5 py-0.5 text-right text-xs text-white" />
          <span class="text-[10px] text-slate-400 ml-1">(${fmtNum(r.normW, 1)}%)</span>
        </td>
        <td class="py-2 px-2 text-right text-slate-200">$${fmtNum(r.price, 2)}</td>
        <td class="py-2 px-2 text-right text-emerald-400 font-bold">${fmtSigned(r.cagr, 1)}/yr</td>
        <td class="py-2 px-2 text-right text-cyan-300">${fmtNum(r.moat, 1)}</td>
        <td class="py-2 px-2 text-right text-slate-200">${fmtNum(r.roic, 1)}%</td>
        <td class="py-2 px-2 text-right text-slate-300">${fmtNum(r.beta, 2)}</td>
        <td class="py-2 px-2 text-center">
          <button onclick="removePortfolioTicker('${r.ticker}')" class="text-rose-400 hover:text-rose-300 text-xs">✕</button>
        </td>
      </tr>
    `
    )
    .join("");

  Plotly.newPlot(
    "portfolioPieChart",
    [
      {
        labels: enriched.map((e) => `${e.ticker} (${e.sleeve.split(" ")[0]})`),
        values: enriched.map((e) => Number(e.normW.toFixed(1))),
        type: "pie",
        hole: 0.48,
        textinfo: "label+percent",
        textfont: { size: 10, color: "#f8fafc" },
      },
    ],
    {
      paper_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#cbd5e1", size: 10 },
      margin: { l: 10, r: 10, t: 10, b: 10 },
      showlegend: false,
    },
    PLOTLY_CONFIG
  );
}

// ============================================================================
// INITIALIZE DASHBOARD ON LOAD
// ============================================================================
window.addEventListener("DOMContentLoaded", async () => {
  setupGlobalSearch();
  await Promise.all([
    loadOverviewTab(),
    loadMoatStudioTab(),
    loadMoonshotsTab(),
    loadMegaCapsTab(),
  ]);
  await runCustomScreener();
  await loadCompanyDeepDive("TSM");
  await runArenaComparison();
  renderBarbellPortfolio();
});
