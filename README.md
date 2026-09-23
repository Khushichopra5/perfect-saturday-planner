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
| **Understands preferences** | `parseUserPreferences` handles free text **and** the exact structured JSON brief |
| **≥ 3 tools/functions** | 8 tools, no giant prompt (below) |
| **Realistic, specific plan** | Real OSM places, ordered by real distance, timed with travel buffers, sized to your hours |
| **Explains why each part fits** | Every stop carries a `why` built from your mood, interests and constraints |
| **Handles a failure case** | Six distinct failure paths, all visible in the trace (below) |
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

1. `parseUserPreferences(input)` — free text or structured → normalised `Preferences`, plus documented assumptions.
2. `geocodeCity(city)` — Nominatim, with an offline city index fallback.
3. `getActivityOptions(city, interests, mood, constraints)` — Overpass → Nominatim POI search → curated catalogue.
4. `getFoodOptions(city, budget, constraints)` — same layered approach, vegetarian-aware.
5. `estimateCost(plan, budget)` — real `charge`/`fee` tags when present, then curated costs, then category defaults.
6. `validatePlan(plan, constraints)` — checks time (incl. travel), budget, vegetarian and crowd constraints.
7. `generateFinalPlan(context)` — orders by proximity, times the day, swaps closed stops, writes the "why".
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

Requires Python 3.11+.

```bash
git clone <your-repo> && cd Kassmt
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

uvicorn planner.main:app --reload
# open http://127.0.0.1:8000
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv venv && uv pip install -r requirements-dev.txt
uv run uvicorn planner.main:app --reload
```

Set `PLANNER_OFFLINE=1` to force the curated catalogue (no network calls).

### Optional: LLM narrator

The planner works fully without any LLM. If you set an OpenAI-compatible key it
will additionally polish the headline, summary and per-stop explanations:

```bash
cp .env.example .env   # then fill in OPENAI_API_KEY
```

---

## Test

```bash
# unit + in-process API tests (69 tests, offline & deterministic)
pytest -q

# true end-to-end: boots a real uvicorn server and streams from it
python scripts/e2e_live.py          # offline
python scripts/e2e_live.py --live   # hits real OpenStreetMap
```

Both suites pass: **69/69** pytest, **28/28** live-server checks (including real
OpenStreetMap data and real travel distances).

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

I built this with an AI coding assistant (opencode) as a pair-programmer: it
scaffolded the FastAPI app and tool modules, ported the planning heuristics, and
generated the pytest + end-to-end suites. I used it most for debugging real-world
integration issues — e.g. it helped me discover that Nominatim 403s a User-Agent
containing `example.com`, and that the Overpass query needed a total time budget
plus a second data source to stay responsive. All design decisions (tool
decomposition, fallback ordering, streaming trace) and the final review were mine.
