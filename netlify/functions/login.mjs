import {
  authCookie,
  createToken,
} from "./_auth.mjs";

const JSON_HEADERS = { "Content-Type": "application/json" };

export async function handler(event) {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, headers: JSON_HEADERS, body: JSON.stringify({ error: "Method not allowed" }) };
  }

  const secret = process.env.AUTH_SECRET;
  const expectedUser = process.env.SITE_USER;
  const expectedPass = process.env.SITE_PASSWORD;

  if (!secret || !expectedUser || !expectedPass) {
    return {
      statusCode: 503,
      headers: JSON_HEADERS,
      body: JSON.stringify({ error: "Login is not configured on this site." }),
    };
  }

  let body;
  try {
    body = JSON.parse(event.body || "{}");
  } catch {
    return { statusCode: 400, headers: JSON_HEADERS, body: JSON.stringify({ error: "Invalid request" }) };
  }

  const username = String(body.username || "").trim();
  const password = String(body.password || "");

  if (username !== expectedUser || password !== expectedPass) {
    return { statusCode: 401, headers: JSON_HEADERS, body: JSON.stringify({ error: "Invalid username or password" }) };
  }

  const token = createToken(username, secret);
  return {
    statusCode: 200,
    headers: {
      ...JSON_HEADERS,
      "Set-Cookie": authCookie(token),
    },
    body: JSON.stringify({ ok: true }),
  };
}
