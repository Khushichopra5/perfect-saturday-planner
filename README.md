# Perfect Saturday Planner

An AI agent that turns a one-line request into a realistic, timed Saturday plan —
with a live trace of every step it took.

> **Live URL:** _add the deployed URL here_ (see [Deploy](#deploy) — one-click Render/Railway/Fly/Docker).

```
I'm in Bangalore with about ₹2000 and 4 hours. I'm tired but want to do
something fun. I like food, music and walks. I'm vegetarian and want to
avoid crowded places.
```

The agent parses that, looks up **real places on OpenStreetMap**, builds a timed
itinerary, explains why each stop fits, checks it against your time/budget/constraints,
and streams its thinking to the browser as it goes.

---

## What it does

| Requirement | How it's met |
| --- | --- |
| Hosted UI | FastAPI + a single-page UI, SSE streaming, one-click deploy configs included |
| Understands preferences | `parseUserPreferences` handles free text **and** the structured JSON brief |
| At least 3 tools | 6 tools, no giant prompt (see below) |
| Realistic, specific plan | Real OSM places, timed with travel buffers, sized to your available hours |
| Explains each part | Every stop carries a `why` written from your mood, interests and constraints |
| Handles a failure gracefully | Multiple failure paths, all user-visible (see below) |
| Shows a trace | Live "agent is thinking" stream of each tool call, status and duration |

### Tools (each independently testable)

1. `parseUserPreferences(input)` — free text or structured → normalised `Preferences`, plus documented assumptions.
2. `geocodeCity(city)` — OpenStreetMap **Nominatim**, with an offline city index fallback.
3. `getActivityOptions(city, interests, mood, constraints)` — OSM **Overpass**, then Nominatim POI search, then a curated catalogue.
4. `getFoodOptions(city, budget, constraints)` — same layered approach, vegetarian-aware.
5. `estimateCost(plan, budget)` — uses real `charge`/`fee` tags when present, then curated costs, then category defaults.
6. `validatePlan(plan, constraints)` + `generateFinalPlan(context)` — self-checks time/budget/constraints, then trims and re-times.

The agent (`planner/agent.py`) is only an orchestrator: it decides the order and
streams events. All the intelligence lives in small, unit-tested tools.

---

## Failure handling (all visible in the trace)

- **City not found / no city** → builds a sensible template plan and says so.
- **Overpass down or rate-limited (504s happen)** → automatically falls back to a
  Nominatim POI search for real places, then to a curated catalogue.
- **Too few options for your interests** → broadens to the curated catalogue.
- **Plan runs over your time window** → trims the least essential stop and re-times.
- **Vegetarian constraint violated** → drops the offending food stop.
- **Over budget** → keeps the plan but explains the trade-off and what to drop.
- **Anything unexpected** → streamed as an `error` event; the server never crashes.

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
# unit + in-process API tests (52 tests, offline & deterministic)
pytest -q

# true end-to-end: boots a real uvicorn server and streams from it
python scripts/e2e_live.py          # offline
python scripts/e2e_live.py --live   # hits real OpenStreetMap
```

Both suites pass: **52/52** pytest, **23/23** live-server checks (including real
OpenStreetMap data).

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

Responses are `text/event-stream` with `trace`, `clarify`, `plan`, `error` and
`done` events. `GET /health` is the health check.

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
  parse.py (prefs)         places.py (OSM live)         cost / validate /
                     Overpass ▶ Nominatim ▶ catalogue   generate (planning)
```

```
planner/
├── main.py          FastAPI app + SSE endpoint
├── agent.py         orchestrator + trace + failure handling
├── llm.py           optional LLM narrator (off by default)
├── models.py        dataclasses
├── data/mock_data.py  known cities + curated catalogue
├── tools/           parse, places, cost, validate, generate
└── static/          index.html, styles.css, app.js
```

---

## Deploy

The app is a standard ASGI app, so it runs anywhere. Fastest options:

**Render** (free tier): push to GitHub → New → Blueprint → pick the repo. The
included `render.yaml` sets the build/start commands and health check.

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
