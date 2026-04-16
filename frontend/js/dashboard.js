/* dashboard.js — Real-time dashboard logic */

// ─── State ────────────────────────────────────────────────────────────────────
let currentUser    = null;
let sensorInterval = null;
const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:5000" : "";

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

async function parseJsonSafe(res) {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { error: text };
  }
}

// Sensor config: [elementId, maxValue, unit, barId]
const SENSORS = [
  { key: "N",           label: "N",    unit: "kg/ha", valId: "val-N",    barId: "bar-N",    max: 140  },
  { key: "P",           label: "P",    unit: "kg/ha", valId: "val-P",    barId: "bar-P",    max: 145  },
  { key: "K",           label: "K",    unit: "kg/ha", valId: "val-K",    barId: "bar-K",    max: 205  },
  { key: "temperature", label: "Temp", unit: "°C",    valId: "val-temp", barId: "bar-temp", max: 44   },
  { key: "humidity",    label: "Hum",  unit: "%",     valId: "val-hum",  barId: "bar-hum",  max: 100  },
  { key: "ph",          label: "pH",   unit: "pH",    valId: "val-ph",   barId: "bar-ph",   max: 10   },
  { key: "rainfall",    label: "Rain", unit: "mm",    valId: "val-rain", barId: "bar-rain", max: 300  },
];

const CROP_EMOJI = {
  rice:        "", wheat:       "", maize:       "🌽", chickpea:    "🫘",
  kidneybeans: "🫘", pigeonpeas:  "🫛", mothbeans:   "🫘", mungbean:    "🟢",
  blackgram:   "🫘", lentil:      "🟤", pomegranate: "🍎", banana:      "🍌",
  mango:       "🥭", grapes:      "🍇", watermelon:  "🍉", muskmelon:   "🍈",
  apple:       "🍎", orange:      "🍊", papaya:      "🍐", coconut:     "🥥",
  cotton:      "🌸", jute:        "", coffee:      "☕",
};

function getCropEmoji(crop) {
  return CROP_EMOJI[(crop || "").toLowerCase()] || "";
}


// ─── Initialise ───────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  // Verify session
  try {
    const res = await fetch(apiUrl("/api/auth/me"), { credentials: "include" });
    if (!res.ok) { window.location.href = apiUrl("/"); return; }
    currentUser = await res.json();
  } catch {
    window.location.href = apiUrl("/");
    return;
  }

  // Populate UI with user info
  document.getElementById("user-name-sm").textContent  = currentUser.name;
  document.getElementById("user-region-sm").textContent = currentUser.region;
  document.getElementById("user-avatar").textContent   = currentUser.name.charAt(0).toUpperCase();

  // Sensor polling will start once Region is selected via startSensors()

  // Load history
  loadHistory();
});


// ─── Sensor Data ──────────────────────────────────────────────────────────────
async function fetchSensorData() {
  try {
    const res  = await fetch(apiUrl("/api/sensor/latest"), { credentials: "include" });
    if (!res.ok) return;
    const data = await res.json();
    updateSensorUI(data);
  } catch { /* Network hiccup — ignore */ }
}

function updateSensorUI(data) {
  SENSORS.forEach(({ key, valId, barId, max }) => {
    const val    = data[key];
    if (val === undefined || val === null) return;

    const valEl = document.getElementById(valId);
    const barEl = document.getElementById(barId);

    // Animate value change
    const prev = parseFloat(valEl.dataset.val || 0);
    if (Math.abs(prev - val) > 0.01) {
      valEl.parentElement.parentElement.classList.remove("updated");
      setTimeout(() => valEl.parentElement.parentElement.classList.add("updated"), 10);
    }
    valEl.textContent   = key === "ph" ? val.toFixed(2) : val.toFixed(1);
    valEl.dataset.val   = val;
    barEl.style.width   = `${Math.min((val / max) * 100, 100)}%`;
  });

  // Update source badge and status dot
  const source   = data.source || "simulated";
  const badge    = document.getElementById("sensor-source-badge");
  const dot      = document.getElementById("status-dot");
  const statusTx = document.getElementById("status-text");

  if (source === "mqtt") {
    badge.textContent   = " Live MQTT";
    dot.className       = "status-dot live";
    statusTx.textContent = "Live MQTT";
  } else {
    badge.textContent   = " Simulated";
    dot.className       = "status-dot simulated";
    statusTx.textContent = "Simulated";
  }

  // Timestamp
  const now = new Date();
  document.getElementById("last-updated").textContent =
    `Updated: ${now.toLocaleTimeString()}`;
}

function startSensors() {
  const region = document.getElementById("live-region").value.trim();
  const area = document.getElementById("live-area").value.trim();
  if (!region || !area) return;

  document.getElementById("refresh-btn").style.display = "flex";
  
  if (!sensorInterval) {
    fetchSensorData();
    sensorInterval = setInterval(fetchSensorData, 1000);  // Poll every 1 second for live updates
  }
}

async function refreshSensors() {
  const btn = document.getElementById("refresh-btn");
  btn.disabled = true;
  btn.textContent = " Refreshing...";
  try {
    await fetch(apiUrl("/api/sensor/refresh"), { method: "POST", credentials: "include" });
  } catch (err) {
    console.error(err);
  } finally {
    setTimeout(() => {
      btn.disabled = false;
      btn.textContent = " Simulate New Test";
    }, 1000);
  }
}


// ─── Recommendation ───────────────────────────────────────────────────────────
async function getRecommendation() {
  const btn      = document.getElementById("recommend-btn");
  const spinner  = document.getElementById("rec-spinner");
  const errEl    = document.getElementById("rec-error");
  const resultContainer = document.getElementById("result-container");
  const region   = document.getElementById("live-region").value.trim();
  const area     = document.getElementById("live-area").value.trim();

  errEl.classList.add("hidden");

  if (!region || !area) {
    errEl.textContent = "Please provide both Region and Area in the Live Sensors section.";
    errEl.classList.remove("hidden");
    return;
  }

  btn.disabled = true;
  spinner.classList.remove("hidden");
  btn.querySelector(".btn-text").textContent = "Analysing sensors...";
  btn.querySelector(".btn-icon").textContent = "";

  try {
    const res  = await fetch(apiUrl("/api/recommend"), {
      method:      "POST",
      credentials: "include",
      headers:     { "Content-Type": "application/json" },
      body:        JSON.stringify({ region: region, area: area }),
    });
    const data = await parseJsonSafe(res);

    if (!res.ok) {
      errEl.textContent = data.error || `Recommendation failed (${res.status}).`;
      errEl.classList.remove("hidden");
      return;
    }

    displayResult(data);
    // History is no longer implicitly refreshed here, it waits for saveRecommendation
  } catch (err) {
    errEl.textContent = `Network error: ${err?.message || "Failed to reach backend."}`;
    errEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    spinner.classList.add("hidden");
    btn.querySelector(".btn-text").textContent = "Get AI Recommendation";
    btn.querySelector(".btn-icon").textContent = "";
  }
}

function displayResult(data) {
  const container = document.getElementById("result-container");
  container.classList.remove("hidden");

  // Save globally for save button
  window.currentRecommendations = data.recommendations || [];
  
  const listEl = document.getElementById("result-list");
  listEl.innerHTML = window.currentRecommendations.map((crop, idx) => `
    <label class="result-card" style="display: block; cursor: pointer; border: 2px solid ${idx===0 ? 'var(--accent)' : 'var(--border-line)'}; border-radius: var(--radius-card); padding: 24px; transition: border-color 0.2s; position: relative;">
      <input type="radio" name="crop_selection" value="${idx}" ${idx===0 ? 'checked' : ''} style="position: absolute; right: 24px; top: 24px; transform: scale(1.2);">
      
      <div class="result-label">Recommended Option ${idx + 1}</div>
      <div class="result-crop-name" style="margin-bottom: 16px;">${crop.best_crop}</div>
      
      <div class="result-details-grid" style="margin-bottom: 0;">
        <div class="result-detail-item">
          <div class="detail-label">Why?</div>
          <div class="detail-value">${crop.reason}</div>
        </div>
        <div class="result-detail-item">
          <div class="detail-label">Harvest Duration</div>
          <div class="detail-value">${crop.harvest_duration}</div>
        </div>
        <div class="result-detail-item">
          <div class="detail-label">Suggested Planting</div>
          <div class="detail-value">${crop.planting_month}</div>
        </div>
        <div class="result-detail-item">
          <div class="detail-label">Expected Harvest</div>
          <div class="detail-value">${crop.harvest_month}</div>
        </div>
        <div class="result-detail-item">
          <div class="detail-label">Cost per Hectare</div>
          <div class="detail-value" style="font-weight:600; color:var(--text-primary);">${crop.planting_cost_per_hectare}</div>
        </div>
        <div class="result-detail-item">
          <div class="detail-label">Total Est. Cost</div>
          <div class="detail-value" style="font-weight:600; color:var(--text-primary);">${crop.total_cost}</div>
        </div>
      </div>
    </label>
  `).join("");

  // Add event listeners to stylize radio box borders when selected
  const radios = listEl.querySelectorAll('input[type="radio"]');
  radios.forEach(radio => {
    radio.addEventListener('change', (e) => {
      listEl.querySelectorAll('.result-card').forEach(card => card.style.borderColor = 'var(--border-line)');
      if(e.target.checked) e.target.closest('.result-card').style.borderColor = 'var(--accent)';
    });
  });

  // Sensor snapshot pills
  const snapshotEl = document.getElementById("result-sensor-snapshot");
  if (data.sensor_data) {
    const sd = data.sensor_data;
    snapshotEl.innerHTML = [
      `<span class="snapshot-pill"><strong>N:</strong> ${sd.N}</span>`,
      `<span class="snapshot-pill"><strong>P:</strong> ${sd.P}</span>`,
      `<span class="snapshot-pill"><strong>K:</strong> ${sd.K}</span>`,
      `<span class="snapshot-pill"><strong>Temp:</strong> ${sd.temperature}°C</span>`,
      `<span class="snapshot-pill"><strong>Humidity:</strong> ${sd.humidity}%</span>`,
      `<span class="snapshot-pill"><strong>pH:</strong> ${parseFloat(sd.ph).toFixed(2)}</span>`,
      `<span class="snapshot-pill"><strong>Rainfall:</strong> ${sd.rainfall}mm</span>`,
    ].join("");
  } else {
    snapshotEl.innerHTML = "";
  }

  // Scroll to result
  container.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function saveRecommendation() {
  const selectedIdx = document.querySelector('input[name="crop_selection"]:checked')?.value;
  if (selectedIdx === undefined || !window.currentRecommendations) return;
  
  const cropData = window.currentRecommendations[selectedIdx];
  const btn = document.getElementById("save-history-btn");
  btn.disabled = true;
  btn.textContent = "Saving...";

  try {
    const res = await fetch(apiUrl("/api/recommend/save"), {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        crop_name: cropData.best_crop,
        reason: cropData.reason,
        harvest_duration: cropData.harvest_duration,
        planting_month: cropData.planting_month,
        harvest_month: cropData.harvest_month,
        planting_cost_per_hectare: cropData.planting_cost_per_hectare,
        total_cost: cropData.total_cost
      }),
    });
    
    if (res.ok) {
      btn.textContent = "Saved to History!";
      btn.style.backgroundColor = "var(--success)";
      btn.style.borderColor = "var(--success)";
      loadHistory();
      setTimeout(() => {
        btn.textContent = "Confirm & Save Selection";
        btn.style.backgroundColor = "var(--accent)";
        btn.style.borderColor = "var(--accent)";
        btn.disabled = false;
      }, 3000);
    }
  } catch (err) {
    console.error(err);
    btn.disabled = false;
    btn.textContent = "Confirm & Save Selection";
  }
}


// ─── Crop History ─────────────────────────────────────────────────────────────
async function loadHistory() {
  try {
    const res  = await fetch(apiUrl("/api/history"), { credentials: "include" });
    if (!res.ok) return;
    const rows = await res.json();
    renderHistory(rows);
  } catch {}
}

function renderHistory(rows) {
  const tbody   = document.getElementById("history-tbody");
  const emptyEl = document.getElementById("history-empty");
  const countEl = document.getElementById("history-count");

  countEl.textContent = `${rows.length} record${rows.length !== 1 ? "s" : ""}`;

  if (rows.length === 0) {
    emptyEl.classList.remove("hidden");
    tbody.innerHTML = "";
    return;
  }

  emptyEl.classList.add("hidden");
  tbody.innerHTML = rows.map((r, i) => `
    <tr>
      <td>${i + 1}</td>
      <td><span class="crop-chip">${getCropEmoji(r.crop_name)} ${r.crop_name}</span></td>
      <td>${r.harvest_duration || "—"}</td>
      <td>${r.planting_month  || "—"}</td>
      <td>${r.harvest_month   || "—"}</td>
      <td>${r.planting_cost_per_hectare || "—"}</td>
      <td style="font-weight: 600;">${r.total_cost || "—"}</td>
      <td>${formatDate(r.date_recorded)}</td>
      <td>
        <button class="btn-delete" onclick="deleteHistoryEntry(${r.id}, this)">
           Delete
        </button>
      </td>
    </tr>
  `).join("");
}

async function deleteHistoryEntry(id, btn) {
  btn.disabled = true;
  btn.textContent = "...";
  try {
    const res = await fetch(apiUrl(`/api/history/${id}`), {
      method:      "DELETE",
      credentials: "include",
    });
    if (res.ok) loadHistory();
  } catch {}
}

function formatDate(isoStr) {
  if (!isoStr) return "—";
  const d = new Date(isoStr);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}


// ─── Logout ───────────────────────────────────────────────────────────────────
async function handleLogout() {
  clearInterval(sensorInterval);
  await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
  window.location.href = "/";
}
