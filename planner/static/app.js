const inputEl = document.getElementById("input");
const traceEl = document.getElementById("trace");
const planEl = document.getElementById("plan");
const goBtn = document.getElementById("go");
const randomizeBtn = document.getElementById("randomize");
const outageEl = document.getElementById("outage");

const DOT_ICON = { ok: "✓", fallback: "!", error: "×", info: "i", running: "" };

let runningSteps = new Map();
let currentController = null;

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function setBusy(busy) {
  goBtn.disabled = busy;
  goBtn.textContent = busy ? "Planning…" : "Plan my Saturday";
  randomizeBtn.disabled = busy;
  document.querySelectorAll("#examples .chip").forEach((chip) => {
    chip.disabled = busy;
  });
}

function clearEmptyState(container) {
  const empty = container.querySelector(".empty");
  if (empty) empty.remove();
}

function stepHTML(step) {
  const icon = DOT_ICON[step.status] ?? "";
  const ms = step.ms != null ? ` · ${step.ms}ms` : "";
  return (
    `<div class="dot ${esc(step.status)}">${esc(icon)}</div>` +
    `<div>` +
    `<div class="tool">${esc(step.tool)}<span class="ms">${esc(ms)}</span></div>` +
    `<div class="msg">${esc(step.message)}</div>` +
    `</div>`
  );
}

function renderTrace(step) {
  clearEmptyState(traceEl);
  if (step.status === "running") {
    let node = runningSteps.get(step.tool);
    if (!node) {
      node = document.createElement("div");
      node.className = "step";
      traceEl.appendChild(node);
      runningSteps.set(step.tool, node);
    }
    node.innerHTML = stepHTML(step);
  } else {
    const node = runningSteps.get(step.tool);
    if (node) {
      node.innerHTML = stepHTML(step);
      runningSteps.delete(step.tool);
    } else {
      const fresh = document.createElement("div");
      fresh.className = "step";
      fresh.innerHTML = stepHTML(step);
      traceEl.appendChild(fresh);
    }
  }
  traceEl.scrollTop = traceEl.scrollHeight;
}

function finalizeRunning() {
  runningSteps.forEach((node) => {
    const dot = node.querySelector(".dot");
    if (dot) {
      dot.classList.remove("running");
      dot.classList.add("info");
    }
  });
  runningSteps = new Map();
}

function renderClarify(questions) {
  const box = document.createElement("div");
  box.className = "callout warn";
  box.innerHTML = `<strong>Quick check before I plan:</strong><div class="questions"></div>`;
  const qWrap = box.querySelector(".questions");
  questions.forEach((q) => {
    const row = document.createElement("div");
    row.className = "qrow";
    const opts = (q.options || [])
      .map((o) => `<button class="chip" data-answer="${esc(o)}">${esc(o)}</button>`)
      .join("");
    row.innerHTML = `<div class="qtext">${esc(q.question)}</div><div class="chips">${opts}</div>`;
    qWrap.appendChild(row);
  });
  const skip = document.createElement("button");
  skip.className = "ghost";
  skip.textContent = "Plan anyway with sensible assumptions";
  skip.onclick = () => runPlanner(true);
  box.appendChild(skip);

  box.querySelectorAll("[data-answer]").forEach((btn) => {
    btn.onclick = () => {
      const answer = btn.getAttribute("data-answer");
      inputEl.value = `${inputEl.value.trim()} ${answer}`.trim();
      box.remove();
      runPlanner(false);
    };
  });

  clearEmptyState(planEl);
  planEl.prepend(box);
}

function money(amount, currency) {
  const n = Number(amount || 0).toLocaleString(currency === "USD" ? "en-US" : "en-IN");
  const symbols = { INR: "₹", USD: "$", EUR: "€", GBP: "£", JPY: "¥", SGD: "S$", AED: "AED ", AUD: "A$" };
  return `${symbols[currency] || ""}${n}`;
}

function itemCard(item, currency) {
  const tags = (item.tags || [])
    .map((t) => `<span class="tag ${t === "live-data" ? "live" : ""}">${esc(t)}</span>`)
    .join("");
  const note = item.note ? `<div class="note">${esc(item.note)}</div>` : "";
  const cost = Number(item.cost) > 0 ? money(item.cost, currency) : "Free";
  const travel =
    item.travel_mins > 0
      ? ` · ${item.travel_mins} min travel${item.distance_km ? ` (${item.distance_km} km)` : ""}`
      : "";
  return (
    `<div class="card">` +
    `<div class="time">${esc(item.start_time)} · ${esc(item.duration_mins)} min${esc(travel)}</div>` +
    `<h3>${esc(item.title)}</h3>` +
    `<p class="desc">${esc(item.description)}</p>` +
    `<div class="why">${esc(item.why)}</div>` +
    `<div class="foot"><div class="tagrow">${tags}</div><div class="cost">${esc(cost)}</div></div>` +
    note +
    `</div>`
  );
}

function renderPlan(plan) {
  clearEmptyState(planEl);
  const items = Array.isArray(plan.items) ? plan.items : [];
  const totalMins = Number(plan.total_duration_mins) || 0;
  const budgetPill =
    plan.budget != null
      ? `<span class="pill ${plan.within_budget ? "good" : "warn"}">${
          plan.within_budget ? "Within budget" : "Over budget"
        } · ${esc(money(plan.total_cost, plan.currency))} / ${esc(money(plan.budget, plan.currency))}</span>`
      : `<span class="pill">Est. ${esc(money(plan.total_cost, plan.currency))}</span>`;

  const sourceLabel =
    plan.source === "osm" ? "Live OpenStreetMap data" : plan.source === "mixed" ? "Mixed live + curated" : "Curated data";

  const tradeoffs = (plan.tradeoffs || []).length
    ? `<div class="callout warn"><strong>Trade-offs &amp; notes</strong><ul>${plan.tradeoffs
        .map((t) => `<li>${esc(t)}</li>`)
        .join("")}</ul></div>`
    : "";

  planEl.innerHTML =
    `<div class="plan-head"><h2>${esc(plan.headline)}</h2><p>${esc(plan.summary)}</p></div>` +
    `<div class="meta-row">` +
    budgetPill +
    `<span class="pill">${esc(Math.round(totalMins / 6) / 10)}h door-to-door</span>` +
    `<span class="pill">${esc(items.length)} stops</span>` +
    `<span class="pill">${esc(sourceLabel)}</span>` +
    `</div>` +
    `<div class="timeline">${items.map((i) => itemCard(i, plan.currency)).join("")}</div>` +
    tradeoffs;
}

function renderError(message) {
  clearEmptyState(planEl);
  const box = document.createElement("div");
  box.className = "callout error";
  box.innerHTML = `<strong>Something went wrong.</strong><div>${esc(message)}</div>`;
  planEl.prepend(box);
}

function handleEvent(event) {
  switch (event.type) {
    case "trace":
      renderTrace(event.step);
      break;
    case "clarify":
      renderClarify(event.questions);
      break;
    case "plan":
      renderPlan(event.plan);
      break;
    case "error":
      renderError(event.message);
      break;
    case "done":
      finalizeRunning();
      break;
    default:
      break;
  }
}

function parseFrame(frame) {
  const line = frame.split(/\r?\n/).find((l) => l.startsWith("data:"));
  if (!line) return;
  try {
    handleEvent(JSON.parse(line.slice(5).trim()));
  } catch {
    /* ignore malformed frame */
  }
}

async function runPlanner(force = false) {
  const text = inputEl.value.trim();
  if (!text && !force) {
    inputEl.focus();
    return;
  }

  if (currentController) currentController.abort();
  const controller = new AbortController();
  currentController = controller;

  setBusy(true);
  traceEl.innerHTML = "";
  runningSteps = new Map();
  planEl.innerHTML = `<p class="empty">Thinking…</p>`;

  try {
    const res = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: text, force, simulate_outage: Boolean(outageEl && outageEl.checked) }),
      signal: controller.signal,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `Request failed (${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? "";
      frames.forEach(parseFrame);
    }
    if (buffer.trim()) parseFrame(buffer);
  } catch (err) {
    if (err.name !== "AbortError") renderError(err.message || String(err));
  } finally {
    finalizeRunning();
    if (currentController === controller) {
      currentController = null;
      setBusy(false);
    }
  }
}

document.getElementById("examples").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-example]");
  if (!btn) return;
  inputEl.value = btn.getAttribute("data-example");
  inputEl.focus();
});

goBtn.addEventListener("click", () => runPlanner(false));

const SURPRISES = [
  "Bangalore, ₹2500, 5 hours, energetic and social, into music, games and food, no constraints",
  "London, 4 hours, tired but wants something fun, love art, books and coffee, avoid crowded places",
  "San Francisco, $80, 6 hours, adventurous, nature, walks and food, vegetarian",
  "Delhi, ₹1500, 3 hours, cozy and relaxed, into history, walks and street food, avoid crowds",
];

randomizeBtn.addEventListener("click", () => {
  inputEl.value = SURPRISES[Math.floor(Math.random() * SURPRISES.length)];
  runPlanner(false);
});
