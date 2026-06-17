const COOKIE_NAME = "wc_auth";

const PUBLIC_PATHS = new Set([
  "/login.html",
  "/login.js",
  "/login.css",
  "/favicon.ico",
]);

const PUBLIC_PREFIXES = [
  "/.netlify/functions/login",
  "/.netlify/functions/logout",
];

function isPublic(pathname) {
  if (PUBLIC_PATHS.has(pathname)) return true;
  return PUBLIC_PREFIXES.some((p) => pathname.startsWith(p));
}

async function hmacHex(secret, message) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function parseCookies(header) {
  const out = {};
  if (!header) return out;
  for (const part of header.split(";")) {
    const [rawKey, ...rest] = part.trim().split("=");
    if (!rawKey) continue;
    out[rawKey] = decodeURIComponent(rest.join("="));
  }
  return out;
}

async function verifyToken(token, secret) {
  if (!token || !secret) return null;
  const parts = token.split(":");
  if (parts.length !== 3) return null;
  const [exp, username, sig] = parts;
  const payload = `${exp}:${username}`;
  const expected = await hmacHex(secret, payload);
  if (sig !== expected) return null;
  if (Number(exp) < Math.floor(Date.now() / 1000)) return null;
  return username;
}

export default async (request, context) => {
  const url = new URL(request.url);
  const { pathname } = url;

  if (isPublic(pathname)) {
    return context.next();
  }

  const secret = Netlify.env.get("AUTH_SECRET");
  if (!secret) {
    return context.next();
  }

  const cookies = parseCookies(request.headers.get("cookie"));
  const user = await verifyToken(cookies[COOKIE_NAME], secret);

  if (user) {
    return context.next();
  }

  if (pathname.startsWith("/data/") || pathname.startsWith("/api/")) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const next = encodeURIComponent(pathname + url.search);
  return Response.redirect(`${url.origin}/login.html?next=${next}`, 302);
};
