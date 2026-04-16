/* auth.js — Login / Registration logic */

const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:5000" : "";

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

// Auto-redirect if already logged in
(async function checkSession() {
  try {
    const res = await fetch(apiUrl("/api/auth/me"), { credentials: "include" });
    if (res.ok) window.location.href = apiUrl("/dashboard");
  } catch (_) {}
})();


/* ─── Tab switching ──────────────────────────────────────────────────── */
function switchTab(tab) {
  const loginForm  = document.getElementById("login-form");
  const regForm    = document.getElementById("register-form");
  const tabLogin   = document.getElementById("tab-login");
  const tabReg     = document.getElementById("tab-register");

  if (tab === "login") {
    loginForm.classList.remove("hidden");
    regForm.classList.add("hidden");
    tabLogin.classList.add("active");
    tabReg.classList.remove("active");
  } else {
    regForm.classList.remove("hidden");
    loginForm.classList.add("hidden");
    tabReg.classList.add("active");
    tabLogin.classList.remove("active");
  }
}


/* ─── Helper ─────────────────────────────────────────────────────────── */
function setLoading(btnId, spinnerId, isLoading) {
  const btn     = document.getElementById(btnId);
  const spinner = document.getElementById ? document.querySelector(`#${btnId} .btn-spinner`) : null;
  const text    = btn.querySelector(".btn-text");
  const sp      = btn.querySelector(".btn-spinner");

  btn.disabled = isLoading;
  if (text) text.style.display = isLoading ? "none" : "";
  if (sp)   sp.classList.toggle("hidden", !isLoading);
}

function showError(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.classList.remove("hidden");
}

function hideError(id) {
  document.getElementById(id).classList.add("hidden");
}


/* ─── Login ──────────────────────────────────────────────────────────── */
async function handleLogin(event) {
  event.preventDefault();
  hideError("login-error");

  const email    = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;

  const btn = document.getElementById("login-btn");
  btn.disabled = true;
  const text = btn.querySelector(".btn-text");
  const sp   = btn.querySelector(".btn-spinner");
  text.textContent = "Logging in...";
  sp.classList.remove("hidden");

  try {
    const res  = await fetch(apiUrl("/api/auth/login"), {
      method:      "POST",
      credentials: "include",
      headers:     { "Content-Type": "application/json" },
      body:        JSON.stringify({ email, password }),
    });
    const data = await res.json();

    if (!res.ok) {
      showError("login-error", data.error || "Login failed. Please try again.");
    } else {
      window.location.href = apiUrl("/dashboard");
    }
  } catch (err) {
    showError("login-error", "Network error. Is the server running?");
  } finally {
    btn.disabled = false;
    text.textContent = "Login to Dashboard";
    sp.classList.add("hidden");
  }
}


/* ─── Register ───────────────────────────────────────────────────────── */
async function handleRegister(event) {
  event.preventDefault();
  hideError("reg-error");

  const name      = document.getElementById("reg-name").value.trim();
  const email     = document.getElementById("reg-email").value.trim();
  const password  = document.getElementById("reg-password").value;

  if (password.length < 6) {
    showError("reg-error", "Password must be at least 6 characters long.");
    return;
  }

  const btn  = document.getElementById("reg-btn");
  btn.disabled = true;
  const text = btn.querySelector(".btn-text");
  const sp   = btn.querySelector(".btn-spinner");
  text.textContent = "Creating account...";
  sp.classList.remove("hidden");

  try {
    const res  = await fetch(apiUrl("/api/auth/register"), {
      method:      "POST",
      credentials: "include",
      headers:     { "Content-Type": "application/json" },
      body:        JSON.stringify({ name, email, password }),
    });
    const data = await res.json();

    if (!res.ok) {
      showError("reg-error", data.error || "Registration failed. Please try again.");
    } else {
      window.location.href = apiUrl("/dashboard");
    }
  } catch (err) {
    showError("reg-error", "Network error. Is the server running?");
  } finally {
    btn.disabled = false;
    text.textContent = "Create Account";
    sp.classList.add("hidden");
  }
}
