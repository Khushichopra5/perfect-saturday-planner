#!/usr/bin/env python
"""True end-to-end test: boot the real uvicorn server and stream from it.

Unlike the pytest suite (which uses an in-process TestClient), this exercises
the actual ASGI server over a real TCP socket, including SSE streaming, static
files and error responses.

    python scripts/e2e_live.py           # offline, deterministic
    python scripts/e2e_live.py --live    # allow real OpenStreetMap network calls
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_health(base: str, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{base}/health", timeout=2)
            if resp.status_code == 200:
                return True
        except httpx.HTTPError:
            time.sleep(0.25)
    return False


def stream_plan(base: str, payload: dict, timeout: float = 120.0) -> tuple[int, list[dict]]:
    events: list[dict] = []
    with httpx.stream("POST", f"{base}/api/plan", json=payload, timeout=timeout) as resp:
        status = resp.status_code
        if status != 200:
            resp.read()
            return status, events
        buffer = ""
        for chunk in resp.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                for line in frame.splitlines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))
    return status, events


class Harness:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"  PASS  {name}")
        else:
            self.failed += 1
            print(f"  FAIL  {name} {detail}")

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} checks passed")
        return 1 if self.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="allow real OpenStreetMap calls")
    args = parser.parse_args()

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    if not args.live:
        env["PLANNER_OFFLINE"] = "1"
    env.pop("OPENAI_API_KEY", None)

    print(f"Starting server on {base} (live={args.live})")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "planner.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    harness = Harness()
    try:
        if not wait_for_health(base):
            out = server.stdout.read().decode() if server.stdout else ""
            print("Server failed to start:\n", out)
            return 1

        print("\nHTTP surface")
        health = httpx.get(f"{base}/health", timeout=5).json()
        harness.check("health returns ok", health.get("status") == "ok", str(health))

        index = httpx.get(f"{base}/", timeout=5)
        harness.check("index serves the UI", index.status_code == 200 and "Plan a perfect Saturday" in index.text)

        css = httpx.get(f"{base}/static/styles.css", timeout=5)
        js = httpx.get(f"{base}/static/app.js", timeout=5)
        harness.check("static assets served", css.status_code == 200 and js.status_code == 200)

        print("\nFree-text plan stream")
        status, events = stream_plan(
            base,
            {
                "input": "I'm in Bangalore with about ₹2000 and 4 hours. Tired but want something fun. "
                "I like food, music and walks. I'm vegetarian and avoid crowded places.",
                "force": True,
            },
        )
        types = [e["type"] for e in events]
        plan = next((e["plan"] for e in events if e["type"] == "plan"), None)
        harness.check("stream returns 200", status == 200, str(status))
        harness.check("stream ends with done", bool(types) and types[-1] == "done", str(types[-3:]))
        harness.check("plan event present", plan is not None)
        if plan:
            harness.check("plan has stops", len(plan["items"]) >= 1, str(len(plan["items"])))
            harness.check("every stop explains itself", all(i["why"] for i in plan["items"]))
            harness.check("cost equals sum of items", plan["total_cost"] == sum(i["cost"] for i in plan["items"]))
            harness.check("plan has a trace of tools", len([e for e in events if e["type"] == "trace"]) >= 6)

        print("\nStructured brief input")
        status, events = stream_plan(
            base,
            {
                "city": "Bangalore",
                "budget": 2000,
                "available_time": "4 hours",
                "mood": "tired but wants to do something fun",
                "interests": ["food", "music", "walks"],
                "constraints": ["vegetarian", "avoid crowded places"],
            },
        )
        plan = next((e["plan"] for e in events if e["type"] == "plan"), None)
        harness.check("structured input returns a plan", plan is not None)
        if plan:
            harness.check("city parsed from structured input", plan["city"] == "Bangalore", plan["city"])
            harness.check("budget parsed from structured input", plan["budget"] == 2000, str(plan["budget"]))
            food = [i for i in plan["items"] if i["kind"] == "food"]
            harness.check("vegetarian constraint honoured", all("not-vegetarian" not in i["tags"] for i in food))

        print("\nClarifying-question flow")
        _, events = stream_plan(base, {"input": "plan my saturday"})
        harness.check("vague input asks questions", any(e["type"] == "clarify" for e in events))
        harness.check("vague input does not plan yet", not any(e["type"] == "plan" for e in events))
        _, forced = stream_plan(base, {"input": "plan my saturday", "force": True})
        harness.check("force proceeds to a plan", any(e["type"] == "plan" for e in forced))

        print("\nFailure handling")
        harness.check("empty body -> 400", httpx.post(f"{base}/api/plan", json={}, timeout=5).status_code == 400)
        harness.check(
            "invalid json -> 400",
            httpx.post(f"{base}/api/plan", content="{nope", headers={"Content-Type": "application/json"}, timeout=5).status_code == 400,
        )
        _, events = stream_plan(base, {"input": "I'm in Zzyzxville with 4 hours and food", "force": True})
        plan = next((e["plan"] for e in events if e["type"] == "plan"), None)
        harness.check("unknown city still yields a plan", plan is not None)
        harness.check(
            "unknown city shows a fallback step",
            any(e["type"] == "trace" and e["step"]["status"] == "fallback" for e in events),
        )

        if args.live:
            print("\nLive OpenStreetMap data")
            _, events = stream_plan(
                base,
                {"input": "Bangalore, ₹2000, 4 hours, relaxed, food music walks, vegetarian", "force": True},
                timeout=120,
            )
            plan = next((e["plan"] for e in events if e["type"] == "plan"), None)
            harness.check("live run still produces a plan", plan is not None)
            if plan:
                harness.check("plan cites its data source", plan["source"] in ("osm", "mixed", "mock"), plan["source"])
                print(f"        source={plan['source']} stops={[i['title'] for i in plan['items']]}")

    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    return harness.summary()


if __name__ == "__main__":
    raise SystemExit(main())
