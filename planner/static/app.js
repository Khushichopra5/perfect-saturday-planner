const inputEl = document.getElementById("input");
const traceEl = document.getElementById("trace");
const planEl = document.getElementById("plan");
const goBtn = document.getElementById("go");
const randomizeBtn = document.getElementById("randomize");

const DOT_ICON = { ok: "✓", fallback: "!", error: "×", info: "i", running: "" };

let runningSteps = new Map();

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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
    const node = document.createElement("div");
    node.className = "step";
    node.innerHTML = stepHTML(step);
    traceEl.appendChild(node);
    runningSteps.set(step.tool, node);
  } else {
    const existing = runningSteps.get(step.tool);
    if (existing) {
      existing.innerHTML = stepHTML(step);
      runningSteps.delete(step.tool);
    } else {
      const node = document.createElement("div");
      node.className = "step";
      node.innerHTML = stepHTML(step);
      traceEl.appendChild(node);
    }
  }
  traceEl.scrollTop = traceEl.scrollHeight;
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
  return currency === "USD" ? `$${n}` : `₹${n}`;
}

function itemCard(item, currency) {
  const tags = (item.tags || [])
    .map((t) => {
      const live = t === "live-data" || t === "curated" || t === "quiet";
      return `<span class="tag ${live ? "live" : ""}">${esc(t)}</span>`;
    })
    .join("");
  const note = item.note ? `<div class="note">${esc(item.note)}</div>` : "";
  const cost = Number(item.cost) > 0 ? money(item.cost, currency) : "Free";
  return (
    `<div class="card">` +
    `<div class="time">${esc(item.start_time)} · ${esc(item.duration_mins)} min</div>` +
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
  const budgetPill =
    plan.budget != null
      ? `<span class="pill ${plan.within_budget ? "good" : "warn"}">${
          plan.within_budget ? "Within budget" : "Over budget"
        } · ${esc(money(plan.total_cost, plan.currency))} / ${esc(money(plan.budget, plan.currency))}</span>`
      : `<span class="pill">Est. ${esc(money(plan.total_cost, plan.currency))}</span>`;

  const sourceLabel = plan.source === "osm" ? "Live OpenStreetMap data" : plan.source === "mixed" ? "Mixed live + curated" : "Curated data";

  const tradeoffs = (plan.tradeoffs || []).length
    ? `<div class="callout warn"><strong>Trade-offs &amp; notes</strong><ul>${plan.tradeoffs
        .map((t) => `<li>${esc(t)}</li>`)
        .join("")}</ul></div>`
    : "";

  planEl.innerHTML =
    `<div class="plan-head"><h2>${esc(plan.headline)}</h2><p>${esc(plan.summary)}</p></div>` +
    `<div class="meta-row">` +
    budgetPill +
    `<span class="pill">${esc(Math.round(plan.total_duration_mins / 6) / 10)}h door-to-door</span>` +
    `<span class="pill">${esc(plan.items.length)} stops</span>` +
    `<span class="pill">${esc(sourceLabel)}</span>` +
    `</div>` +
    `<div class="timeline">${plan.items.map((i) => itemCard(i, plan.currency)).join("")}</div>` +
    tradeoffs;
}

function renderError(message) {
  clearEmptyState(planEl);
  const box = document.createElement("div");
  box.className = "callout error";
  box.innerHTML = `<strong>Something went wrong.</strong><div>${esc(message)}</div>`;
  planEl.prepend(box);
}

async function runPlanner(force = false) {
  const text = inputEl.value.trim();
  if (!text && !force) {
    inputEl.focus();
    return;
  }

  goBtn.disabled = true;
  goBtn.textContent = "Planning…";
  traceEl.innerHTML = "";
  runningSteps = new Map();
  planEl.innerHTML = `<p class="empty">Thinking…</p>`;

  try {
    const res = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: text, force }),
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

      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const dataLine = frame.split("\n").find((l) => l.startsWith("data: "));
        if (!dataLine) continue;
        let event;
        try {
          event = JSON.parse(dataLine.slice(6));
        } catch {
          continue;
        }
        handleEvent(event);
      }
    }
  } catch (err) {
    renderError(err.message || String(err));
  } finally {
    goBtn.disabled = false;
    goBtn.textContent = "Plan my Saturday";
  }
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
      runningSteps = new Map();
      break;
    default:
      break;
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
