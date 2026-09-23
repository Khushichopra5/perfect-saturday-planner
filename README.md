# Perfect Saturday Planner

[![CI / CD](https://github.com/Khushichopra5/perfect-saturday-planner/actions/workflows/deploy.yml/badge.svg)](https://github.com/Khushichopra5/perfect-saturday-planner/actions/workflows/deploy.yml)

An AI agent that turns a one-line request into a realistic, timed Saturday plan —
with a live trace of every step it took.

> **Live URL:** **https://perfect-saturday-planner.onrender.com**
> **Repo:** https://github.com/Khushichopra5/perfect-saturday-planner
>
> _Render's free tier sleeps after inactivity — the first load can take ~30–60s to wake up._

```
I'm in Bangalore with about ₹2000 and 4 hours. I'm tired but want to do
something fun. I like food, music and walks. I'm vegetarian and want to
avoid crowded places.
```

The agent parses that, looks up **real places on OpenStreetMap**, builds a timed
itinerary ordered by proximity, explains why each stop fits, checks it against your
time/budget/constraints, and streams its thinking to the browser as it goes.

---

## Requirement coverage

### Required behaviour

| Requirement | Where it lives |
| --- | --- |
| **Hosted UI** | FastAPI + single-page UI with SSE streaming; `Dockerfile`, `render.yaml`, `Procfile` included |
| **Understands preferences** | `parseUserPreferences` handles free text; `parseStructured` handles the exact structured JSON brief |
| **≥ 3 tools/functions** | 8 tools, no giant prompt (below) |
| **Realistic, specific plan** | Real OSM places, ordered by real distance, timed with travel buffers, sized to your hours |
| **Explains why each part fits** | Every stop carries a `why` built from your mood, interests and constraints |
| **Handles a failure case** | Eight distinct failure paths, all visible in the trace (below) |
| **Shows a trace** | Live "agent is thinking" stream of each tool call, its status and duration |

### Bonus points

| Bonus | How it's done |
| --- | --- |
| **Real data instead of mocks** | OpenStreetMap **Overpass** for places + **Nominatim** for geocoding *and* as a second POI source. No API keys. |
| **Streaming trace** | Server-Sent Events; the UI updates each step from spinner → result with timings. |
| **Fallback plan when nothing matches** | Layered: Overpass → Nominatim → curated catalogue, with an explicit "no live options matched" message. |
| **1–2 clarifying questions when vague** | `detectClarifications` asks at most two, and the UI offers one-tap answers plus a "plan anyway" escape. |
| **Explains trade-offs** | Over-budget, time-trimmed, crowd-flagged, vegetarian substitutions, long hops, and closed-place swaps. |
| **Avoids unrealistic suggestions** | Real travel times + nearest-neighbour ordering + **opening-hours** checks that swap out likely-closed venues. |

### Tools (each independently unit-tested)

1. `parseUserPreferences(input)` / `parseStructured(payload)` — free text or the exact JSON brief → normalised `Preferences`, plus documented assumptions.
2. `geocodeCity(city)` — Nominatim, with an offline city index fallback.
3. `getActivityOptions(geo, interests, moodTags, avoidCrowded)` — Overpass → Nominatim POI search → curated catalogue.
4. `getFoodOptions(geo, vegetarian, avoidCrowded)` — same layered approach, vegetarian-aware.
5. `estimateCost(itemCosts, budget, currency)` — real `charge`/`fee` tags when present, then curated costs, then category defaults.
6. `validatePlan(items, prefs, totalCost)` — checks time (incl. travel), vegetarian and crowd constraints (budget trade-offs come from `generateFinalPlan`).
7. `generateFinalPlan(activities, foods, prefs, usedFallback, origin)` — orders by proximity, times the day, swaps closed stops, writes the "why".
8. `openingHours` / `geo` helpers — parse OSM `opening_hours` and compute haversine distance + travel time.

The agent (`planner/agent.py`) is only an orchestrator: it decides the order and
streams events. All the intelligence lives in small, unit-tested tools.

---

## Failure handling (all visible in the trace)

- **City not found / no city** → builds a sensible template plan and says so.
- **Overpass down or rate-limited (504s happen)** → automatically falls back to a
  Nominatim POI search for real places, then to a curated catalogue.
- **No options match your interests** → broadens to the curated catalogue and says so.
- **Plan runs over your time window** → trims the least essential stop and re-times.
- **Vegetarian constraint violated** → drops the offending food stop.
- **A venue looks closed at its slot** → swaps it for the next best open option.
- **Over budget** → keeps the plan but explains the trade-off and what to drop.
- **Anything unexpected** → streamed as an `error` event; the server never crashes.

You can see all of this without breaking anything: the UI has a
**"Simulate a live-data outage"** toggle (or send `"simulate_outage": true`) that
forces the graceful-degradation path.

---

## Run locally

Requires **Python 3.11+** (3.12 recommended) and `git`.

```bash
# 1. Clone and enter the project
git clone https://github.com/Khushichopra5/perfect-saturday-planner.git
cd perfect-saturday-planner

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1

# 3. Install dependencies (runtime + test/lint tools)
pip install -r requirements-dev.txt

# 4. Start the server
python -m uvicorn planner.main:app --reload
```

Then open **http://127.0.0.1:8000** in your browser.

> `python -m uvicorn ...` is used instead of bare `uvicorn` so it works even when
> the venv's scripts folder isn't on your `PATH`. `python -m planner.main` does the
> same thing and honours the `PORT` environment variable.

### Or with [uv](https://docs.astral.sh/uv/) (no manual venv activation)

```bash
uv venv
uv pip install -r requirements-dev.txt
uv run uvicorn planner.main:app --reload
```

### Offline mode

Set `PLANNER_OFFLINE=1` before starting the server to force the curated catalogue
(no network calls), e.g. `PLANNER_OFFLINE=1 python -m uvicorn planner.main:app`.

### Optional: LLM narrator

The planner works fully without any LLM — the narrator is entirely optional. To
enable it, create a `.env` with an OpenAI-compatible key and **restart the server**
(the file is only read at startup):

```bash
cp .env.example .env   # then fill in OPENAI_API_KEY
# then restart: python -m uvicorn planner.main:app --reload
```

---

## Test

```bash
# unit + in-process API tests (offline & deterministic)
pytest -q

# true end-to-end: boots a real uvicorn server and streams from it
python scripts/e2e_live.py          # offline — 25/25 checks
python scripts/e2e_live.py --live   # real OpenStreetMap — 28/28 checks

# or point the same suite at a deployment
python scripts/e2e_live.py --url https://perfect-saturday-planner.onrender.com
```

Both pass: **91/91** pytest, **25/25** offline e2e checks, and **28/28** live
checks (the extra 3 are the real OpenStreetMap assertions).

---

## API

Free text:

```bash
curl -N -X POST localhost:8000/api/plan \
  -H 'Content-Type: application/json' \
  -d '{"input":"Bangalore, ₹2000, 4 hours, tired but fun, food music walks, vegetarian, avoid crowds"}'
```

Or the structured brief shape (exactly as specified in the assignment):

```bash
curl -N -X POST localhost:8000/api/plan \
  -H 'Content-Type: application/json' \
  -d '{
    "city": "Bangalore",
    "budget": 2000,
    "available_time": "4 hours",
    "mood": "tired but wants to do something fun",
    "interests": ["food", "music", "walks"],
    "constraints": ["vegetarian", "avoid crowded places"]
  }'
```

Optional fields: `"force": true` (skip clarifying questions) and
`"simulate_outage": true` (demo the fallback). Responses are `text/event-stream`
with `trace`, `clarify`, `plan`, `error` and `done` events. `GET /health` is the
health check.

---

## Architecture

```
browser  ──POST /api/plan──▶  FastAPI (planner/main.py)
   ▲                                │
   │  SSE: trace / clarify / plan   ▼
   └──────────────────────  agent.run_agent()  ──▶  tools/*
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
  parse.py (prefs)         places.py (OSM live)         cost / geo / hours /
                     Overpass ▶ Nominatim ▶ catalogue   validate / generate
```

```
planner/
├── main.py          FastAPI app + SSE endpoint
├── agent.py         orchestrator + trace + failure handling
├── llm.py           optional LLM narrator (off by default)
├── models.py        dataclasses
├── data/mock_data.py  known cities + curated catalogue
├── tools/           parse, places, cost, geo, hours, validate, generate
└── static/          index.html, styles.css, app.js
```

---

## Deploy

### Continuous deployment (how this repo is wired)

Every push to `main` runs `.github/workflows/deploy.yml`, which:

1. installs dependencies, runs `ruff`, `pytest`, and the offline end-to-end suite;
2. if all green, calls the Render API to trigger a deploy:

   ```
   POST https://api.render.com/v1/services/$RENDER_SERVICE_ID/deploys
   Authorization: Bearer $RENDER_API_KEY
   ```

The Render API key and service ID live in GitHub Actions **repository secrets**
(`RENDER_API_KEY`, `RENDER_SERVICE_ID`) — never in the code. So `git push` →
tests pass → the live URL updates automatically. You can watch runs on the
[Actions tab](https://github.com/Khushichopra5/perfect-saturday-planner/actions).

### Deploying elsewhere

The app is a standard ASGI app, so it runs anywhere:

**Render** (free tier): New → Blueprint → pick the repo. The included
`render.yaml` sets the build/start commands and health check.

**Railway / Fly / Heroku**: use the included `Procfile` or `Dockerfile`.

**Docker** anywhere:

```bash
docker build -t saturday-planner .
docker run -p 8000:8000 saturday-planner
```

No secrets are required for the core experience. Overpass/Nominatim are free and
keyless; only the optional LLM narrator needs a key.

---

## Notes & limitations

- Public Overpass instances are occasionally slow (504). That is exactly why
  there are two live sources and a curated fallback — the plan always renders.
- Costs are estimates (OSM `charge` tags are sparse); they are labelled as estimates.
- Opening hours are parsed from a common subset of the OSM spec; anything unclear
  is treated as "unknown" rather than guessed.
- The LLM narrator is intentionally optional: the itinerary itself is deterministic
  so it is reproducible and testable.

## How I used AI tools during the build

I used an AI coding assistant (opencode) as a pair-programmer to scaffold the
FastAPI app and tool modules. I leaned on it most to debug real integration
issues: Nominatim 403s a User-Agent containing `example.com`, and Overpass needs
a total time budget plus a second data source to stay responsive. I made the
design calls (tool decomposition, fallback ordering, streaming trace) and reviewed
the final result.
