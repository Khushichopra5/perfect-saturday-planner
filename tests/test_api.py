import json

from fastapi.testclient import TestClient

from planner.main import app

client = TestClient(app)


def parse_sse(text):
    events = []
    for frame in text.split("\n\n"):
        for line in frame.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["llm"] is False


def test_index_serves_the_ui():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Plan a perfect Saturday" in resp.text
    assert "/static/app.js" in resp.text


def test_static_assets_are_served():
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_plan_streams_from_free_text():
    resp = client.post(
        "/api/plan",
        json={
            "input": "Bangalore, ₹2000, 4 hours, relaxed, food music walks, vegetarian, avoid crowded",
            "force": True,
        },
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    events = parse_sse(resp.text)
    assert events[-1]["type"] == "done"
    plan = next(e["plan"] for e in events if e["type"] == "plan")
    assert plan["city"] == "Bangalore"
    assert plan["items"]


def test_plan_accepts_the_structured_brief_shape():
    resp = client.post(
        "/api/plan",
        json={
            "city": "Bangalore",
            "budget": 2000,
            "available_time": "4 hours",
            "mood": "tired but wants to do something fun",
            "interests": ["food", "music", "walks"],
            "constraints": ["vegetarian", "avoid crowded places"],
        },
    )
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    plan = next(e["plan"] for e in events if e["type"] == "plan")
    assert plan["city"] == "Bangalore"
    assert plan["budget"] == 2000
    assert plan["items"]


def test_clarifying_then_force():
    first = parse_sse(client.post("/api/plan", json={"input": "plan my saturday"}).text)
    assert any(e["type"] == "clarify" for e in first)

    forced = parse_sse(client.post("/api/plan", json={"input": "plan my saturday", "force": True}).text)
    assert any(e["type"] == "plan" for e in forced)


def test_simulate_outage_flag_degrades_gracefully():
    resp = client.post(
        "/api/plan",
        json={
            "input": "Bangalore, ₹2000, 4 hours, relaxed, food and walks",
            "force": True,
            "simulate_outage": True,
        },
    )
    events = parse_sse(resp.text)
    plan = next(e["plan"] for e in events if e["type"] == "plan")
    assert plan["source"] == "mock"
    assert any(e["type"] == "trace" and e["step"]["status"] == "fallback" for e in events)


def test_empty_body_returns_400():
    assert client.post("/api/plan", json={}).status_code == 400


def test_invalid_json_returns_400():
    resp = client.post("/api/plan", content="{not json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 400
