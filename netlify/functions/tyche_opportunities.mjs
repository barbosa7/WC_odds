import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TYCHE_BASE = "https://api.tychemkt.com";
const JSON_HEADERS = {
  "Content-Type": "application/json",
  "Cache-Control": "private, no-store",
};

const TEAM_ALIASES = {
  Czechia: "Czech Republic",
  Türkiye: "Turkey",
  Curacao: "Curaçao",
  USA: "United States",
};

function normaliseTeam(name) {
  return TEAM_ALIASES[name?.trim()] ?? name?.trim() ?? "";
}

function readJson(name) {
  const p = path.join(__dirname, "data", name);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

async function fetchJsonFromSite(siteUrl, siteCookie, name) {
  if (!siteUrl) return null;
  const headers = siteCookie ? { Cookie: siteCookie } : {};
  const res = await fetch(`${siteUrl.replace(/\/$/, "")}/data/${name}`, { headers });
  if (!res.ok) return null;
  return res.json();
}

async function loadTheos(siteUrl, siteCookie) {
  let teamPre = readJson("expected_points.json");
  let teamCurrent = readJson("expected_points_current.json");
  let matchRows = readJson("match_events_predictions.json");

  if (!teamPre?.teams && siteUrl) {
    teamPre = await fetchJsonFromSite(siteUrl, siteCookie, "expected_points.json");
  }
  if (!teamCurrent?.teams && siteUrl) {
    teamCurrent = await fetchJsonFromSite(siteUrl, siteCookie, "expected_points_current.json");
  }
  if (!Array.isArray(matchRows) && siteUrl) {
    matchRows = await fetchJsonFromSite(siteUrl, siteCookie, "match_events_predictions.json");
  }

  const theosPre = teamPre?.teams
    ? Object.fromEntries(teamPre.teams.map((r) => [r.team, Number(r.expected_points)]))
    : {};
  const theosCurrent = teamCurrent?.teams
    ? Object.fromEntries(teamCurrent.teams.map((r) => [r.team, Number(r.expected_points)]))
    : {};
  const matchTheos = new Map();
  if (Array.isArray(matchRows)) {
    for (const row of matchRows) {
      const home = normaliseTeam(row.home);
      const away = normaliseTeam(row.away);
      matchTheos.set(`${home}\0${away}`, Number(row.expected_gxcxc));
    }
  }

  return { theosPre, theosCurrent, matchTheos };
}

async function mapInBatches(items, batchSize, fn) {
  const out = [];
  for (let i = 0; i < items.length; i += batchSize) {
    const batch = items.slice(i, i + batchSize);
    out.push(...(await Promise.all(batch.map(fn))));
  }
  return out;
}

function bestLevel(levels) {
  if (!levels?.length) return [null, null];
  const top = levels[0];
  return [Number(top.price?.value), Number(top.quantity?.value ?? 0)];
}

function round2(n) {
  return n == null ? null : Math.round(n * 100) / 100;
}

function computeEdges(theo, bid, ask) {
  const buyEdge = theo != null && ask != null ? theo - ask : null;
  const sellEdge = theo != null && bid != null ? bid - theo : null;
  let side = null;
  let edge = null;
  if (buyEdge != null && buyEdge > 0 && (sellEdge == null || sellEdge <= 0 || buyEdge >= sellEdge)) {
    side = "buy";
    edge = buyEdge;
  } else if (sellEdge != null && sellEdge > 0) {
    side = "sell";
    edge = sellEdge;
  } else if (buyEdge != null || sellEdge != null) {
    edge = Math.max(buyEdge ?? -Infinity, sellEdge ?? -Infinity);
  }
  return {
    buy_edge: round2(buyEdge),
    sell_edge: round2(sellEdge),
    side,
    edge: round2(edge),
  };
}

function buildItem({
  kind,
  contract,
  theoPre,
  theoCurrent,
  mark,
  bid,
  ask,
  bidQty,
  askQty,
  myPosition,
  extra = {},
}) {
  const pre = computeEdges(theoPre, bid, ask);
  const cur = computeEdges(theoCurrent, bid, ask);
  return {
    kind,
    contract_id: contract.id,
    title: contract.title,
    status: (contract.status || "").replace("CONTRACT_STATUS_", ""),
    theo_pre: round2(theoPre),
    theo_current: round2(theoCurrent),
    mark: round2(mark),
    best_bid: bid,
    best_ask: ask,
    bid_qty: bidQty,
    ask_qty: askQty,
    buy_edge_pre: pre.buy_edge,
    sell_edge_pre: pre.sell_edge,
    side_pre: pre.side,
    edge_pre: pre.edge,
    buy_edge_current: cur.buy_edge,
    sell_edge_current: cur.sell_edge,
    side_current: cur.side,
    edge_current: cur.edge,
    my_net: myPosition?.net ?? 0,
    my_cash: myPosition?.cash ?? 0,
    ...extra,
  };
}

async function tycheCall(cookieJar, service, method, body = {}) {
  const headers = {
    "Content-Type": "application/json",
    "Connect-Protocol-Version": "1",
  };
  if (cookieJar) headers.Cookie = cookieJar;

  const res = await fetch(`${TYCHE_BASE}/tyche.v1.${service}/${method}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  const setCookie = res.headers.get("set-cookie");
  let newCookie = cookieJar;
  if (setCookie) {
    const m = setCookie.match(/tyche_session=([^;]+)/);
    if (m) newCookie = `tyche_session=${m[1]}`;
  }

  const payload = res.headers.get("content-type")?.includes("json")
    ? await res.json()
    : {};

  if (!res.ok) {
    const err = new Error(payload.message || res.statusText);
    err.code = payload.code || "unknown";
    err.status = res.status;
    throw err;
  }

  return { data: payload, cookie: newCookie };
}

function relevantContracts(contracts) {
  return contracts.filter((contract) => {
    const meta = contract.metadata || {};
    if (meta.kind === "total") return false;
    if (meta.kind === "multiplier") return true;
    return (contract.description || "").includes("finish value");
  });
}

async function fetchOpportunities(email, password, { siteUrl = "", siteCookie = "" } = {}) {
  const [{ theosPre, theosCurrent, matchTheos }, login] = await Promise.all([
    loadTheos(siteUrl, siteCookie),
    tycheCall("", "AuthService", "Login", { email, password }),
  ]);
  let cookie = login.cookie;
  const user = login.data.user;

  const eventsRes = await tycheCall(cookie, "QueryService", "ListEvents", {
    page: { pageSize: 10 },
  });
  cookie = eventsRes.cookie;
  const events = eventsRes.data.events || [];
  if (!events.length) throw new Error("No Tyche events found");
  const event = events[0];

  const contractsRes = await tycheCall(cookie, "QueryService", "ListContracts", {
    eventId: event.id,
    page: { pageSize: 500 },
  });
  cookie = contractsRes.cookie;
  const contracts = relevantContracts(contractsRes.data.contracts || []);

  const [marksRes, posRes] = await Promise.all([
    tycheCall(cookie, "QueryService", "ListContractMarks", { eventId: event.id }),
    tycheCall(cookie, "QueryService", "ListPositions", {
      eventId: event.id,
      userId: user.id,
      page: { pageSize: 500 },
    }),
  ]);
  cookie = posRes.cookie || marksRes.cookie || cookie;
  const marks = Object.fromEntries(
    (marksRes.data.marks || []).map((m) => [m.contractId, Number(m.price?.value)]),
  );

  const myPositions = {};
  for (const row of posRes.data.positions || []) {
    const net = Number(row.netQuantity?.value ?? 0);
    if (!net) continue;
    myPositions[row.contractId] = {
      net,
      cash: Number(row.cash?.value ?? 0),
      trade_count: Number(row.tradeCount ?? 0),
    };
  }

  const books = await mapInBatches(contracts, 20, async (contract) => {
    const bookRes = await tycheCall(cookie, "QueryService", "GetOrderBook", {
      contractId: contract.id,
    });
    return { contract, book: bookRes.data.orderBook || {} };
  });

  const items = [];
  for (const { contract, book } of books) {
    const meta = contract.metadata || {};
    const [bid, bidQty] = bestLevel(book.bids);
    const [ask, askQty] = bestLevel(book.asks);
    const mark = marks[contract.id] ?? null;
    const raw = {
      id: contract.id,
      title: contract.title,
      description: contract.description,
      status: contract.status,
      metadata: meta,
    };

    if (meta.kind === "multiplier") {
      const home = normaliseTeam(meta.homeName);
      const away = normaliseTeam(meta.awayName);
      const theo = matchTheos.get(`${home}\0${away}`) ?? null;
      items.push(
        buildItem({
          kind: "match",
          contract: raw,
          theoPre: theo,
          theoCurrent: theo,
          mark,
          bid,
          ask,
          bidQty,
          askQty,
          myPosition: myPositions[contract.id],
          extra: { home, away, kickoff: meta.kickoff, stage: meta.stage },
        }),
      );
    } else {
      const team = contract.title;
      items.push(
        buildItem({
          kind: "team",
          contract: raw,
          theoPre: theosPre[team] ?? null,
          theoCurrent: theosCurrent[team] ?? null,
          mark,
          bid,
          ask,
          bidQty,
          askQty,
          myPosition: myPositions[contract.id],
          extra: { team, group: meta.group },
        }),
      );
    }
  }

  return {
    fetched_at: new Date().toISOString(),
    live: true,
    account: {
      id: user.id,
      name: user.name,
      email: user.email,
      open_positions: Object.keys(myPositions).length,
    },
    event: {
      id: event.id,
      title: event.title,
      slug: event.slug,
      status: (event.status || "").replace("EVENT_STATUS_", ""),
    },
    sources: {
      theo_pre: "netlify/functions/data/expected_points.json",
      theo_current: fs.existsSync(path.join(__dirname, "data", "expected_points_current.json"))
        ? "netlify/functions/data/expected_points_current.json"
        : null,
      match_theo: fs.existsSync(path.join(__dirname, "data", "match_events_predictions.json"))
        ? "netlify/functions/data/match_events_predictions.json"
        : null,
    },
    items,
  };
}

export async function handler(event) {
  if (event.httpMethod && event.httpMethod !== "GET") {
    return {
      statusCode: 405,
      headers: JSON_HEADERS,
      body: JSON.stringify({ error: "Method not allowed" }),
    };
  }

  const email = process.env.TYCHE_EMAIL || "";
  const password = process.env.TYCHE_PASSWORD || "";
  if (!email || !password) {
    return {
      statusCode: 503,
      headers: JSON_HEADERS,
      body: JSON.stringify({
        error: "Tyche credentials not configured",
        hint: "Set TYCHE_EMAIL and TYCHE_PASSWORD in Netlify environment variables",
      }),
    };
  }

  const siteUrl =
    process.env.URL || process.env.DEPLOY_PRIME_URL || process.env.DEPLOY_URL || "";
  const siteCookie = event.headers?.cookie || event.headers?.Cookie || "";

  try {
    const data = await fetchOpportunities(email, password, { siteUrl, siteCookie });
    return {
      statusCode: 200,
      headers: JSON_HEADERS,
      body: JSON.stringify(data),
    };
  } catch (err) {
    const isAuth = err.status === 401 || err.code === "unauthenticated";
    return {
      statusCode: isAuth ? 502 : 502,
      headers: JSON_HEADERS,
      body: JSON.stringify({
        error: isAuth
          ? "Tyche login failed — check TYCHE_EMAIL and TYCHE_PASSWORD"
          : err.message || "Tyche fetch failed",
        code: err.code,
      }),
    };
  }
}
