const TYCHE_BASE = "https://api.tychemkt.com";
const JSON_HEADERS = {
  "Content-Type": "application/json",
  "Cache-Control": "private, no-store",
};

const CACHE_MS = 30_000;
let cache = { payload: null, expires: 0 };

const TEAM_ALIASES = {
  Czechia: "Czech Republic",
  Türkiye: "Turkey",
  Curacao: "Curaçao",
  USA: "United States",
};

function normaliseTeam(name) {
  return TEAM_ALIASES[name?.trim()] ?? name?.trim() ?? "";
}

function bestQuote(levels, side) {
  if (!levels?.length) return [null, null];
  let bestPrice = null;
  let bestQty = null;
  for (const level of levels) {
    const price = Number(level.price?.value);
    if (Number.isNaN(price)) continue;
    const qty = Number(level.quantity?.value ?? 0);
    if (bestPrice == null || (side === "bid" ? price > bestPrice : price < bestPrice)) {
      bestPrice = price;
      bestQty = qty;
    }
  }
  return [bestPrice, bestQty];
}

function round2(n) {
  return n == null ? null : Math.round(n * 100) / 100;
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
    const err = new Error(payload.message || res.statusText || `HTTP ${res.status}`);
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

function contractToItem(contract, marks, myPositions) {
  const meta = contract.metadata || {};
  const pos = myPositions[contract.id];
  const base = {
    contract_id: contract.id,
    title: contract.title,
    status: (contract.status || "").replace("CONTRACT_STATUS_", ""),
    mark: round2(marks[contract.id] ?? null),
    best_bid: null,
    best_ask: null,
    bid_qty: null,
    ask_qty: null,
    my_net: pos?.net ?? 0,
    my_cash: pos?.cash ?? 0,
    tyche_listed: true,
  };

  if (meta.kind === "multiplier") {
    return {
      ...base,
      kind: "match",
      home: normaliseTeam(meta.homeName),
      away: normaliseTeam(meta.awayName),
      kickoff: meta.kickoff,
      stage: meta.stage,
    };
  }

  return {
    ...base,
    kind: "team",
    team: contract.title,
    group: meta.group,
  };
}

async function fetchOrderBooks(cookie, contracts, batchSize = 12) {
  const books = new Map();
  for (let i = 0; i < contracts.length; i += batchSize) {
    const batch = contracts.slice(i, i + batchSize);
    const results = await Promise.allSettled(
      batch.map(async (contract) => {
        for (let attempt = 0; attempt < 2; attempt += 1) {
          try {
            const bookRes = await tycheCall(cookie, "QueryService", "GetOrderBook", {
              contractId: contract.id,
            });
            return [contract.id, bookRes.data.orderBook || {}];
          } catch (err) {
            if (attempt === 1) {
              console.warn(`GetOrderBook failed for ${contract.title}: ${err.message}`);
              return null;
            }
          }
        }
        return null;
      }),
    );
    for (const result of results) {
      if (result.status === "fulfilled" && result.value) {
        books.set(result.value[0], result.value[1]);
      }
    }
  }
  return books;
}

function applyOrderBook(item, book) {
  const [bid, bidQty] = bestQuote(book.bids, "bid");
  const [ask, askQty] = bestQuote(book.asks, "ask");
  item.best_bid = bid;
  item.best_ask = ask;
  item.bid_qty = bidQty;
  item.ask_qty = askQty;
}

async function fetchOpportunities(email, password) {
  const login = await tycheCall("", "AuthService", "Login", { email, password });
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

  const items = contracts.map((contract) => contractToItem(contract, marks, myPositions));
  const books = await fetchOrderBooks(cookie, contracts);
  for (const item of items) {
    const book = books.get(item.contract_id);
    if (book) applyOrderBook(item, book);
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
    items,
  };
}

function jsonResponse(statusCode, body) {
  return {
    statusCode,
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  };
}

export async function handler(event) {
  if (event.httpMethod && event.httpMethod !== "GET") {
    return jsonResponse(405, { error: "Method not allowed" });
  }

  const email = (process.env.TYCHE_EMAIL || "").trim();
  const password = (process.env.TYCHE_PASSWORD || "").trim();

  if (event.queryStringParameters?.ping === "1") {
    return jsonResponse(200, {
      ok: true,
      runtime: "lambda",
      has_email: !!email,
      has_password: !!password,
      node: process.version,
    });
  }

  if (!email || !password) {
    return jsonResponse(503, {
      error: "Tyche credentials not configured",
      hint: "Set TYCHE_EMAIL and TYCHE_PASSWORD in Netlify environment variables",
    });
  }

  const force = event.queryStringParameters?.refresh === "1";
  if (!force && cache.payload && Date.now() < cache.expires) {
    return jsonResponse(200, cache.payload);
  }

  try {
    const data = await fetchOpportunities(email, password);
    cache = { payload: data, expires: Date.now() + CACHE_MS };
    return jsonResponse(200, data);
  } catch (err) {
    console.error("tyche_opportunities failed:", err.message, err.code, err.status);
    const isAuth = err.status === 401 || err.code === "unauthenticated";
    return jsonResponse(502, {
      error: isAuth
        ? "Tyche login failed — check TYCHE_EMAIL and TYCHE_PASSWORD"
        : err.message || "Tyche fetch failed",
      code: err.code,
    });
  }
}

export default handler;
