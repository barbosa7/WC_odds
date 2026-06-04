/* Opti WC dashboard */

const API = {
  results: "./data/expected_points.json",
  tournament: "./data/tournament.json",
  odds: "./data/odds_oddschecker.json",
};

let state = {
  results: null,
  tournament: null,
  odds: null,
  teamToGroup: {},
  enriched: [],
  charts: {},
  sortKey: "expected_points",
  sortAsc: false,
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

const FUNNEL_KEYS = [
  { key: "p_round_of_32", label: "Round of 32" },
  { key: "p_round_of_16", label: "Round of 16" },
  { key: "p_quarter_final", label: "Quarter-finals" },
  { key: "p_semi_final", label: "Semi-finals" },
  { key: "p_champion", label: "Win tournament" },
];

async function loadData() {
  const [results, tournament, odds] = await Promise.all([
    fetch(API.results).then((r) => {
      if (!r.ok) throw new Error("Missing simulation output — run python run.py first");
      return r.json();
    }),
    fetch(API.tournament).then((r) => r.json()),
    fetch(API.odds).then((r) => r.json()),
  ]);
  state.results = results;
  state.tournament = tournament;
  state.odds = odds;
  state.teamToGroup = {};
  for (const [g, teams] of Object.entries(tournament.groups)) {
    for (const t of teams) state.teamToGroup[t] = g;
  }
  state.enriched = results.teams.map((row, i) => ({
    ...row,
    rank: i + 1,
    group: state.teamToGroup[row.team] || "—",
    oc_odds: results.outright_input?.[row.team] ?? null,
    implied_win: results.outright_input?.[row.team]
      ? 100 / results.outright_input[row.team]
      : null,
  }));
}

function pct(v, digits = 1) {
  if (v == null || isNaN(v)) return "—";
  return (v * 100).toFixed(digits) + "%";
}

function fmtPts(v) {
  return Number(v).toFixed(1);
}

function destroyChart(id) {
  if (state.charts[id]) {
    state.charts[id].destroy();
    delete state.charts[id];
  }
}

function renderMeta() {
  const r = state.results;
  document.getElementById("meta").innerHTML = `
    <div>${r.n_simulations.toLocaleString()} simulations</div>
    <div>Seed · 42</div>
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
      <td><strong>${fmtPts(r.expected_points)}</strong></td>
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
  state.charts.points = new Chart(ctx, {
    type: "bar",
    data: {
      labels: top.map((t) => t.team),
      datasets: [
        {
          label: "Expected points",
          data: top.map((t) => t.expected_points),
          backgroundColor: top.map((_, i) =>
            i === 0 ? "#3dd68c" : `rgba(61, 214, 140, ${0.55 - i * 0.02})`
          ),
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
  state.charts.winners = new Chart(ctx, {
    type: "bar",
    data: {
      labels: top.map((t) => t.team),
      datasets: [
        {
          label: "P(Champion)",
          data: top.map((t) => t.p_champion * 100),
          backgroundColor: "#5b9cf5",
          borderRadius: 4,
        },
        {
          label: "Implied (OC)",
          data: top.map((t) => t.implied_win ?? 0),
          backgroundColor: "rgba(167, 139, 250, 0.7)",
          borderRadius: 4,
        },
      ],
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
          max: Math.ceil(Math.max(...top.map((t) => Math.max(t.p_champion * 100, t.implied_win || 0))) + 2),
        },
        x: { grid: { display: false } },
      },
    },
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

  document.getElementById("team-summary").innerHTML = `
    <div class="stat-grid">
      <div class="stat"><div class="stat-label">Expected pts</div><div class="stat-value accent">${fmtPts(r.expected_points)}</div></div>
      <div class="stat"><div class="stat-label">Group ${r.group}</div><div class="stat-value">#${r.rank}</div></div>
      <div class="stat"><div class="stat-label">P(Win)</div><div class="stat-value">${pct(r.p_champion)}</div></div>
      <div class="stat"><div class="stat-label">OC winner</div><div class="stat-value">${r.oc_odds ?? "—"}</div></div>
    </div>
  `;

  destroyChart("funnel");
  state.charts.funnel = new Chart(document.getElementById("chart-funnel"), {
    type: "bar",
    data: {
      labels: FUNNEL_KEYS.map((f) => f.label),
      datasets: [
        {
          label: "Probability",
          data: FUNNEL_KEYS.map((f) => r[f.key] * 100),
          backgroundColor: ["#252d3a", "#2f3a4a", "#3a4a5c", "#5b9cf5", "#3dd68c"],
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
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
          label: "% of simulations",
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
        (a, b) => (byTeam[b]?.expected_points || 0) - (byTeam[a]?.expected_points || 0)
      );
      return `
      <div class="group-card">
        <div class="group-header">Group ${g}<span>by E[Pts]</span></div>
        ${sorted
          .map((t) => {
            const r = byTeam[t];
            return `
          <div class="group-team" data-team="${t}">
            <span class="group-team-name">${t}</span>
            <span class="group-team-pts">${r ? fmtPts(r.expected_points) : "—"}</span>
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
          label: "Teams",
          data: withOdds.map((r) => ({
            x: r.implied_win,
            y: r.p_champion * 100,
            team: r.team,
          })),
          backgroundColor: "#3dd68c",
          pointRadius: 6,
          pointHoverRadius: 9,
        },
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
        legend: { display: false },
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
        if (elems[0]?.datasetIndex === 0) {
          const pt = withOdds[elems[0].index];
          if (pt) selectTeam(pt.team);
        }
      },
    },
  });

  const gaps = withOdds
    .map((r) => ({
      ...r,
      gap: r.implied_win - r.p_champion * 100,
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
      <td>${pct(r.p_champion)}</td>
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
      if (tab.dataset.tab === "calibration") renderCalibration();
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
}

function setupSearch() {
  document.getElementById("search-rankings").addEventListener("input", (e) => {
    renderRankingsTable(e.target.value);
  });
  document.getElementById("search-matches").addEventListener("input", (e) => {
    renderMatches(e.target.value);
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
  } catch (err) {
    document.getElementById("loading").innerHTML = `
      <div class="error-banner" style="max-width:480px;text-align:left">
        <strong>Could not load data</strong><br>${err.message}
      </div>
    `;
  }
}

init();
