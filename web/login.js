const form = document.getElementById("login-form");
const errorEl = document.getElementById("login-error");
const submitBtn = document.getElementById("login-submit");

function nextPath() {
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");
  if (!next || !next.startsWith("/") || next.startsWith("//")) {
    return "/";
  }
  return next;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorEl.hidden = true;
  submitBtn.disabled = true;
  submitBtn.textContent = "Signing in…";

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;

  try {
    const res = await fetch("/.netlify/functions/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    if (!res.ok) {
      let msg = "Invalid username or password";
      try {
        const data = await res.json();
        if (data.error) msg = data.error;
      } catch (_) {
        /* ignore */
      }
      errorEl.textContent = msg;
      errorEl.hidden = false;
      return;
    }

    window.location.href = nextPath();
  } catch {
    errorEl.textContent = "Could not reach the server. Try again.";
    errorEl.hidden = false;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Sign in";
  }
});
