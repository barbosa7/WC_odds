import { clearAuthCookie } from "./_auth.mjs";

export async function handler(event) {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method not allowed" };
  }

  return {
    statusCode: 200,
    headers: {
      "Content-Type": "application/json",
      "Set-Cookie": clearAuthCookie(),
    },
    body: JSON.stringify({ ok: true }),
  };
}
