/* Opti WC dashboard */

const API = {
  results: "./data/expected_points.json",
  resultsOdds: "./data/expected_points_odds_only.json",
  tournament: "./data/tournament.json",
  odds: "./data/odds_oddschecker.json",
};

let state = {
  results: null,
  resultsOdds: null,
  hasCompare: false,
  tournament: null,
  odds: null,
  teamToGroup: {},
  enriched: [],
  charts: {},
  sortKey: "expected_points",
  sortAsc: false,
  cmpSortKey: "pts_diff",
  cmpSortAsc: false,
};

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

function renderBreakdownTable(title, rows, subtotal) {
  const body = rows
    .map(
      (row) => `
      <tr>
        <td>${row.label}</td>
        <td class="num">${pct(row.prob)}</td>
        <td class="num">${row.ptsEach}</td>
        <td class="num pts">${fmtPts(row.expected)}</td>
      </tr>`,
    )
    .join("");

  return `
    <div class="breakdown-section">
      <h3>${title}</h3>
      <div class="table-scroll">
        <table class="data-table breakdown-table">
          <thead>
            <tr>
              <th>Outcome</th>
              <th>Probability</th>
              <th>Pts if…</th>
              <th>E[Pts]</th>
            </tr>
          </thead>
          <tbody>${body}</tbody>
          <tfoot>
            <tr>
              <td colspan="3">Subtotal</td>
              <td class="num pts">${fmtPts(subtotal)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
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
      `Group ${groupLetter} · E[Pts] = Σ (probability × points) for group finish, tournament exit, and entertainment bonus.`;

    const barTotal = bd.total || 1;
    const barHtml = `
      <div class="breakdown-bar" aria-hidden="true">
        <div class="breakdown-bar-seg group" style="width:${(bd.groupTotal / barTotal) * 100}%" title="Group: ${fmtPts(bd.groupTotal)}"></div>
        <div class="breakdown-bar-seg stage" style="width:${(bd.stageTotal / barTotal) * 100}%" title="Tournament: ${fmtPts(bd.stageTotal)}"></div>
        <div class="breakdown-bar-seg bonus" style="width:${Math.max((bd.bonusTotal / barTotal) * 100, bd.bonusTotal > 0 ? 2 : 0)}%" title="Bonus: ${fmtPts(bd.bonusTotal)}"></div>
      </div>
      <div class="breakdown-bar-legend">
        <span><i class="swatch group"></i> Group ${fmtPts(bd.groupTotal)}</span>
        <span><i class="swatch stage"></i> Tournament ${fmtPts(bd.stageTotal)}</span>
        <span><i class="swatch bonus"></i> Bonus ${fmtPts(bd.bonusTotal)}</span>
        <span class="breakdown-total">Total ${fmtPts(bd.total)}</span>
      </div>`;

    const groupMatesHtml = mates.length
      ? `<p class="breakdown-mates">Also in Group ${groupLetter}: ${mates.join(", ")}</p>`
      : "";

    container.innerHTML = `
      ${groupMatesHtml}
      ${barHtml}
      ${renderBreakdownTable("Group stage finish", bd.groupRows, bd.groupTotal)}
      ${renderBreakdownTable("Tournament exit (final standing)", bd.stageRows, bd.stageTotal)}
      ${renderBreakdownTable("Entertainment bonus", [bd.bonusRow], bd.bonusTotal)}
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

  state.results = results;
  state.resultsOdds = resultsOdds;
  state.hasCompare = !!resultsOdds;
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

  state.enriched = results.teams.map((row, i) => {
    const oddsRow = oddsByTeam[row.team];
    const epMl = row.expected_points;
    const epOdds = oddsRow?.expected_points ?? null;
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
      pts_diff: epOdds != null ? epMl - epOdds : null,
      p_champion_ml: pwMl,
      p_champion_odds: pwOdds,
      pw_diff: pwOdds != null ? pwMl - pwOdds : null,
      odds_row: oddsRow,
    };
  });
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
  document.getElementById("meta").innerHTML = `
    <div>${r.n_simulations.toLocaleString()} simulations</div>
    <div>${r.use_ml !== false ? "ML + Oddschecker" : "Oddschecker only"}</div>
    ${compareNote}
  `;
  document.getElementById("footer-sources").textContent =
    "Odds: " + r.odds_sources.join(" · ");
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
    .map(
      (r) => `
    <tr data-team="${r.team}">
      <td class="rank-cell">${r.rank}</td>
      <td class="team-cell">${r.team}</td>
      <td>${r.group}</td>
      <td><strong>${fmtPts(r.expected_points_ml)}</strong></td>
      <td>${fmtPts(r.expected_points_odds)}</td>
      <td>${fmtDiff(r.pts_diff)}</td>
      <td class="pct ${r.p_champion > 0.08 ? "pct-high" : ""}">${pct(r.p_champion)}</td>
      <td class="pct">${pct(r.p_semi_final)}</td>
      <td class="pct">${pct(r.p_quarter_final)}</td>
      <td class="pct">${pct(r.p_round_of_16)}</td>
      <td class="pct">${pct(r.p_round_of_32)}</td>
      <td class="pct">${pct(r.p_group_1)}</td>
      <td class="pct">${pct(r.p_bonus_goals)}</td>
    </tr>`
    )
    .join("");

  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => selectTeam(tr.dataset.team, "teams"));
  });
}

function renderPointsChart() {
  destroyChart("points");
  const top = state.enriched.slice(0, 20);
  const ctx = document.getElementById("chart-points");
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
    .sort((a, b) => b.p_champion - a.p_champion)
    .slice(0, 12);
  const ctx = document.getElementById("chart-winners");
  const datasets = [
    {
      label: "P(Champion) ML",
      data: top.map((t) => t.p_champion_ml * 100),
      backgroundColor: "#3dd68c",
      borderRadius: 4,
    },
  ];
  if (state.hasCompare) {
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
  sel.innerHTML = state.enriched
    .map((r) => `<option value="${r.team}">${r.team} (Group ${r.group})</option>`)
    .join("");
  sel.addEventListener("change", () => renderTeamDetail(sel.value));
  renderTeamDetail(sel.value);
}

function renderTeamDetail(teamName) {
  const r = state.enriched.find((t) => t.team === teamName);
  if (!r) return;

  const compareStats = state.hasCompare
    ? `
      <div class="stat"><div class="stat-label">E[Pts] odds</div><div class="stat-value">${fmtPts(r.expected_points_odds)}</div></div>
      <div class="stat"><div class="stat-label">Δ E[Pts]</div><div class="stat-value">${r.pts_diff != null ? (r.pts_diff > 0 ? "+" : "") + r.pts_diff.toFixed(1) : "—"}</div></div>
      <div class="stat"><div class="stat-label">P(Win) odds</div><div class="stat-value">${pct(r.p_champion_odds)}</div></div>
    `
    : "";

  document.getElementById("team-summary").innerHTML = `
    <div class="stat-grid">
      <div class="stat"><div class="stat-label">E[Pts] ML</div><div class="stat-value accent">${fmtPts(r.expected_points_ml)}</div></div>
      <div class="stat"><div class="stat-label">Group ${r.group}</div><div class="stat-value">#${r.rank_ml}</div></div>
      <div class="stat"><div class="stat-label">P(Win) ML</div><div class="stat-value">${pct(r.p_champion_ml)}</div></div>
      <div class="stat"><div class="stat-label">OC winner</div><div class="stat-value">${r.oc_odds ?? "—"}</div></div>
      ${compareStats}
    </div>
  `;

  renderPointsBreakdown(r);

  destroyChart("funnel");
  state.charts.funnel = new Chart(document.getElementById("chart-funnel"), {
    type: "bar",
    data: {
      labels: FUNNEL_KEYS.map((f) => f.label),
      datasets: [
        {
          label: "ML model",
          data: FUNNEL_KEYS.map((f) => r[f.key] * 100),
          backgroundColor: "#3dd68c",
          borderRadius: 6,
        },
        ...(state.hasCompare && r.odds_row
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
          data: [r.p_group_1, r.p_group_2, r.p_group_3, r.p_group_4].map((x) => x * 100),
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

  const stages = STAGE_ORDER.filter((s) => r.stage_probs?.[s] > 0.001).map((s) => ({
    label: s,
    value: r.stage_probs[s] * 100,
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

  grid.innerHTML = Object.entries(state.tournament.groups)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([g, teams]) => {
      const sorted = [...teams].sort(
        (a, b) => (byTeam[b]?.expected_points_ml || 0) - (byTeam[a]?.expected_points_ml || 0)
      );
      return `
      <div class="group-card">
        <div class="group-header">Group ${g}<span>ML E[Pts]</span></div>
        ${sorted
          .map((t) => {
            const r = byTeam[t];
            const oddsPts = r?.expected_points_odds != null ? fmtPts(r.expected_points_odds) : null;
            return `
          <div class="group-team" data-team="${t}">
            <span class="group-team-name">${t}</span>
            <span class="group-team-pts">
              ${r ? fmtPts(r.expected_points_ml) : "—"}
              ${oddsPts ? `<span class="group-team-pts-sub">${oddsPts}</span>` : ""}
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
    });
  });
}

function setupSort() {
  document.querySelectorAll("#rankings-table th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) state.sortAsc = !state.sortAsc;
      else {
        state.sortKey = key;
        state.sortAsc = key === "team" || key === "group";
      }
      renderRankingsTable(document.getElementById("search-rankings").value);
    });
  });

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

async function init() {
  try {
    await loadData();
    document.getElementById("loading").classList.add("hidden");
    renderMeta();
    renderRankingsTable();
    renderPointsChart();
    renderWinnersChart();
    renderTeamSelect();
    renderGroups();
    renderCalibration();
    renderMatches();
    setupTabs();
    setupSort();
    setupSearch();
    setupLogout();
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
