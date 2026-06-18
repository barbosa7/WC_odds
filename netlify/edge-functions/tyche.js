const TYCHE_BASE = "https://api.tychemkt.com";
const JSON_HEADERS = {
  "Content-Type": "application/json",
  "Cache-Control": "private, no-store",
};
const CACHE_MS = 45_000;

const TEAM_ALIASES = {
  Czechia: "Czech Republic",
  Türkiye: "Turkey",
  Curacao: "Curaçao",
  USA: "United States",
};

let cache = { payload: null, expires: 0 };

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

function normaliseTeam(name) {
  return TEAM_ALIASES[name?.trim()] ?? name?.trim() ?? "";
}

function bestLevel(levels) {
  if (!levels?.length) return [null, null];
  const top = levels[0];
  return [Number(top.price?.value), Number(top.quantity?.value ?? 0)];
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

  const bookResults = await Promise.allSettled(
    contracts.map(async (contract) => {
      const bookRes = await tycheCall(cookie, "QueryService", "GetOrderBook", {
        contractId: contract.id,
      });
      return { contract, book: bookRes.data.orderBook || {} };
    }),
  );

  const items = [];
  for (const result of bookResults) {
    if (result.status !== "fulfilled") continue;
    const { contract, book } = result.value;
    const meta = contract.metadata || {};
    const [bid, bidQty] = bestLevel(book.bids);
    const [ask, askQty] = bestLevel(book.asks);
    const pos = myPositions[contract.id];

    if (meta.kind === "multiplier") {
      items.push({
        kind: "match",
        contract_id: contract.id,
        title: contract.title,
        status: (contract.status || "").replace("CONTRACT_STATUS_", ""),
        mark: round2(marks[contract.id] ?? null),
        best_bid: bid,
        best_ask: ask,
        bid_qty: bidQty,
        ask_qty: askQty,
        my_net: pos?.net ?? 0,
        my_cash: pos?.cash ?? 0,
        home: normaliseTeam(meta.homeName),
        away: normaliseTeam(meta.awayName),
        kickoff: meta.kickoff,
        stage: meta.stage,
      });
    } else {
      items.push({
        kind: "team",
        contract_id: contract.id,
        title: contract.title,
        status: (contract.status || "").replace("CONTRACT_STATUS_", ""),
        mark: round2(marks[contract.id] ?? null),
        best_bid: bid,
        best_ask: ask,
        bid_qty: bidQty,
        ask_qty: askQty,
        my_net: pos?.net ?? 0,
        my_cash: pos?.cash ?? 0,
        team: contract.title,
        group: meta.group,
      });
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
    items,
  };
}

export default async (request) => {
  if (request.method !== "GET") {
    return json({ error: "Method not allowed" }, 405);
  }

  const url = new URL(request.url);
  const email = (Netlify.env.get("TYCHE_EMAIL") || "").trim();
  const password = (Netlify.env.get("TYCHE_PASSWORD") || "").trim();

  if (url.searchParams.get("ping") === "1") {
    return json({
      ok: true,
      runtime: "edge",
      has_email: !!email,
      has_password: !!password,
    });
  }

  if (!email || !password) {
    return json(
      {
        error: "Tyche credentials not configured",
        hint: "Set TYCHE_EMAIL and TYCHE_PASSWORD in Netlify environment variables",
      },
      503,
    );
  }

  const force = url.searchParams.get("refresh") === "1";
  if (!force && cache.payload && Date.now() < cache.expires) {
    return json(cache.payload);
  }

  try {
    const data = await fetchOpportunities(email, password);
    cache = { payload: data, expires: Date.now() + CACHE_MS };
    return json(data);
  } catch (err) {
    console.error("tyche edge failed:", err.message, err.code, err.status);
    const isAuth = err.status === 401 || err.code === "unauthenticated";
    return json(
      {
        error: isAuth
          ? "Tyche login failed — check TYCHE_EMAIL and TYCHE_PASSWORD"
          : err.message || "Tyche fetch failed",
        code: err.code,
      },
      502,
    );
  }
};
