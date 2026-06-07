import crypto from "crypto";

const COOKIE_NAME = "wc_auth";
const TTL_SECONDS = 60 * 60 * 24 * 7; // 7 days

function hmacHex(secret, payload) {
  return crypto.createHmac("sha256", secret).update(payload).digest("hex");
}

export function createToken(username, secret, ttlSeconds = TTL_SECONDS) {
  const exp = Math.floor(Date.now() / 1000) + ttlSeconds;
  const payload = `${exp}:${username}`;
  const sig = hmacHex(secret, payload);
  return `${payload}:${sig}`;
}

export function verifyToken(token, secret) {
  if (!token || !secret) return null;
  const parts = token.split(":");
  if (parts.length !== 3) return null;
  const [exp, username, sig] = parts;
  const payload = `${exp}:${username}`;
  if (sig !== hmacHex(secret, payload)) return null;
  if (Number(exp) < Math.floor(Date.now() / 1000)) return null;
  return username;
}

export function parseCookies(header) {
  const out = {};
  if (!header) return out;
  for (const part of header.split(";")) {
    const [rawKey, ...rest] = part.trim().split("=");
    if (!rawKey) continue;
    out[rawKey] = decodeURIComponent(rest.join("="));
  }
  return out;
}

export function authCookie(token, maxAge = TTL_SECONDS) {
  return `${COOKIE_NAME}=${encodeURIComponent(token)}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${maxAge}`;
}

export function clearAuthCookie() {
  return `${COOKIE_NAME}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0`;
}

export { COOKIE_NAME };
