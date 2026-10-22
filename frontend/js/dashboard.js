/* dashboard.js — Kisan Mitra v2 dashboard */

// ─── State ────────────────────────────────────────────────────────────────────
let currentUser = null;
let meta = null;
let sensorInterval = null;
let lastResult = null;
const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:5000" : "";

const SOIL_FIELDS = [
  { key: "pH", label: "pH",              step: "0.01" },
  { key: "OC", label: "Organic carbon",  step: "0.01" },
  { key: "N",  label: "Nitrogen (N)",    step: "1" },
  { key: "P",  label: "Phosphorus (P)",  step: "0.1" },
  { key: "K",  label: "Potassium (K)",   step: "1" },
  { key: "S",  label: "Sulphur (S)",     step: "0.1" },
  { key: "Zn", label: "Zinc (Zn)",       step: "0.01" },
  { key: "B",  label: "Boron (B)",       step: "0.01" },
  { key: "Fe", label: "Iron (Fe)",       step: "0.1" },
  { key: "Mn", label: "Manganese (Mn)",  step: "0.1" },
  { key: "Cu", label: "Copper (Cu)",     step: "0.01" },
];

function apiUrl(path) { return `${API_BASE}${path}`; }

async function api(path, options = {}) {
  const res = await fetch(apiUrl(path), {
    credentials: "include",
    headers: options.body ? { "Content-Type": "application/json" } : {},
    ...options,
  });
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { error: text }; }
  if (res.status === 401) { window.location.href = apiUrl("/"); throw new Error("Not logged in"); }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function el(id) { return document.getElementById(id); }


// ─── Initialise ───────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  try {
    currentUser = await api("/api/auth/me");
  } catch { return; }

  el("user-name-sm").textContent = currentUser.name;
  el("user-avatar").textContent = currentUser.name.charAt(0).toUpperCase();

  meta = await api("/api/meta");
  buildTalukaSelect();
  buildSoilForm();
  buildCropSelect();
  showModelBadge();

  loadDistrictProfile();
  onTalukaChange();
  el("sowing-date").value = isoToday();
  loadHistory();
  loadTasks();

  fetchSensorData();
  sensorInterval = setInterval(fetchSensorData, 1500);
  trackActiveSection();
});

function trackActiveSection() {
  const links = [...document.querySelectorAll(".sidebar-nav .nav-link")];
  const sections = links.map(a => document.querySelector(a.getAttribute("href")));
  const scroller = document.querySelector(".main-content");
  const update = () => {
    // On phones the page itself scrolls; on desktop the main panel does
    const top = scroller.scrollHeight > scroller.clientHeight ? scroller.getBoundingClientRect().top : 0;
    let current = 0;
    sections.forEach((sec, i) => { if (sec.getBoundingClientRect().top - top < 160) current = i; });
    // The last section is short, so treat "scrolled to the bottom" as being on it
    const pageEl = scroller.scrollHeight > scroller.clientHeight ? scroller : document.scrollingElement;
    if (pageEl.scrollTop + pageEl.clientHeight >= pageEl.scrollHeight - 4) current = sections.length - 1;
    links.forEach((a, i) => a.classList.toggle("active", i === current));
  };
  scroller.addEventListener("scroll", update, { passive: true });
  window.addEventListener("scroll", update, { passive: true });
  update();
}


// ─── Farm setup ───────────────────────────────────────────────────────────────
function buildTalukaSelect() {
  const saved = localStorageGet("km_taluka") || "Haveli";
  el("taluka").innerHTML = meta.talukas.map(t =>
    `<option value="${esc(t.name)}" ${t.name === saved ? "selected" : ""}>${esc(t.name)}${t.in_training_data ? "" : " *"}</option>`
  ).join("");
}

function onTalukaChange() {
  const taluka = el("taluka").value;
  localStorageSet("km_taluka", taluka);
  const info = meta.talukas.find(t => t.name === taluka);
  const hint = el("taluka-hint");
  if (info && !info.in_training_data) {
    hint.textContent = `* ${taluka} has no villages in the training data. Recommendations still work from your soil card, but treat them with extra care.`;
    hint.classList.remove("hidden");
  } else {
    hint.classList.add("hidden");
  }
  loadWeather(taluka);
  api("/api/irrigation/config", { method: "POST", body: JSON.stringify({ taluka }) }).catch(() => {});
}

async function loadWeather(taluka) {
  try {
    const w = await api(`/api/weather?taluka=${encodeURIComponent(taluka)}`);
    el("weather-source").textContent = w.available ? "(Open-Meteo)" : "(offline: Pune normals)";
    const rows = [
      ["Temperature", `${w.temperature_c} °C`],
      ["Humidity", `${w.humidity_pct} %`],
      ["Rain next 24 h", `${w.rain_next_24h_mm} mm`],
    ];
    (w.forecast || []).slice(1).forEach(d => rows.push([formatDay(d.date), `${d.rain_mm ?? 0} mm · ${d.t_min}–${d.t_max} °C`]));
    el("weather-box").innerHTML = rows.map(([k, v]) => `<div class="kv"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join("");
  } catch (err) {
    el("weather-box").innerHTML = `<span class="muted">${esc(err.message)}</span>`;
  }
}

async function loadDistrictProfile() {
  try {
    const d = await api("/api/district-profile");
    if (!d.available) { el("district-box").innerHTML = `<span class="muted">District data not found.</span>`; return; }
    const bars = Object.entries(d.deficient_share_pct).map(([name, pct]) => `
      <div class="bar-row">
        <span>${esc(name)}</span>
        <div class="bar"><div class="bar-fill" style="width:${pct}%"></div></div>
        <strong>${pct}%</strong>
      </div>`).join("");
    el("district-box").innerHTML = `
      <p class="muted small">Share of soil samples deficient in each nutrient</p>
      ${bars}
      <div class="kv-grid" style="margin-top:12px">
        <div class="kv"><span>Soil stress</span><strong>${esc(d.soil_stress.category)}</strong></div>
        <div class="kv"><span>Mean rainfall</span><strong>${Math.round(d.mean_rainfall_mm)} mm/yr</strong></div>
        <div class="kv"><span>Irrigated area</span><strong>${d.irrigated_share_pct}%</strong></div>
      </div>`;
  } catch (err) {
    el("district-box").innerHTML = `<span class="muted">${esc(err.message)}</span>`;
  }
}

function showModelBadge() {
  const m = meta.model;
  el("model-badge").textContent = m
    ? `Model: ${m.samples} real soil cards · first pick suitable ${Math.round(m.top1_correct * 100)}% (baseline ${Math.round(m.baseline_top1 * 100)}%)`
    : "Model not trained";
  const fm = meta.fertilizer_model;
  if (fm) {
    el("model-badge").title =
      `Fertilizer combination models: ${Math.round(fm.combination_1.accuracy * 100)}% / ${Math.round(fm.combination_2.accuracy * 100)}% accuracy ` +
      `(baseline ${Math.round(fm.combination_1.baseline * 100)}% / ${Math.round(fm.combination_2.baseline * 100)}%)`;
  }
}


// ─── Soil card ────────────────────────────────────────────────────────────────
function buildSoilForm() {
  el("soil-grid").innerHTML = SOIL_FIELDS.map(f => {
    const unit = meta.soil_units[f.key];
    return `
      <div class="field">
        <label for="soil-${f.key}">${esc(f.label)} ${unit ? `<span class="muted">(${esc(unit)})</span>` : ""}</label>
        <input type="number" id="soil-${f.key}" step="${f.step}" min="0" oninput="this.classList.remove('invalid')" />
      </div>`;
  }).join("");
}

function readSoilForm() {
  const soil = {};
  SOIL_FIELDS.forEach(f => { soil[f.key] = el(`soil-${f.key}`).value; });
  return soil;
}

async function loadSampleCard() {
  try {
    const s = await api("/api/soil/sample");
    SOIL_FIELDS.forEach(f => {
      const input = el(`soil-${f.key}`);
      input.value = s.soil[f.key];
      input.classList.remove("invalid");
      input.classList.toggle("approx", s.source.approximated.includes(f.key));
    });
    const src = s.source;
    el("sample-info").innerHTML =
      `Loaded a real soil card from <strong>${esc(src.village)}, ${esc(src.sub_district)}</strong>${src.year ? ` (${src.year})` : ""}. ` +
      `Crops advised on that card: ${src.known_crops.map(esc).join(", ")}. ` +
      `<span class="muted">Highlighted fields were stored only as Low/Medium/High in the dataset, so a typical value for that level is shown.</span>`;
  } catch (err) {
    el("sample-info").textContent = err.message;
  }
}


// ─── Recommendation ───────────────────────────────────────────────────────────
async function getRecommendation() {
  const btn = el("recommend-btn"), spinner = el("rec-spinner"), errEl = el("rec-error");
  errEl.classList.add("hidden");
  el("result-container").classList.add("hidden");  // never show results for an older input

  const missing = SOIL_FIELDS.filter(f => {
    const input = el(`soil-${f.key}`);
    const bad = input.value.trim() === "" || Number.isNaN(Number(input.value));
    input.classList.toggle("invalid", bad);
    return bad;
  });
  if (missing.length) {
    errEl.textContent = `Please fill in every soil card value. Missing: ${missing.map(f => f.label).join(", ")}.`;
    errEl.classList.remove("hidden");
    el(`soil-${missing[0].key}`).focus();
    return;
  }
  btn.disabled = true;
  spinner.classList.remove("hidden");

  try {
    const result = await api("/api/recommend", {
      method: "POST",
      body: JSON.stringify({
        taluka: el("taluka").value,
        area: el("area").value,
        irrigation: el("irrigation").checked,
        sowing_date: el("sowing-date").value,
        soil: readSoilForm(),
      }),
    });
    lastResult = result;
    displayResult(result);
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    spinner.classList.add("hidden");
  }
}

function displayResult(r) {
  el("result-container").classList.remove("hidden");

  const c = r.confidence;
  el("confidence-box").innerHTML = `
    <div class="confidence conf-${c.level.toLowerCase()}">
      <strong>Confidence: ${esc(c.level)}</strong>
      <span>${c.level === "High" ? "Your soil is similar to soil cards the model learned from." :
              c.level === "Medium" ? "Your soil is somewhat different from the training data." :
              "Your soil is unlike the Pune training data. Use these suggestions with caution."}</span>
      ${c.warnings.map(w => `<div class="warn">⚠ ${esc(w)}</div>`).join("")}
    </div>`;

  el("soil-levels").innerHTML = SOIL_FIELDS.filter(f => r.soil_levels[f.key])
    .map(f => `<span class="snapshot-pill"><strong>${esc(f.key)}:</strong> ${esc(r.soil_levels[f.key])}</span>`).join("");

  el("result-now").innerHTML = r.sow_now.length
    ? r.sow_now.map((crop, i) => cropCard(crop, i)).join("")
    : `<p class="muted">No suitable crop has its sowing window open right now. See the crops for later this year below.</p>`;

  el("result-later").innerHTML = r.later.length
    ? r.later.map(crop => `
        <div class="later-item">
          <strong>${esc(crop.crop)}</strong> <span class="muted">${esc(crop.marathi)}</span>
          <span>${Math.round(crop.suitability * 100)}% soil match</span>
          <span class="muted">${esc(crop.season.label)}</span>
        </div>`).join("")
    : `<p class="muted">None.</p>`;

  el("save-history-btn").classList.toggle("hidden", !r.sow_now.length);
  el("result-container").scrollIntoView({ behavior: "smooth", block: "start" });
}

function cropCard(crop, idx) {
  const f = crop.fertilizer;
  const water = crop.water;
  const waterBadge = water.feasible_without_irrigation
    ? `<span class="tag ok">Rain-fed OK</span>`
    : water.feasible ? `<span class="tag warn">Needs irrigation</span>`
    : `<span class="tag bad">Not enough water without irrigation</span>`;

  return `
    <label class="crop-card ${idx === 0 ? "selected" : ""}">
      <input type="radio" name="crop_selection" value="${idx}" ${idx === 0 ? "checked" : ""} onchange="selectCard(this)" aria-label="Select ${esc(crop.crop)}">
      <div class="crop-head">
        <div>
          <div class="result-crop-name">${esc(crop.crop)} <span class="muted marathi">${esc(crop.marathi)}</span></div>
          <div class="tags"><span class="tag">${esc(crop.season.label)}</span>${waterBadge}<span class="tag">Water need: ${esc(crop.water_need)}</span></div>
        </div>
        <div class="score">
          <div class="score-num">${Math.round(crop.suitability * 100)}%</div>
          <div class="muted small">soil match</div>
        </div>
      </div>

      <p class="reason">${esc(crop.reason)}</p>

      <div class="result-details-grid">
        <div class="result-detail-item"><div class="detail-label">Duration</div><div class="detail-value">${esc(crop.harvest_duration)}</div></div>
        <div class="result-detail-item"><div class="detail-label">Sowing months</div><div class="detail-value">${esc(crop.season.sowing_months)}</div></div>
        <div class="result-detail-item"><div class="detail-label">Cost of cultivation per ha</div><div class="detail-value">${esc(crop.cost_per_ha)}</div></div>
        <div class="result-detail-item"><div class="detail-label">Fertilizer for your soil</div><div class="detail-value">${rupees(crop.fertilizer.dose_options[0].cost_total)} <span class="muted small">(${rupees(crop.fertilizer.dose_options[0].cost_per_ha)}/ha)</span></div></div>
      </div>
      ${economicsBlock(crop.economics)}

      <details class="fert">
        <summary>Fertilizer plan</summary>
        ${fertilizerPlan(f)}
      </details>
    </label>`;
}

function fertilizerPlan(f) {
  const combos = f.card_combinations.length ? `
    <div class="fert-block">
      <div class="detail-label">Soil Health Card combinations (predicted from real Pune cards)</div>
      <div class="combo-row">
        ${f.card_combinations.map(c => `
          <div class="combo">
            <span class="muted small">Combination ${c.slot}</span>
            <strong>${esc(c.code)}</strong>
            <span class="small">${esc(c.name)}</span>
            ${c.status === "inferred"
              ? `<span class="muted small" title="${esc(c.evidence || "")}">Meaning inferred from the data (${esc(c.meaning_confidence || "low")} confidence)</span>`
              : ""}
            <span class="muted small">${Math.round(c.confidence * 100)}% model confidence</span>
          </div>`).join("")}
      </div>
    </div>` : "";

  const doseTable = opt => `
    <div class="fert-block">
      <div class="detail-label">${esc(opt.label)} ${opt.matches_card ? `<span class="tag ok">Matches card combination</span>` : ""}</div>
      <table class="mini-table">
        <thead><tr><th>Product</th><th>kg/ha</th><th>Total</th><th>Bags</th><th>Cost</th></tr></thead>
        <tbody>
          ${opt.products.map(p => `<tr><td>${esc(p.product)}</td><td>${p.kg_per_ha}</td><td>${p.total_kg} kg</td><td>${p.bags} × ${p.bag_kg} kg</td><td>${rupees(p.cost)}</td></tr>`).join("")}
          <tr><td colspan="4"><strong>Total</strong></td><td><strong>${rupees(opt.cost_total)}</strong></td></tr>
        </tbody>
      </table>
      ${opt.note ? `<p class="muted small">${esc(opt.note)}</p>` : ""}
    </div>`;

  const micro = f.micronutrients.length ? `
    <div class="fert-block">
      <div class="detail-label">Micronutrient corrections</div>
      <table class="mini-table">
        <tbody>${f.micronutrients.map(m => `<tr><td>${esc(m.product)} <span class="muted">(${esc(m.nutrient)} low)</span></td><td>${m.kg_per_ha} kg/ha</td><td>${m.total_kg} kg total</td></tr>`).join("")}</tbody>
      </table>
    </div>` : "";

  return `
    ${combos}
    ${scheduleTimeline(f.schedule)}
    <p class="muted small">Season totals: standard ${f.standard_dose_kg_per_ha.N}:${f.standard_dose_kg_per_ha.P2O5}:${f.standard_dose_kg_per_ha.K2O} kg/ha (N:P₂O₅:K₂O),
      adjusted for your soil (N ${esc(f.soil_status.N)}, P ${esc(f.soil_status.P)}, K ${esc(f.soil_status.K)})
      → ${f.nutrient_need_kg_per_ha.N}:${f.nutrient_need_kg_per_ha.P2O5}:${f.nutrient_need_kg_per_ha.K2O} kg/ha for the whole season. Two ways to supply it:</p>
    <div class="dose-grid">${f.dose_options.map(doseTable).join("")}</div>
    ${micro}
    <div class="fert-block">
      <div class="detail-label">Organic manure <span class="muted">(${esc(f.organic.reason)})</span></div>
      <p class="small">${esc(f.organic.text)}</p>
    </div>
    ${f.notes.length ? `<ul class="notes">${f.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}`;
}

function rupees(v) {
  if (v === null || v === undefined) return "—";
  const sign = v < 0 ? "−" : "";
  return sign + "₹" + Math.abs(Math.round(v)).toLocaleString("en-IN");
}

function economicsBlock(e) {
  if (!e) return "";
  const live = e.live
    ? `${rupees(e.live.price)}/quintal <span class="muted small">${e.live.level === "fixed" ? esc(e.live.basis)
        : `${esc(e.live.level)} · ${esc(e.live.markets.slice(0, 3).join(", "))}${e.live.date ? " · " + esc(e.live.date) : ""}`}</span>`
    : `<span class="muted">No mandi quote today</span>`;
  const exp = e.expected_price
    ? `${rupees(e.expected_price.median)}/quintal <span class="muted small">(${rupees(e.expected_price.low)}–${rupees(e.expected_price.high)} across years · ${esc(e.expected_price.years || "fixed")})</span>`
    : `<span class="muted">Not enough price history</span>`;
  const yld = e.yield ? `${e.yield.t_per_ha} t/ha <span class="muted small">(${esc(e.yield.basis)})</span>` : `<span class="muted">No district yield data yet</span>`;

  let profit = `<p class="muted small">Profit estimate needs ${esc(e.missing.join(" and "))}.</p>`;
  if (e.profit_total) {
    const p = e.profit_total, lo = Math.min(p.low, 0), hi = Math.max(p.high, 0), span = hi - lo || 1;
    const pos = v => ((v - lo) / span * 100).toFixed(1);
    profit = `
      <div class="profit">
        <div class="profit-head"><span class="detail-label">Expected profit for your area</span>
          <strong class="${p.typical >= 0 ? "pos" : "neg"}">${rupees(p.typical)}</strong></div>
        <div class="range-bar">
          <div class="range-fill" style="left:${pos(p.low)}%;width:${(pos(p.high) - pos(p.low)).toFixed(1)}%"></div>
          ${lo < 0 ? `<div class="range-zero" style="left:${pos(0)}%"></div>` : ""}
          <div class="range-mark" style="left:${pos(p.typical)}%"></div>
        </div>
        <div class="range-labels"><span>Bad year ${rupees(p.low)}</span><span>Good year ${rupees(p.high)}</span></div>
        <p class="muted small">Yield × harvest-month price − cost of cultivation. Typical income ${rupees(e.income_per_ha_typical)}/ha.
          ${e.yield_note ? esc(e.yield_note) : ""}</p>
      </div>`;
  }
  return `
    <div class="econ">
      <div class="econ-grid">
        <div><div class="detail-label">Mandi price today</div><div class="small">${live}</div></div>
        <div><div class="detail-label">Expected at harvest (${esc(e.harvest_month)})</div><div class="small">${exp}</div></div>
        <div><div class="detail-label">Yield</div><div class="small">${yld}</div></div>
      </div>
      ${profit}
    </div>`;
}

const STEP_STATUS = { done: "Done", due: "Due now", upcoming: "Upcoming" };
const REF_WORD = { sowing: "sowing", transplanting: "transplanting", planting: "planting" };

function scheduleTimeline(sch) {
  if (!sch || !sch.steps) return "";
  const basis = { verified: "official recommendation", partial: "partly from an official source", general: "standard practice" }[sch.status] || sch.status;
  return `
    <div class="fert-block">
      <div class="detail-label">When to apply <span class="muted">(${esc(sch.option_label)} · ${esc(basis)})</span></div>
      <ol class="timeline">
        ${sch.steps.map(st => `
          <li class="tl-step tl-${st.status}">
            <div class="tl-when">
              <strong>${formatDay(st.date)}</strong>
              <span class="muted small">Day ${st.day} after ${esc(REF_WORD[sch.reference] || sch.reference)}</span>
              <span class="tl-status">${STEP_STATUS[st.status] || ""}</span>
            </div>
            <div class="tl-what">
              <div class="tl-stage">${esc(st.stage)}</div>
              <div class="tl-products">${st.products.map(p => `<span class="pill">${esc(p.product)} <strong>${p.kg_per_ha} kg/ha</strong> · ${p.total_kg} kg · ${p.bags} bags · ${rupees(p.cost)}</span>`).join("")}</div>
              ${st.tips.map(t => `<div class="small ${t.includes("rain") ? "tl-warn" : "muted"}">${t.includes("rain") ? "⚠ " : ""}${esc(t)}</div>`).join("")}
            </div>
          </li>`).join("")}
      </ol>
      ${sch.note ? `<p class="muted small">${esc(sch.note)}</p>` : ""}
      ${sch.sources.length ? `<p class="muted small" title="${esc(sch.sources.join(" | "))}">Source: ${esc(sch.sources[0].split(" (")[0])}</p>` : ""}
    </div>`;
}

async function loadTasks() {
  try {
    const tasks = await api("/api/tasks/upcoming");
    el("tasks-panel").classList.toggle("hidden", !tasks.length);
    el("tasks-list").innerHTML = tasks.map(t => `
      <div class="task ${t.days_left <= 3 ? "task-soon" : ""}">
        <div class="task-when"><strong>${formatDay(t.date)}</strong>
          <span class="muted small">${t.days_left < 0 ? `${-t.days_left} days overdue` : t.days_left === 0 ? "today" : `in ${t.days_left} days`}</span></div>
        <div class="task-what"><strong>${esc(t.crop)}</strong> · ${esc(t.stage)}
          <div class="small">${t.products.map(p => `${esc(p.product)} ${p.total_kg} kg (${p.bags} bags)`).join(", ")}</div>
          ${t.warning ? `<div class="small tl-warn">⚠ ${esc(t.warning)}</div>` : ""}</div>
      </div>`).join("");
  } catch { /* tasks are optional */ }
}

function isoToday() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function selectCard(radio) {
  document.querySelectorAll(".crop-card").forEach(c => c.classList.remove("selected"));
  radio.closest(".crop-card").classList.add("selected");
}

async function saveRecommendation() {
  const idx = document.querySelector('input[name="crop_selection"]:checked')?.value;
  if (idx === undefined || !lastResult) return;
  const crop = lastResult.sow_now[idx];
  const btn = el("save-history-btn");
  btn.disabled = true;
  btn.textContent = "Saving...";

  try {
    await api("/api/recommend/save", {
      method: "POST",
      body: JSON.stringify({
        crop_name: crop.crop,
        reason: crop.reason,
        harvest_duration: crop.harvest_duration,
        planting_month: crop.season.sowing_months,
        planting_cost_per_hectare: crop.cost_per_ha,
        total_cost: crop.total_cost,
        taluka: lastResult.taluka,
        soil: lastResult.soil,
        sowing_date: crop.fertilizer.schedule.start_date,
        schedule: crop.fertilizer.schedule,
      }),
    });
    btn.textContent = `Saved — irrigation now set for ${crop.crop}`;
    el("irr-crop").value = crop.crop;
    loadHistory();
    loadTasks();
  } catch (err) {
    btn.textContent = err.message;
  } finally {
    setTimeout(() => {
      btn.disabled = false;
      btn.textContent = "Save selected crop & use it for irrigation";
    }, 2500);
  }
}


// ─── Irrigation ───────────────────────────────────────────────────────────────
// ─── Farm plan ────────────────────────────────────────────────────────────────
const PLOT_COLORS = ["#2E7D5B", "#D9A441", "#3B6EA8", "#BE2823", "#7A5BA6", "#6B6B6B"];

async function makePlan() {
  const btn = el("plan-btn"), spinner = el("plan-spinner"), errEl = el("plan-error");
  errEl.classList.add("hidden");
  el("plan-result").classList.add("hidden");
  const missing = SOIL_FIELDS.filter(f => el(`soil-${f.key}`).value.trim() === "");
  if (missing.length) {
    errEl.textContent = "Fill in the Soil Health Card above first (or load a real Pune soil card).";
    errEl.classList.remove("hidden");
    return;
  }
  btn.disabled = true;
  spinner.classList.remove("hidden");
  try {
    const fixedCrop = el("plan-fixed").value;
    const plan = await api("/api/plan", {
      method: "POST",
      body: JSON.stringify({
        total_ha: el("plan-total").value, plots: el("plan-plots").value, irrigated_ha: el("plan-irrigated").value,
        sowing_date: el("sowing-date").value, taluka: el("taluka").value, soil: readSoilForm(),
        fixed: fixedCrop ? { crop: fixedCrop, ha: el("plan-fixed-ha").value } : null,
      }),
    });
    renderPlan(plan);
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    spinner.classList.add("hidden");
  }
}

function renderPlan(p) {
  const out = el("plan-result");
  const t = p.totals, lo = Math.min(t.low, 0), hi = Math.max(t.high, 0), span = hi - lo || 1;
  const pos = v => ((v - lo) / span * 100).toFixed(1);
  const base = p.baseline_single_crop;
  const irrigatedUsed = p.plots.filter(x => x.needs_irrigation).reduce((s, x) => s + x.ha, 0);

  out.innerHTML = `
    <div class="panel plan-summary">
      <div class="detail-label">How your ${p.total_ha} ha is split</div>
      <div class="split-bar" role="img" aria-label="${esc(p.plots.map(x => `${x.crop} ${x.ha} ha`).join(", "))}">
        ${p.plots.map((x, i) => `<div class="split-seg" style="width:${(x.share * 100).toFixed(2)}%;background:${PLOT_COLORS[i % 6]}"
            title="${esc(x.crop)}: ${x.ha} ha">${x.share >= 0.25 ? `${esc(x.crop)} · ${x.ha} ha` : x.share >= 0.1 ? esc(x.crop) : ""}</div>`).join("")}
      </div>
      <div class="split-legend">${p.plots.map((x, i) => `<span><i style="background:${PLOT_COLORS[i % 6]}"></i>${esc(x.crop)} ${x.ha} ha (${Math.round(x.share * 100)}%)</span>`).join("")}</div>

      <div class="plan-total">
        <div class="profit-head"><span class="detail-label">Expected farm profit</span>
          <strong class="${t.typical >= 0 ? "pos" : "neg"}">${rupees(t.typical)}</strong></div>
        <div class="range-bar">
          <div class="range-fill" style="left:${pos(t.low)}%;width:${(pos(t.high) - pos(t.low)).toFixed(1)}%"></div>
          ${lo < 0 ? `<div class="range-zero" style="left:${pos(0)}%"></div>` : ""}
          <div class="range-mark" style="left:${pos(t.typical)}%"></div>
        </div>
        <div class="range-labels"><span>Bad year ${rupees(t.low)}</span><span>Good year ${rupees(t.high)}</span></div>
        ${base ? `<p class="small">The best single crop on the whole farm (${esc(base.crop)}) would give ${rupees(base.typical)} in a typical year:
            this plan is <strong class="${p.gain_vs_single_crop >= 0 ? "pos" : "neg"}">${p.gain_vs_single_crop >= 0 ? "+" : ""}${rupees(p.gain_vs_single_crop)}</strong>
            and spreads the price risk across ${p.plots.length} crop${p.plots.length > 1 ? "s" : ""}.</p>` : ""}
        <p class="muted small">Irrigated land used: ${irrigatedUsed} of ${p.irrigated_ha} ha.
          Plot sizes in ${p.rules.step_ha} ha steps; each crop between ${Math.round(p.rules.min_share * 100)}% and ${Math.round(p.rules.max_share * 100)}% of the farm.</p>
      </div>
    </div>

    <div class="plot-grid">
      ${p.plots.map((x, i) => `
        <div class="plot-card">
          <div class="plot-head"><i style="background:${PLOT_COLORS[i % 6]}"></i>
            <strong>Plot ${i + 1}: ${esc(x.crop)}</strong> <span class="muted">${esc(x.marathi)}</span></div>
          <div class="plot-ha">${x.ha} ha <span class="muted small">· ${Math.round(x.share * 100)}% of farm · ${Math.round(x.suitability * 100)}% soil match</span></div>
          <div class="tags">${x.needs_irrigation ? `<span class="tag warn">Irrigated</span>` : `<span class="tag ok">Rain-fed</span>`}<span class="tag">Water need: ${esc(x.water_need)}</span></div>
          <div class="kv"><span>Typical profit</span><strong class="${x.profit.typical >= 0 ? "pos" : "neg"}">${rupees(x.profit.typical)}</strong></div>
          <div class="kv"><span>Range</span><span>${rupees(x.profit.low)} to ${rupees(x.profit.high)}</span></div>
          <div class="kv"><span>Fertilizer cost</span><span>${rupees(x.fertilizer_cost)}</span></div>
          ${x.warning ? `<p class="small tl-warn">⚠ ${esc(x.warning)}</p>` : ""}
          <details class="fert"><summary>Fertilizer schedule for this plot</summary>${scheduleTimeline(x.schedule)}</details>
        </div>`).join("")}
    </div>
    ${p.excluded.length ? `<p class="muted small">Not planned: ${p.excluded.map(e => `${esc(e.crop)} (${esc(e.reason)})`).join(", ")}.</p>` : ""}`;
  out.classList.remove("hidden");
  out.scrollIntoView({ behavior: "smooth", block: "start" });
}

function buildCropSelect() {
  el("plan-fixed").innerHTML = `<option value="">No preference</option>` +
    meta.crops.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  el("irr-crop").innerHTML = `<option value="">Not set (medium water need)</option>` +
    meta.crops.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
}

async function fetchSensorData() {
  try {
    updateSensorUI(await api("/api/sensor/latest"));
  } catch { /* network hiccup */ }
}

function updateSensorUI(s) {
  const r = s.reading;
  const irr = s.irrigation;
  const live = s.source === "mqtt";

  el("status-dot").className = `status-dot ${live ? "live" : s.connected ? "simulated" : "error"}`;
  el("status-text").textContent = live ? "Live sensor (MQTT)" : s.connected ? "MQTT connected · no sensor, simulating" : "MQTT offline · simulating";
  const others = (s.devices_online || []).filter(d => d !== r?.device);
  el("sensor-source-badge").textContent = live
    ? `Live from ${r?.device || "ESP32"}${others.length ? ` (also online, ignored: ${others.join(", ")})` : ""}`
    : "SIMULATED readings";
  el("sensor-source-badge").classList.toggle("badge-warn", !live);

  if (r) {
    el("val-moisture").textContent = r.soil_moisture.toFixed(1);
    el("val-temp").textContent = r.temperature.toFixed(1);
    el("val-hum").textContent = r.humidity.toFixed(0);
    el("bar-moisture").style.width = `${Math.min(100, r.soil_moisture)}%`;
    el("last-updated").textContent = `Updated: ${new Date(r.at * 1000).toLocaleTimeString()}`;
  }

  const band = el("band-moisture");
  band.style.left = `${irr.thresholds.moisture_on}%`;
  band.style.width = `${irr.thresholds.moisture_off - irr.thresholds.moisture_on}%`;

  el("val-pump").textContent = irr.pump_on ? "ON" : "OFF";
  el("pump-card").classList.toggle("pump-on", irr.pump_on);
  el("mode-auto").classList.toggle("active", irr.mode === "auto");
  el("mode-manual").classList.toggle("active", irr.mode === "manual");
  el("manual-controls").classList.toggle("disabled", irr.mode !== "manual");
  if (document.activeElement !== el("irr-crop")) el("irr-crop").value = irr.crop || "";
  el("decision-text").innerHTML =
    `<strong>${irr.mode === "auto" ? "Auto decision" : "Manual mode"}:</strong> ${esc(irr.decision.reason)}
     <div class="muted small">Target band for ${esc(irr.crop || "default crop")} (${esc(irr.thresholds.water_class)} water need): ${irr.thresholds.moisture_on}–${irr.thresholds.moisture_off}% moisture</div>`;
}

async function setIrrigation(change) {
  const errEl = el("irr-error");
  errEl.classList.add("hidden");
  try {
    await api("/api/irrigation/config", { method: "POST", body: JSON.stringify(change) });
    fetchSensorData();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
  }
}


// ─── Crop History ─────────────────────────────────────────────────────────────
async function loadHistory() {
  try { renderHistory(await api("/api/history")); } catch {}
}

function renderHistory(rows) {
  el("history-count").textContent = `${rows.length} record${rows.length !== 1 ? "s" : ""}`;
  el("history-empty").classList.toggle("hidden", rows.length > 0);
  document.querySelector(".history-table-wrap").classList.toggle("hidden", rows.length === 0);
  el("history-tbody").innerHTML = rows.map((r, i) => `
    <tr>
      <td>${i + 1}</td>
      <td><span class="crop-chip">${esc(r.crop_name)}</span></td>
      <td>${esc(r.taluka || "—")}</td>
      <td>${esc(r.harvest_duration || "—")}</td>
      <td>${r.sowing_date ? formatDay(r.sowing_date) : esc(r.planting_month || "—")}</td>
      <td>${esc(r.planting_cost_per_hectare || "—")}</td>
      <td style="font-weight: 600;">${esc(r.total_cost || "—")}</td>
      <td>${formatDate(r.date_recorded)}</td>
      <td><button class="btn-delete" onclick="deleteHistoryEntry(${Number(r.id)}, this)">Delete</button></td>
    </tr>`).join("");
}

async function deleteHistoryEntry(id, btn) {
  if (!confirm("Delete this crop from your history?")) return;
  btn.disabled = true;
  btn.textContent = "...";
  try { await api(`/api/history/${id}`, { method: "DELETE" }); loadHistory(); } catch {}
}


// ─── Helpers ──────────────────────────────────────────────────────────────────
function formatDate(isoStr) {
  if (!isoStr) return "—";
  const d = new Date(isoStr.replace(" ", "T") + "Z");
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function formatDay(isoDate) {
  return new Date(isoDate).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
}

function localStorageGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
function localStorageSet(key, val) { try { localStorage.setItem(key, val); } catch {} }

async function handleLogout() {
  clearInterval(sensorInterval);
  await fetch(apiUrl("/api/auth/logout"), { method: "POST", credentials: "include" });
  window.location.href = apiUrl("/");
}
