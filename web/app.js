/* Opti WC dashboard */

const API = {
  results: "./data/expected_points.json",
  resultsOdds: "./data/expected_points_odds_only.json",
  resultsCurrent: "./data/expected_points_current.json",
  resultsCurrentOdds: "./data/expected_points_current_odds_only.json",
  tournament: "./data/tournament.json",
  odds: "./data/odds_oddschecker.json",
  tyche: "/.netlify/functions/tyche_opportunities",
  tycheLocal: "/api/tyche-opportunities",
  tycheFallback: "./data/tychemkt_opportunities.json",
};

let state = {
  results: null,
  resultsOdds: null,
  resultsCurrent: null,
  resultsCurrentOdds: null,
  hasCompare: false,
  hasCurrent: false,
  evView: "pre",
  tournament: null,
  odds: null,
  teamToGroup: {},
  enriched: [],
  charts: {},
  sortKey: "expected_points",
  sortAsc: false,
  cmpSortKey: "pts_diff",
  cmpSortAsc: false,
  tyche: null,
  tycheLive: false,
  tycheLoading: false,
  tycheError: null,
  tycheFetchedAt: 0,
  tycheFilter: "opps",
  tycheKind: "all",
  tycheSortKey: "edge",
  tycheSortAsc: false,
};

const RANKINGS_COLS = {
  pre: [
    { key: "display_rank", label: "#" },
    { key: "team", label: "Team" },
    { key: "group", label: "Grp" },
    { key: "expected_points_ml", label: "E[Pts] Pre" },
    { key: "expected_points_odds", label: "E[Pts] Odds" },
    { key: "pts_diff", label: "Δ ML−Odds" },
    { key: "p_champion", label: "P(W)" },
    { key: "p_semi_final", label: "P(SF)" },
    { key: "p_quarter_final", label: "P(QF)" },
    { key: "p_round_of_16", label: "P(R16)" },
    { key: "p_round_of_32", label: "P(R32)" },
    { key: "p_group_1", label: "P(1st)" },
    { key: "p_bonus_goals", label: "P(bonus)" },
  ],
  current: [
    { key: "display_rank", label: "#" },
    { key: "team", label: "Team" },
    { key: "group", label: "Grp" },
    { key: "expected_points_current", label: "E[Pts] Current" },
    { key: "expected_points_ml", label: "E[Pts] Pre" },
    { key: "pts_current_delta", label: "Δ vs Pre" },
    { key: "p_champion", label: "P(W)" },
    { key: "p_semi_final", label: "P(SF)" },
    { key: "p_quarter_final", label: "P(QF)" },
    { key: "p_round_of_16", label: "P(R16)" },
    { key: "p_round_of_32", label: "P(R32)" },
    { key: "p_group_1", label: "P(1st)" },
    { key: "p_bonus_goals", label: "P(bonus)" },
  ],
};

function isCurrentView() {
  return state.evView === "current" && state.hasCurrent;
}

function activeStats(r) {
  if (isCurrentView() && r.current_row) {
    return { ...r, ...r.current_row };
  }
  return r;
}

function primaryPts(r) {
  if (isCurrentView()) return r.expected_points_current;
  return r.expected_points_ml;
}

function updateDisplayRanks() {
  const key = isCurrentView() ? "expected_points_current" : "expected_points_ml";
  const sorted = [...state.enriched].sort((a, b) => (b[key] ?? 0) - (a[key] ?? 0));
  const rankMap = Object.fromEntries(sorted.map((row, i) => [row.team, i + 1]));
  state.enriched.forEach((row) => {
    row.display_rank = rankMap[row.team];
  });
  if (isCurrentView()) {
    state.enriched.sort((a, b) => a.display_rank - b.display_rank);
  }
}

function sortedEnriched() {
  return [...state.enriched].sort((a, b) => a.display_rank - b.display_rank);
}

Chart.defaults.color = "#8b97a8";
Chart.defaults.borderColor = "#252d3a";
Chart.defaults.font.family = "'DM Sans', system-ui, sans-serif";

const STAGE_ORDER = [
  "Champion",
  "Runner-up",
  "Third place",
  "Fourth",
  "Quarter-finals",
  "Round of 16",
  "Round of 32",
  "Group stage out",
  "Group stage (48th)",
];

const GROUP_POS_POINTS = { 1: 20, 2: 10, 3: 0, 4: 5 };
const BONUS_POINTS = 15;
const STAGE_POINTS = {
  Champion: 90,
  "Runner-up": 70,
  "Third place": 55,
  Fourth: 40,
  "Quarter-finals": 30,
  "Round of 16": 15,
  "Round of 32": 5,
  "Group stage out": 0,
  "Group stage (48th)": 5,
};

const GROUP_POS_LABELS = {
  1: "1st in group",
  2: "2nd in group",
  3: "3rd in group",
  4: "4th in group",
};

function computePointsBreakdown(r) {
  const groupRows = [1, 2, 3, 4].map((pos) => {
    const prob = r[`p_group_${pos}`] ?? 0;
    const ptsEach = GROUP_POS_POINTS[pos];
    return {
      label: GROUP_POS_LABELS[pos],
      prob,
      ptsEach,
      expected: prob * ptsEach,
    };
  });

  const stageRows = STAGE_ORDER.map((stage) => {
    const prob = r.stage_probs?.[stage] ?? 0;
    const ptsEach = STAGE_POINTS[stage];
    return { label: stage, prob, ptsEach, expected: prob * ptsEach };
  }).filter((row) => row.prob > 0.0001 || row.ptsEach > 0);

  const bonusProb = r.p_bonus_goals ?? 0;
  const bonusRow = {
    label: "Most GF+GA in groups (split if tied)",
    prob: bonusProb,
    ptsEach: BONUS_POINTS,
    expected: bonusProb * BONUS_POINTS,
  };

  const groupTotal = groupRows.reduce((s, row) => s + row.expected, 0);
  const stageTotal = stageRows.reduce((s, row) => s + row.expected, 0);
  const bonusTotal = bonusRow.expected;
  const total = groupTotal + stageTotal + bonusTotal;

  return { groupRows, stageRows, bonusRow, groupTotal, stageTotal, bonusTotal, total };
}

function fmtEv(v) {
  if (v == null || isNaN(v)) return "—";
  const n = Number(v);
  if (n > 0 && n < 0.05) return n.toFixed(2);
  return n.toFixed(1);
}

function renderBreakdownSection(title, rows, subtotal, accent) {
  const visible = rows.filter((row) => row.expected > 0.005 || row.prob > 0.001);
  const maxEv = Math.max(...visible.map((r) => r.expected), 0.01);

  const body = visible
    .map((row) => {
      const barPct = (row.expected / maxEv) * 100;
      return `
      <tr>
        <td class="breakdown-outcome">${row.label}</td>
        <td class="num breakdown-formula">
          <span class="formula-p">${pct(row.prob)}</span>
          <span class="formula-x">×</span>
          <span class="formula-pts">${row.ptsEach}</span>
        </td>
        <td class="num breakdown-ev">
          <div class="ev-cell">
            <span class="ev-value">${fmtEv(row.expected)}</span>
            <span class="ev-bar" style="width:${barPct}%"></span>
          </div>
        </td>
      </tr>`;
    })
    .join("");

  return `
    <div class="breakdown-panel" style="--breakdown-accent:${accent}">
      <div class="breakdown-panel-head">
        <h3>${title}</h3>
        <span class="breakdown-panel-total">${fmtEv(subtotal)} pts</span>
      </div>
      <table class="breakdown-table">
        <thead>
          <tr>
            <th>Outcome</th>
            <th>P × pts</th>
            <th>EV</th>
          </tr>
        </thead>
        <tbody>${body || `<tr><td colspan="3" class="breakdown-empty">No contribution</td></tr>`}</tbody>
      </table>
    </div>`;
}

function renderPointsBreakdown(r) {
  const hintEl = document.getElementById("breakdown-hint");
  const container = document.getElementById("team-points-breakdown");
  if (!hintEl || !container) return;

  try {
    const bd = computePointsBreakdown(r);
    const groupLetter = r.group;
    const groupTeams = state.tournament?.groups?.[groupLetter] || [];
    const mates = groupTeams.filter((t) => t !== r.team);

    hintEl.textContent =
      `Each row is expected value: probability × points. Components sum to ${fmtEv(bd.total)} expected points.`;

    const barTotal = bd.total || 1;
    const groupMatesHtml = mates.length
      ? `<p class="breakdown-mates">Group ${groupLetter}: ${mates.join(", ")}</p>`
      : `<p class="breakdown-mates">Group ${groupLetter}</p>`;

    container.innerHTML = `
      <div class="breakdown-header">
        <div class="breakdown-header-main">
          <span class="breakdown-team">${r.team}</span>
          ${groupMatesHtml}
        </div>
        <div class="breakdown-header-total">
          <span class="breakdown-header-label">Expected points</span>
          <span class="breakdown-header-value">${fmtEv(bd.total)}</span>
        </div>
      </div>

      <div class="breakdown-summary">
        <div class="breakdown-summary-item group">
          <span class="breakdown-summary-label">Group stage</span>
          <span class="breakdown-summary-value">${fmtEv(bd.groupTotal)}</span>
          <span class="breakdown-summary-share">${pct(bd.groupTotal / barTotal, 0)} of total</span>
        </div>
        <div class="breakdown-summary-item stage">
          <span class="breakdown-summary-label">Tournament exit</span>
          <span class="breakdown-summary-value">${fmtEv(bd.stageTotal)}</span>
          <span class="breakdown-summary-share">${pct(bd.stageTotal / barTotal, 0)} of total</span>
        </div>
        <div class="breakdown-summary-item bonus">
          <span class="breakdown-summary-label">Entertainment bonus</span>
          <span class="breakdown-summary-value">${fmtEv(bd.bonusTotal)}</span>
          <span class="breakdown-summary-share">${pct(bd.bonusTotal / barTotal, 0)} of total</span>
        </div>
      </div>

      <div class="breakdown-bar" aria-hidden="true">
        <div class="breakdown-bar-seg group" style="width:${(bd.groupTotal / barTotal) * 100}%"></div>
        <div class="breakdown-bar-seg stage" style="width:${(bd.stageTotal / barTotal) * 100}%"></div>
        <div class="breakdown-bar-seg bonus" style="width:${Math.max((bd.bonusTotal / barTotal) * 100, bd.bonusTotal > 0 ? 1.5 : 0)}%"></div>
      </div>

      <div class="breakdown-grid">
        ${renderBreakdownSection("Group finish", bd.groupRows, bd.groupTotal, "#3dd68c")}
        ${renderBreakdownSection("Final standing", bd.stageRows.sort((a, b) => b.expected - a.expected), bd.stageTotal, "#a78bfa")}
        ${renderBreakdownSection("Entertainment bonus", [bd.bonusRow], bd.bonusTotal, "#f0c14a")}
      </div>
    `;
  } catch (err) {
    console.error("Points breakdown render failed:", err);
    hintEl.textContent = "Could not render points breakdown.";
    container.innerHTML = `<p class="breakdown-error">${err.message}</p>`;
  }
}

const FUNNEL_KEYS = [
  { key: "p_round_of_32", label: "Round of 32" },
  { key: "p_round_of_16", label: "Round of 16" },
  { key: "p_quarter_final", label: "Quarter-finals" },
  { key: "p_semi_final", label: "Semi-finals" },
  { key: "p_champion", label: "Win tournament" },
];

async function fetchJson(url, label) {
  const r = await fetch(url, { credentials: "same-origin" });
  if (r.status === 401) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/login.html?next=${next}`;
    throw new Error("Session expired — redirecting to sign in");
  }
  if (!r.ok) throw new Error(`Missing ${label} — run python run.py first`);
  return r.json();
}

function tycheRowFields(row) {
  const useCurrent = isCurrentView() && row.theo_current != null;
  return {
    theo: useCurrent ? row.theo_current : row.theo_pre,
    side: useCurrent ? row.side_current : row.side_pre,
    edge: useCurrent ? row.edge_current : row.edge_pre,
    buy_edge: useCurrent ? row.buy_edge_current : row.buy_edge_pre,
    sell_edge: useCurrent ? row.sell_edge_current : row.sell_edge_pre,
  };
}

function fmtPrice(v) {
  if (v == null || Number.isNaN(v)) return "—";
  const n = Number(v);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function formatMyPosition(row, side) {
  const net = Number(row.my_net ?? 0);
  if (!net) {
    return { html: "—", cls: "pos-flat", aligned: false };
  }
  const label = net > 0 ? "long" : "short";
  const aligned = (side === "buy" && net > 0) || (side === "sell" && net < 0);
  const qty = net > 0 ? `+${fmtPrice(net)}` : fmtPrice(net);
  const held = aligned ? `<span class="pos-held" title="Already positioned for this opportunity">✓</span>` : "";
  return {
    html: `<span class="pos-qty">${qty}</span><span class="pos-label ${label}">${label}</span>${held}`,
    cls: `pos-${label}${aligned ? " pos-aligned" : ""}`,
    aligned,
  };
}

const TYCHE_STALE_MS = 45_000;
const TYCHE_WARN_MS = 120_000;

function tycheDataAgeMs() {
  if (!state.tyche) return null;
  const fromPayload = state.tyche.fetched_at ? Date.parse(state.tyche.fetched_at) : NaN;
  const fromClient = state.tycheFetchedAt || 0;
  const ts = Number.isFinite(fromPayload) ? fromPayload : fromClient;
  if (!ts) return null;
  return Date.now() - ts;
}

function formatTycheAge(ms) {
  if (ms == null) return "unknown age";
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  return `${Math.floor(min / 60)}h ago`;
}

function getTycheStaleInfo() {
  if (state.tycheLoading) return null;
  if (!state.tyche) {
    return state.tycheError
      ? { level: "error", message: `No Tyche data loaded — ${state.tycheError}` }
      : null;
  }

  const ageMs = tycheDataAgeMs();
  const ageLabel = formatTycheAge(ageMs);

  if (!state.tycheLive) {
    return {
      level: "warn",
      message: `Showing a cached snapshot (${ageLabel}), not a live pull. Orderbooks and positions may be out of date — click Refresh or configure TYCHE credentials on the server.`,
    };
  }

  if (state.tycheError) {
    return {
      level: "warn",
      message: `Live pull had issues (${state.tycheError}). Displaying last successful data from ${ageLabel}.`,
    };
  }

  if (ageMs != null && ageMs > TYCHE_WARN_MS) {
    return {
      level: "warn",
      message: `Tyche data is ${ageLabel}. Orderbooks may have moved — click Refresh for a fresh pull.`,
    };
  }

  return null;
}

function renderTycheStaleBanner() {
  const banner = document.getElementById("tyche-stale-banner");
  if (!banner) return;

  const info = getTycheStaleInfo();
  if (!info) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }

  banner.classList.remove("hidden");
  banner.classList.toggle("tyche-stale-error", info.level === "error");
  banner.classList.toggle("tyche-stale-warn", info.level !== "error");
  banner.textContent = info.message;
}

function renderTycheSummary() {
  const el = document.getElementById("tyche-summary");
  const hint = document.getElementById("tyche-hint");
  const footer = document.getElementById("tyche-footer");
  if (!el) return;

  if (state.tycheLoading && !state.tyche) {
    el.innerHTML = `
      <div class="tyche-stat neutral" style="grid-column: 1 / -1">
        <span class="tyche-stat-label">Loading live Tyche data…</span>
      </div>`;
    if (footer) footer.textContent = "Pulling live data from Tyche…";
    return;
  }

  if (!state.tyche) return;

  const items = state.tyche.items || [];
  const buy = items.filter((r) => tycheRowFields(r).side === "buy");
  const sell = items.filter((r) => tycheRowFields(r).side === "sell");
  const openPos = state.tyche.account?.open_positions ?? items.filter((r) => r.my_net).length;
  const acct = state.tyche.account?.name || "You";
  const fetched = state.tyche.fetched_at
    ? new Date(state.tyche.fetched_at).toLocaleString()
    : "unknown";

  el.innerHTML = `
    <div class="tyche-stat buy">
      <span class="tyche-stat-value">${buy.length}</span>
      <span class="tyche-stat-label">Buy opportunities</span>
      <span class="tyche-stat-sub">Ask below theo</span>
    </div>
    <div class="tyche-stat sell">
      <span class="tyche-stat-value">${sell.length}</span>
      <span class="tyche-stat-label">Sell opportunities</span>
      <span class="tyche-stat-sub">Bid above theo</span>
    </div>
    <div class="tyche-stat neutral">
      <span class="tyche-stat-value">${openPos}</span>
      <span class="tyche-stat-label">Your positions</span>
      <span class="tyche-stat-sub">${acct} on Tyche</span>
    </div>
  `;

  if (hint) {
    hint.textContent = `Theo = model expected points (${isCurrentView() ? "current tournament state" : "pre-tournament"}). Buy when ask < theo · Sell when bid > theo. ✓ = you already hold the suggested side.`;
  }
  if (footer) {
    if (state.tycheLoading) {
      footer.textContent = "Pulling live data from Tyche…";
    } else if (state.tycheError && !state.tyche) {
      footer.textContent = `Could not reach Tyche: ${state.tycheError}`;
    } else if (state.tycheLive) {
      footer.textContent = `Live from Tyche · updated ${fetched}`;
    } else if (state.tyche) {
      footer.textContent = `Cached snapshot · ${fetched} (set TYCHE_EMAIL / TYCHE_PASSWORD for live pulls)`;
    } else {
      footer.textContent = "No Tyche data — configure credentials or run the fetch script";
    }
  }

  renderTycheStaleBanner();
}

function renderTycheTable(query = "") {
  const tbody = document.querySelector("#tyche-table tbody");
  if (!tbody) return;

  if (!state.tyche?.items?.length) {
    const msg = state.tycheLoading
      ? "Loading Tyche orderbooks…"
      : state.tycheError
        ? `Could not load Tyche data: ${state.tycheError}`
        : `No Tyche data. Set <code>TYCHE_EMAIL</code> / <code>TYCHE_PASSWORD</code> on the server, or run the fetch script.`;
    tbody.innerHTML = `<tr><td colspan="9" class="tyche-empty">${msg}</td></tr>`;
    return;
  }

  const q = query.trim().toLowerCase();
  let rows = state.tyche.items.map((row) => ({ row, ...tycheRowFields(row) }));

  if (state.tycheFilter === "opps") rows = rows.filter((r) => r.side);
  else if (state.tycheFilter === "unheld") {
    rows = rows.filter((r) => r.side && Number(r.row.my_net ?? 0) === 0);
  } else if (state.tycheFilter === "buy") rows = rows.filter((r) => r.side === "buy");
  else if (state.tycheFilter === "sell") rows = rows.filter((r) => r.side === "sell");
  else if (state.tycheFilter === "held") rows = rows.filter((r) => Number(r.row.my_net ?? 0) !== 0);

  if (state.tycheKind !== "all") rows = rows.filter((r) => r.row.kind === state.tycheKind);

  if (q) {
    rows = rows.filter(({ row }) => {
      const hay = [row.title, row.team, row.home, row.away, row.group, row.stage]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }

  const key = state.tycheSortKey;
  const dir = state.tycheSortAsc ? 1 : -1;
  rows.sort((a, b) => {
    if (key === "title") return dir * String(a.row.title).localeCompare(b.row.title);
    if (key === "side") {
      const order = { buy: 0, sell: 1 };
      return dir * ((order[a.side] ?? 9) - (order[b.side] ?? 9));
    }
    const av =
      key === "theo"
        ? a.theo
        : key === "my_net"
          ? Number(a.row.my_net ?? 0)
          : key === "spread"
            ? (a.row.best_ask ?? 0) - (a.row.best_bid ?? 0)
            : key === "edge"
              ? a.edge ?? -999
              : a.row[key];
    const bv =
      key === "theo"
        ? b.theo
        : key === "my_net"
          ? Number(b.row.my_net ?? 0)
          : key === "spread"
            ? (b.row.best_ask ?? 0) - (b.row.best_bid ?? 0)
            : key === "edge"
              ? b.edge ?? -999
              : b.row[key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return dir * (av - bv);
  });

  tbody.innerHTML = rows
    .map(({ row, theo, side, edge }) => {
      const spread =
        row.best_bid != null && row.best_ask != null ? row.best_ask - row.best_bid : null;
      const kindBadge =
        row.kind === "match"
          ? `<span class="tyche-kind match">Match</span>`
          : `<span class="tyche-kind team">Team</span>`;
      const sideBadge = side
        ? `<span class="tyche-side ${side}">${side.toUpperCase()}</span>`
        : `<span class="tyche-side none">—</span>`;
      const edgeCls = edge > 0 ? "edge-pos" : edge != null ? "edge-neg" : "";
      const titleExtra =
        row.kind === "team" && row.group
          ? `<span class="tyche-meta">Grp ${row.group}</span>`
          : row.kind === "match" && row.kickoff
            ? `<span class="tyche-meta">${new Date(row.kickoff).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>`
            : "";
      const bidCell =
        row.best_bid != null
          ? `${fmtPrice(row.best_bid)}<span class="tyche-qty">×${fmtPrice(row.bid_qty)}</span>`
          : "—";
      const askCell =
        row.best_ask != null
          ? `${fmtPrice(row.best_ask)}<span class="tyche-qty">×${fmtPrice(row.ask_qty)}</span>`
          : "—";
      const bidCls = side === "sell" ? "book-highlight sell" : "";
      const askCls = side === "buy" ? "book-highlight buy" : "";
      const pos = formatMyPosition(row, side);
      return `
      <tr class="${side ? `tyche-opp-${side}` : ""}${pos.aligned ? " tyche-pos-aligned" : ""}">
        <td class="num ${edgeCls}">${edge != null && edge > 0 ? `+${fmtPrice(edge)}` : edge != null ? fmtPrice(edge) : "—"}</td>
        <td>${sideBadge}</td>
        <td class="tyche-title">${kindBadge}${row.title}${titleExtra}</td>
        <td class="num tyche-pos ${pos.cls}">${pos.html}</td>
        <td class="num">${theo != null ? fmtPrice(theo) : "—"}</td>
        <td class="num ${bidCls}">${bidCell}</td>
        <td class="num ${askCls}">${askCell}</td>
        <td class="num">${row.mark != null ? fmtPrice(row.mark) : "—"}</td>
        <td class="num">${spread != null ? fmtPrice(spread) : "—"}</td>
      </tr>`;
    })
    .join("");
}

function setupTychePanel() {
  document.getElementById("tyche-refresh")?.addEventListener("click", () => {
    loadTycheData(true);
  });

  document.querySelectorAll("[data-tyche-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.tycheFilter = btn.dataset.tycheFilter;
      document.querySelectorAll("[data-tyche-filter]").forEach((b) => {
        b.classList.toggle("active", b.dataset.tycheFilter === state.tycheFilter);
      });
      renderTycheTable(document.getElementById("search-tyche")?.value || "");
    });
  });

  document.querySelectorAll("[data-tyche-kind]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.tycheKind = btn.dataset.tycheKind;
      document.querySelectorAll("[data-tyche-kind]").forEach((b) => {
        b.classList.toggle("active", b.dataset.tycheKind === state.tycheKind);
      });
      renderTycheTable(document.getElementById("search-tyche")?.value || "");
    });
  });

  document.getElementById("search-tyche")?.addEventListener("input", (e) => {
    renderTycheTable(e.target.value);
  });

  document.querySelectorAll("#tyche-table th[data-sort-tyche]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sortTyche;
      if (state.tycheSortKey === key) state.tycheSortAsc = !state.tycheSortAsc;
      else {
        state.tycheSortKey = key;
        state.tycheSortAsc = key === "title" || key === "side";
      }
      renderTycheTable(document.getElementById("search-tyche")?.value || "");
    });
  });
}

async function loadTycheData(force = false) {
  if (state.tycheLoading) return;
  if (!force && state.tyche && Date.now() - state.tycheFetchedAt < TYCHE_STALE_MS) {
    return;
  }

  state.tycheLoading = true;
  state.tycheError = null;
  const refreshBtn = document.getElementById("tyche-refresh");
  if (refreshBtn) refreshBtn.disabled = true;
  renderTycheSummary();
  renderTycheTable(document.getElementById("search-tyche")?.value || "");

  const urls =
    window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost"
      ? [API.tycheLocal, API.tyche]
      : [API.tyche, API.tycheLocal];

  for (const url of urls) {
    try {
      const r = await fetch(url, { credentials: "same-origin" });
      if (r.status === 401) {
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = `/login.html?next=${next}`;
        return;
      }
      if (r.ok) {
        state.tyche = await r.json();
        state.tycheLive = !!state.tyche.live;
        state.tycheFetchedAt = Date.now();
        state.tycheLoading = false;
        if (refreshBtn) refreshBtn.disabled = false;
        renderTycheSummary();
        renderTycheTable(document.getElementById("search-tyche")?.value || "");
        return;
      }
      const errBody = await r.json().catch(() => ({}));
      state.tycheError = errBody.error || `HTTP ${r.status}`;
    } catch (err) {
      state.tycheError = err.message || "Network error";
    }
  }

  if (!state.tyche) {
    try {
      const r = await fetch(API.tycheFallback, { credentials: "same-origin" });
      if (r.ok) {
        state.tyche = await r.json();
        state.tycheLive = false;
        state.tycheFetchedAt = Date.now();
        state.tycheError = state.tycheError
          ? `${state.tycheError} — showing cached snapshot`
          : null;
      }
    } catch (_) {
      /* no fallback */
    }
  }

  state.tycheLoading = false;
  if (refreshBtn) refreshBtn.disabled = false;
  renderTycheSummary();
  renderTycheTable(document.getElementById("search-tyche")?.value || "");
}

async function loadData() {
  const [results, tournament, odds] = await Promise.all([
    fetchJson(API.results, "simulation output"),
    fetchJson(API.tournament, "tournament data"),
    fetchJson(API.odds, "odds data"),
  ]);

  let resultsOdds = null;
  try {
    const r = await fetch(API.resultsOdds, { credentials: "same-origin" });
    if (r.status === 401) {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/login.html?next=${next}`;
      throw new Error("Session expired");
    }
    if (r.ok) resultsOdds = await r.json();
  } catch (err) {
    if (err.message === "Session expired") throw err;
    /* optional comparison file */
  }

  let resultsCurrent = null;
  let resultsCurrentOdds = null;
  try {
    const r = await fetch(API.resultsCurrent, { credentials: "same-origin" });
    if (r.ok) resultsCurrent = await r.json();
  } catch (_) {
    /* optional current EV file */
  }
  try {
    const r = await fetch(API.resultsCurrentOdds, { credentials: "same-origin" });
    if (r.ok) resultsCurrentOdds = await r.json();
  } catch (_) {
    /* optional */
  }

  state.results = results;
  state.resultsOdds = resultsOdds;
  state.resultsCurrent = resultsCurrent;
  state.resultsCurrentOdds = resultsCurrentOdds;
  state.hasCompare = !!resultsOdds;
  state.hasCurrent = !!resultsCurrent;
  state.tournament = tournament;
  state.odds = odds;
  state.teamToGroup = {};
  for (const [g, teams] of Object.entries(tournament.groups)) {
    for (const t of teams) state.teamToGroup[t] = g;
  }

  const oddsByTeam = resultsOdds
    ? Object.fromEntries(resultsOdds.teams.map((t) => [t.team, t]))
    : {};
  const oddsRank = resultsOdds
    ? Object.fromEntries(resultsOdds.teams.map((t, i) => [t.team, i + 1]))
    : {};
  const currentByTeam = resultsCurrent
    ? Object.fromEntries(resultsCurrent.teams.map((t) => [t.team, t]))
    : {};
  const currentOddsByTeam = resultsCurrentOdds
    ? Object.fromEntries(resultsCurrentOdds.teams.map((t) => [t.team, t]))
    : {};

  state.enriched = results.teams.map((row, i) => {
    const oddsRow = oddsByTeam[row.team];
    const currentRow = currentByTeam[row.team];
    const currentOddsRow = currentOddsByTeam[row.team];
    const epMl = row.expected_points;
    const epOdds = oddsRow?.expected_points ?? null;
    const epCurrent = currentRow?.expected_points ?? null;
    const epCurrentOdds = currentOddsRow?.expected_points ?? null;
    const pwMl = row.p_champion;
    const pwOdds = oddsRow?.p_champion ?? null;
    return {
      ...row,
      rank: i + 1,
      rank_ml: i + 1,
      rank_odds: oddsRank[row.team] ?? null,
      group: state.teamToGroup[row.team] || "—",
      oc_odds: results.outright_input?.[row.team] ?? null,
      implied_win: results.outright_input?.[row.team]
        ? 100 / results.outright_input[row.team]
        : null,
      expected_points_ml: epMl,
      expected_points_odds: epOdds,
      expected_points_current: epCurrent,
      expected_points_current_odds: epCurrentOdds,
      pts_diff: epOdds != null ? epMl - epOdds : null,
      pts_current_delta: epCurrent != null ? epCurrent - epMl : null,
      p_champion_ml: pwMl,
      p_champion_odds: pwOdds,
      pw_diff: pwOdds != null ? pwMl - pwOdds : null,
      odds_row: oddsRow,
      current_row: currentRow,
    };
  });

  state.evView = state.hasCurrent ? "current" : "pre";
  updateDisplayRanks();
}

function pct(v, digits = 1) {
  if (v == null || isNaN(v)) return "—";
  return (v * 100).toFixed(digits) + "%";
}

function fmtPts(v) {
  if (v == null || isNaN(v)) return "—";
  return Number(v).toFixed(1);
}

function fmtDiff(v, suffix = "") {
  if (v == null || isNaN(v)) return "—";
  const cls = v > 0.05 ? "diff-pos" : v < -0.05 ? "diff-neg" : "diff-zero";
  const sign = v > 0 ? "+" : "";
  return `<span class="${cls}">${sign}${Number(v).toFixed(1)}${suffix}</span>`;
}

function fmtDiffPct(v) {
  if (v == null || isNaN(v)) return "—";
  const pp = v * 100;
  const cls = pp > 0.5 ? "diff-pos" : pp < -0.5 ? "diff-neg" : "diff-zero";
  const sign = pp > 0 ? "+" : "";
  return `<span class="${cls}">${sign}${pp.toFixed(1)}pp</span>`;
}

function destroyChart(id) {
  if (state.charts[id]) {
    state.charts[id].destroy();
    delete state.charts[id];
  }
}

function renderMeta() {
  const r = state.results;
  const compareNote = state.hasCompare
    ? `<div>ML + odds comparison loaded</div>`
    : `<div class="hint" style="margin-top:0.25rem">Run <code>python run.py --both-models</code> for comparison</div>`;
  const currentNote = state.hasCurrent
    ? `<div>Current EV: ${state.resultsCurrent.completed_matches?.length ?? "?"} match(es) played</div>`
    : `<div class="hint" style="margin-top:0.25rem">Add scores to <code>wc_data/completed_matches.json</code> and run <code>python run.py --results … --current-only</code></div>`;
  document.getElementById("meta").innerHTML = `
    <div>${r.n_simulations.toLocaleString()} simulations</div>
    <div>${r.use_ml !== false ? "ML + Oddschecker" : "Oddschecker only"}</div>
    ${compareNote}
    ${currentNote}
  `;
  document.getElementById("footer-sources").textContent =
    "Odds: " + r.odds_sources.join(" · ");
}

function renderRankingsHeader() {
  const cols = RANKINGS_COLS[isCurrentView() ? "current" : "pre"];
  const head = document.getElementById("rankings-head-row");
  if (!head) return;
  head.innerHTML = cols
    .map((col) => `<th data-sort="${col.key}">${col.label}</th>`)
    .join("");
  document.querySelectorAll("#rankings-table th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) state.sortAsc = !state.sortAsc;
      else {
        state.sortKey = key;
        state.sortAsc = key === "team" || key === "group";
      }
      renderRankingsTable(document.getElementById("search-rankings")?.value || "");
    });
  });
}

function renderRankingsTable(filter = "") {
  const tbody = document.querySelector("#rankings-table tbody");
  const q = filter.toLowerCase();
  let rows = state.enriched.filter((r) => r.team.toLowerCase().includes(q));

  rows = [...rows].sort((a, b) => {
    const av = a[state.sortKey];
    const bv = b[state.sortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "string") return state.sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    return state.sortAsc ? av - bv : bv - av;
  });

  tbody.innerHTML = rows
    .map((r) => {
      const s = activeStats(r);
      if (isCurrentView()) {
        return `
    <tr data-team="${r.team}">
      <td class="rank-cell">${r.display_rank}</td>
      <td class="team-cell">${r.team}</td>
      <td>${r.group}</td>
      <td><strong>${fmtPts(r.expected_points_current)}</strong></td>
      <td>${fmtPts(r.expected_points_ml)}</td>
      <td>${fmtDiff(r.pts_current_delta)}</td>
      <td class="pct ${s.p_champion > 0.08 ? "pct-high" : ""}">${pct(s.p_champion)}</td>
      <td class="pct">${pct(s.p_semi_final)}</td>
      <td class="pct">${pct(s.p_quarter_final)}</td>
      <td class="pct">${pct(s.p_round_of_16)}</td>
      <td class="pct">${pct(s.p_round_of_32)}</td>
      <td class="pct">${pct(s.p_group_1)}</td>
      <td class="pct">${pct(s.p_bonus_goals)}</td>
    </tr>`;
      }
      return `
    <tr data-team="${r.team}">
      <td class="rank-cell">${r.display_rank}</td>
      <td class="team-cell">${r.team}</td>
      <td>${r.group}</td>
      <td><strong>${fmtPts(r.expected_points_ml)}</strong></td>
      <td>${fmtPts(r.expected_points_odds)}</td>
      <td>${fmtDiff(r.pts_diff)}</td>
      <td class="pct ${s.p_champion > 0.08 ? "pct-high" : ""}">${pct(s.p_champion)}</td>
      <td class="pct">${pct(s.p_semi_final)}</td>
      <td class="pct">${pct(s.p_quarter_final)}</td>
      <td class="pct">${pct(s.p_round_of_16)}</td>
      <td class="pct">${pct(s.p_round_of_32)}</td>
      <td class="pct">${pct(s.p_group_1)}</td>
      <td class="pct">${pct(s.p_bonus_goals)}</td>
    </tr>`;
    })
    .join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => selectTeam(tr.dataset.team, "teams"));
  });
}

function renderPointsChart() {
  destroyChart("points");
  const top = sortedEnriched().slice(0, 20);
  const ctx = document.getElementById("chart-points");
  const title = document.getElementById("chart-points-title");
  if (title) {
    title.textContent = isCurrentView()
      ? "Current expected points — top 20"
      : "Pre-tournament expected points — top 20";
  }

  if (isCurrentView()) {
    state.charts.points = new Chart(ctx, {
      type: "bar",
      data: {
        labels: top.map((t) => t.team),
        datasets: [
          {
            label: "Current EV",
            data: top.map((t) => t.expected_points_current ?? 0),
            backgroundColor: "rgba(61, 214, 140, 0.85)",
            borderRadius: 4,
          },
          {
            label: "Pre-tournament EV",
            data: top.map((t) => t.expected_points_ml ?? 0),
            backgroundColor: "rgba(139, 151, 168, 0.55)",
            borderRadius: 4,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: true, position: "bottom", labels: { boxWidth: 12 } },
        },
        scales: {
          x: { grid: { color: "#252d3a" }, title: { display: true, text: "Points" } },
          y: { grid: { display: false } },
        },
      },
    });
    return;
  }

  const datasets = [
    {
      label: "ML + Oddschecker",
      data: top.map((t) => t.expected_points_ml),
      backgroundColor: "rgba(61, 214, 140, 0.85)",
      borderRadius: 4,
    },
  ];
  if (state.hasCompare) {
    datasets.push({
      label: "Odds only",
      data: top.map((t) => t.expected_points_odds ?? 0),
      backgroundColor: "rgba(91, 156, 245, 0.75)",
      borderRadius: 4,
    });
  }
  state.charts.points = new Chart(ctx, {
    type: "bar",
    data: {
      labels: top.map((t) => t.team),
      datasets,
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: state.hasCompare, position: "bottom", labels: { boxWidth: 12 } },
      },
      scales: {
        x: { grid: { color: "#252d3a" }, title: { display: true, text: "Points" } },
        y: { grid: { display: false } },
      },
    },
  });
}

function renderWinnersChart() {
  destroyChart("winners");
  const top = [...state.enriched]
    .map((r) => activeStats(r))
    .sort((a, b) => b.p_champion - a.p_champion)
    .slice(0, 12);
  const ctx = document.getElementById("chart-winners");
  const datasets = [
    {
      label: isCurrentView() ? "P(Champion) current" : "P(Champion) ML",
      data: top.map((t) => t.p_champion * 100),
      backgroundColor: "#3dd68c",
      borderRadius: 4,
    },
  ];
  if (state.hasCompare && !isCurrentView()) {
    datasets.push({
      label: "P(Champion) Odds",
      data: top.map((t) => (t.p_champion_odds ?? 0) * 100),
      backgroundColor: "rgba(91, 156, 245, 0.85)",
      borderRadius: 4,
    });
  }
  datasets.push({
    label: "Implied (OC)",
    data: top.map((t) => t.implied_win ?? 0),
    backgroundColor: "rgba(167, 139, 250, 0.7)",
    borderRadius: 4,
  });
  state.charts.winners = new Chart(ctx, {
    type: "bar",
    data: {
      labels: top.map((t) => t.team),
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, padding: 16 } },
      },
      scales: {
        y: {
          grid: { color: "#252d3a" },
          title: { display: true, text: "%" },
          max: Math.ceil(
            Math.max(
              ...top.map((t) =>
                Math.max(t.p_champion_ml * 100, t.p_champion_odds * 100 || 0, t.implied_win || 0)
              )
            ) + 2
          ),
        },
        x: { grid: { display: false } },
      },
    },
  });
}

function renderCompareChart() {
  if (!state.hasCompare) return;

  destroyChart("compare");
  const top = [...state.enriched]
    .sort((a, b) => b.expected_points_ml - a.expected_points_ml)
    .slice(0, 20);

  state.charts.compare = new Chart(document.getElementById("chart-compare"), {
    type: "bar",
    data: {
      labels: top.map((t) => t.team),
      datasets: [
        {
          label: "ML + Oddschecker",
          data: top.map((t) => t.expected_points_ml),
          backgroundColor: "#3dd68c",
          borderRadius: 4,
        },
        {
          label: "Odds only",
          data: top.map((t) => t.expected_points_odds),
          backgroundColor: "#5b9cf5",
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
      scales: {
        y: { grid: { color: "#252d3a" }, title: { display: true, text: "Expected points" } },
        x: { grid: { display: false }, ticks: { maxRotation: 45, minRotation: 45 } },
      },
    },
  });

  destroyChart("compareScatter");
  const pts = state.enriched.filter((r) => r.expected_points_odds != null);
  const maxPt = Math.max(...pts.map((r) => Math.max(r.expected_points_ml, r.expected_points_odds)));

  state.charts.compareScatter = new Chart(document.getElementById("chart-compare-scatter"), {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Teams",
          data: pts.map((r) => ({
            x: r.expected_points_odds,
            y: r.expected_points_ml,
            team: r.team,
          })),
          backgroundColor: "#3dd68c",
          pointRadius: 6,
          pointHoverRadius: 9,
        },
        {
          label: "Equal",
          data: [
            { x: 0, y: 0 },
            { x: maxPt + 5, y: maxPt + 5 },
          ],
          type: "line",
          borderColor: "rgba(139, 151, 168, 0.4)",
          borderDash: [6, 4],
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const t = ctx.raw.team || "";
              return `${t}: odds ${ctx.raw.x?.toFixed(1)}, ML ${ctx.raw.y?.toFixed(1)}`;
            },
          },
        },
      },
      scales: {
        x: { title: { display: true, text: "Odds-only E[Pts]" }, grid: { color: "#252d3a" } },
        y: { title: { display: true, text: "ML E[Pts]" }, grid: { color: "#252d3a" } },
      },
      onClick: (_, elems) => {
        if (elems[0]?.datasetIndex === 0) {
          const pt = pts[elems[0].index];
          if (pt) selectTeam(pt.team);
        }
      },
    },
  });
}

function renderCompareTable(filter = "") {
  if (!state.hasCompare) {
    document.querySelector("#compare-table tbody").innerHTML = `
      <tr><td colspan="10" style="text-align:center;color:var(--text-muted);padding:2rem">
        Comparison data not found. Run: <code>python run.py --both-models</code>
      </td></tr>`;
    return;
  }

  const q = filter.toLowerCase();
  let rows = state.enriched.filter((r) => r.team.toLowerCase().includes(q));

  rows = [...rows].sort((a, b) => {
    const av = a[state.cmpSortKey];
    const bv = b[state.cmpSortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "string") return state.cmpSortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    return state.cmpSortAsc ? av - bv : bv - av;
  });

  document.querySelector("#compare-table tbody").innerHTML = rows
    .map(
      (r) => `
    <tr data-team="${r.team}">
      <td class="team-cell">${r.team}</td>
      <td>${r.group}</td>
      <td><strong>${fmtPts(r.expected_points_ml)}</strong></td>
      <td>${fmtPts(r.expected_points_odds)}</td>
      <td>${fmtDiff(r.pts_diff)}</td>
      <td class="pct">${pct(r.p_champion_ml)}</td>
      <td class="pct">${pct(r.p_champion_odds)}</td>
      <td>${fmtDiffPct(r.pw_diff)}</td>
      <td class="rank-cell">${r.rank_ml}</td>
      <td class="rank-cell">${r.rank_odds ?? "—"}</td>
    </tr>`
    )
    .join("");

  document.querySelectorAll("#compare-table tbody tr").forEach((tr) => {
    tr.addEventListener("click", () => selectTeam(tr.dataset.team));
  });
}

function selectTeam(name, tab = "teams") {
  document.querySelector(`.tab[data-tab="${tab}"]`)?.click();
  const sel = document.getElementById("team-select");
  if (sel) {
    sel.value = name;
    renderTeamDetail(name);
  }
}

function renderTeamSelect() {
  const sel = document.getElementById("team-select");
  const current = sel.value;
  const ordered = sortedEnriched();
  sel.innerHTML = ordered
    .map((r) => `<option value="${r.team}">${r.team} (Group ${r.group})</option>`)
    .join("");
  if (current && ordered.some((r) => r.team === current)) sel.value = current;
  else if (ordered.length) sel.value = ordered[0].team;
  renderTeamDetail(sel.value);
}

function renderTeamDetail(teamName) {
  const r = state.enriched.find((t) => t.team === teamName);
  if (!r) return;
  const s = activeStats(r);
  const viewLabel = isCurrentView() ? "current" : "pre-tournament";
  const rank = r.display_rank;

  const compareStats = state.hasCompare && !isCurrentView()
    ? `
      <div class="stat"><div class="stat-label">E[Pts] odds</div><div class="stat-value">${fmtPts(r.expected_points_odds)}</div></div>
      <div class="stat"><div class="stat-label">Δ E[Pts]</div><div class="stat-value">${r.pts_diff != null ? (r.pts_diff > 0 ? "+" : "") + r.pts_diff.toFixed(1) : "—"}</div></div>
      <div class="stat"><div class="stat-label">P(Win) odds</div><div class="stat-value">${pct(r.p_champion_odds)}</div></div>
    `
    : "";
  const currentStats = isCurrentView()
    ? `
      <div class="stat"><div class="stat-label">E[Pts] current</div><div class="stat-value accent">${fmtPts(r.expected_points_current)}</div></div>
      <div class="stat"><div class="stat-label">E[Pts] pre</div><div class="stat-value">${fmtPts(r.expected_points_ml)}</div></div>
      <div class="stat"><div class="stat-label">Δ vs pre</div><div class="stat-value">${r.pts_current_delta != null ? (r.pts_current_delta > 0 ? "+" : "") + r.pts_current_delta.toFixed(1) : "—"}</div></div>
    `
    : `
      <div class="stat"><div class="stat-label">E[Pts] pre</div><div class="stat-value accent">${fmtPts(r.expected_points_ml)}</div></div>
    `;

  document.getElementById("team-summary").innerHTML = `
    <div class="stat-grid">
      ${currentStats}
      <div class="stat"><div class="stat-label">Group ${r.group}</div><div class="stat-value">#${rank}</div></div>
      <div class="stat"><div class="stat-label">P(Win) · ${viewLabel}</div><div class="stat-value">${pct(s.p_champion)}</div></div>
      <div class="stat"><div class="stat-label">OC winner</div><div class="stat-value">${r.oc_odds ?? "—"}</div></div>
      ${compareStats}
    </div>
  `;

  renderPointsBreakdown(s);

  destroyChart("funnel");
  state.charts.funnel = new Chart(document.getElementById("chart-funnel"), {
    type: "bar",
    data: {
      labels: FUNNEL_KEYS.map((f) => f.label),
      datasets: [
        {
          label: isCurrentView() ? "Current model" : "ML model",
          data: FUNNEL_KEYS.map((f) => s[f.key] * 100),
          backgroundColor: "#3dd68c",
          borderRadius: 6,
        },
        ...(state.hasCompare && r.odds_row && !isCurrentView()
          ? [
              {
                label: "Odds only",
                data: FUNNEL_KEYS.map((f) => (r.odds_row[f.key] ?? 0) * 100),
                backgroundColor: "rgba(91, 156, 245, 0.85)",
                borderRadius: 6,
              },
            ]
          : []),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: state.hasCompare, position: "bottom", labels: { boxWidth: 12 } },
      },
      scales: {
        y: { max: 100, grid: { color: "#252d3a" }, ticks: { callback: (v) => v + "%" } },
        x: { grid: { display: false } },
      },
    },
  });

  destroyChart("groupPos");
  state.charts.groupPos = new Chart(document.getElementById("chart-group-pos"), {
    type: "doughnut",
    data: {
      labels: ["1st (20p)", "2nd (10p)", "3rd (0p)", "4th (5p)"],
      datasets: [
        {
          data: [s.p_group_1, s.p_group_2, s.p_group_3, s.p_group_4].map((x) => x * 100),
          backgroundColor: ["#3dd68c", "#5b9cf5", "#8b97a8", "#f0c14a"],
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "right", labels: { boxWidth: 10, padding: 12 } },
      },
    },
  });

  const stages = STAGE_ORDER.filter((sname) => s.stage_probs?.[sname] > 0.001).map((sname) => ({
    label: sname,
    value: s.stage_probs[sname] * 100,
  }));

  destroyChart("stages");
  state.charts.stages = new Chart(document.getElementById("chart-stages"), {
    type: "bar",
    data: {
      labels: stages.map((s) => s.label),
      datasets: [
        {
          label: "ML model",
          data: stages.map((s) => s.value),
          backgroundColor: "#a78bfa",
          borderRadius: 4,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: "#252d3a" }, max: 100, ticks: { callback: (v) => v + "%" } },
        y: { grid: { display: false } },
      },
    },
  });
}

function renderGroups() {
  const grid = document.getElementById("groups-grid");
  const byTeam = Object.fromEntries(state.enriched.map((r) => [r.team, r]));
  const ptsKey = isCurrentView() ? "expected_points_current" : "expected_points_ml";
  const headerLabel = isCurrentView() ? "Current E[Pts]" : "Pre E[Pts]";

  grid.innerHTML = Object.entries(state.tournament.groups)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([g, teams]) => {
      const sorted = [...teams].sort(
        (a, b) => (byTeam[b]?.[ptsKey] || 0) - (byTeam[a]?.[ptsKey] || 0)
      );
      return `
      <div class="group-card">
        <div class="group-header">Group ${g}<span>${headerLabel}</span></div>
        ${sorted
          .map((t) => {
            const r = byTeam[t];
            const mainPts = r ? fmtPts(r[ptsKey]) : "—";
            const subPts = isCurrentView()
              ? r?.expected_points_ml != null
                ? fmtPts(r.expected_points_ml)
                : null
              : r?.expected_points_odds != null
                ? fmtPts(r.expected_points_odds)
                : null;
            const delta =
              isCurrentView() && r?.pts_current_delta != null
                ? `<span class="group-team-delta ${r.pts_current_delta >= 0 ? "diff-pos" : "diff-neg"}">${r.pts_current_delta > 0 ? "+" : ""}${r.pts_current_delta.toFixed(1)}</span>`
                : "";
            return `
          <div class="group-team" data-team="${t}">
            <span class="group-team-name">${t}</span>
            <span class="group-team-pts">
              ${mainPts}
              ${subPts ? `<span class="group-team-pts-sub">${subPts}</span>` : ""}
              ${delta}
            </span>
          </div>`;
          })
          .join("")}
      </div>`;
    })
    .join("");

  grid.querySelectorAll(".group-team").forEach((el) => {
    el.addEventListener("click", () => selectTeam(el.dataset.team));
  });
}

function renderCalibration() {
  const withOdds = state.enriched.filter((r) => r.implied_win != null && r.implied_win < 30);

  destroyChart("calibration");
  state.charts.calibration = new Chart(document.getElementById("chart-calibration"), {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "ML model",
          data: withOdds.map((r) => ({
            x: r.implied_win,
            y: r.p_champion_ml * 100,
            team: r.team,
          })),
          backgroundColor: "#3dd68c",
          pointRadius: 6,
          pointHoverRadius: 9,
        },
        ...(state.hasCompare
          ? [
              {
                label: "Odds only",
                data: withOdds.map((r) => ({
                  x: r.implied_win,
                  y: (r.p_champion_odds ?? 0) * 100,
                  team: r.team,
                })),
                backgroundColor: "#5b9cf5",
                pointRadius: 5,
                pointHoverRadius: 8,
              },
            ]
          : []),
        {
          label: "Perfect calibration",
          data: [
            { x: 0, y: 0 },
            { x: 25, y: 25 },
          ],
          type: "line",
          borderColor: "rgba(139, 151, 168, 0.4)",
          borderDash: [6, 4],
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: state.hasCompare, position: "bottom", labels: { boxWidth: 12 } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const t = ctx.raw.team || "";
              return `${t}: implied ${ctx.raw.x?.toFixed(1)}%, sim ${ctx.raw.y?.toFixed(1)}%`;
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: "Oddschecker implied win %" },
          grid: { color: "#252d3a" },
        },
        y: {
          title: { display: true, text: "Simulated P(Champion) %" },
          grid: { color: "#252d3a" },
        },
      },
      onClick: (_, elems) => {
        const ds = elems[0]?.datasetIndex;
        const idx = elems[0]?.index;
        if (ds === 0 || (state.hasCompare && ds === 1)) {
          const pt = withOdds[idx];
          if (pt) selectTeam(pt.team);
        }
      },
    },
  });

  const gaps = withOdds
    .map((r) => ({
      ...r,
      gap: r.implied_win - r.p_champion_ml * 100,
    }))
    .sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))
    .slice(0, 15);

  document.querySelector("#calibration-table tbody").innerHTML = gaps
    .map(
      (r) => `
    <tr data-team="${r.team}">
      <td class="team-cell">${r.team}</td>
      <td>${r.oc_odds?.toFixed(2) ?? "—"}</td>
      <td>${r.implied_win.toFixed(1)}%</td>
      <td>${pct(r.p_champion_ml)}</td>
      <td class="${r.gap > 1 ? "gap-pos" : r.gap < -1 ? "gap-neg" : ""}">${r.gap > 0 ? "+" : ""}${r.gap.toFixed(1)}pp</td>
    </tr>`
    )
    .join("");

  document.querySelectorAll("#calibration-table tbody tr").forEach((tr) => {
    tr.addEventListener("click", () => selectTeam(tr.dataset.team));
  });
}

function renderMatches(filter = "") {
  const q = filter.toLowerCase();
  const matches = (state.odds.matches || []).filter(
    (m) => m.home.toLowerCase().includes(q) || m.away.toLowerCase().includes(q)
  );

  document.querySelector("#matches-table tbody").innerHTML = matches
    .map(
      (m) => `
    <tr>
      <td>${m.date}</td>
      <td class="team-cell">${m.home}</td>
      <td class="team-cell">${m.away}</td>
      <td>${m.odds.home?.toFixed(2) ?? "—"}</td>
      <td>${m.odds.draw?.toFixed(2) ?? "—"}</td>
      <td>${m.odds.away?.toFixed(2) ?? "—"}</td>
    </tr>`
    )
    .join("");
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`panel-${tab.dataset.tab}`).classList.add("active");
      if (tab.dataset.tab === "teams") {
        const sel = document.getElementById("team-select");
        if (sel?.value) renderTeamDetail(sel.value);
      }
      if (tab.dataset.tab === "calibration") renderCalibration();
      if (tab.dataset.tab === "compare") {
        renderCompareChart();
        renderCompareTable(document.getElementById("search-compare")?.value || "");
      }
      if (tab.dataset.tab === "tyche") {
        loadTycheData(false).then(() => {
          renderTycheSummary();
          renderTycheTable(document.getElementById("search-tyche")?.value || "");
        });
      }
    });
  });
}

function setupSort() {
  renderRankingsHeader();

  document.querySelectorAll("#compare-table th[data-sort-cmp]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sortCmp;
      if (state.cmpSortKey === key) state.cmpSortAsc = !state.cmpSortAsc;
      else {
        state.cmpSortKey = key;
        state.cmpSortAsc = key === "team" || key === "group";
      }
      renderCompareTable(document.getElementById("search-compare").value);
    });
  });
}

function setupSearch() {
  document.getElementById("search-rankings").addEventListener("input", (e) => {
    renderRankingsTable(e.target.value);
  });
  document.getElementById("search-matches").addEventListener("input", (e) => {
    renderMatches(e.target.value);
  });
  document.getElementById("search-compare").addEventListener("input", (e) => {
    renderCompareTable(e.target.value);
  });
}

function applyEvView(view) {
  if (view === "current" && !state.hasCurrent) return;
  state.evView = view;
  state.sortKey = view === "current" ? "expected_points_current" : "expected_points_ml";
  state.sortAsc = false;
  updateDisplayRanks();
  document.querySelectorAll(".ev-toggle-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  renderRankingsHeader();
  renderRankingsTable(document.getElementById("search-rankings")?.value || "");
  renderPointsChart();
  renderWinnersChart();
  renderGroups();
  renderTeamSelect();
}

function setupEvViewToggle() {
  const toggle = document.getElementById("ev-view-toggle");
  if (!toggle) return;
  toggle.querySelectorAll(".ev-toggle-btn").forEach((btn) => {
    btn.disabled = btn.dataset.view === "current" && !state.hasCurrent;
    btn.addEventListener("click", () => applyEvView(btn.dataset.view));
  });
  applyEvView(state.evView);
}

async function init() {
  try {
    await loadData();
    document.getElementById("loading").classList.add("hidden");
    renderMeta();
    setupEvViewToggle();
    renderCalibration();
    renderMatches();
    setupTabs();
    setupSort();
    setupSearch();
    setupTychePanel();
    document.getElementById("team-select")?.addEventListener("change", (e) => {
      renderTeamDetail(e.target.value);
    });
    setupLogout();
    loadTycheData(true);
  } catch (err) {
    document.getElementById("loading").innerHTML = `
      <div class="error-banner" style="max-width:480px;text-align:left">
        <strong>Could not load data</strong><br>${err.message}
      </div>
    `;
  }
}

init();

function setupLogout() {
  const btn = document.getElementById("logout-btn");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    try {
      await fetch("/.netlify/functions/logout", { method: "POST", credentials: "same-origin" });
    } catch (_) {
      /* still redirect */
    }
    window.location.href = "/login.html";
  });
}
