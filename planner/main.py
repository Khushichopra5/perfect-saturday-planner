"""FastAPI app: serves the UI and streams the agent trace over SSE.

Run locally with::

    uvicorn planner.main:app --reload

or::

    python -m planner.main
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from . import __version__, llm
from .agent import parse_payload, run_agent_from_prefs, run_agent_safe

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Perfect Saturday Planner", version=__version__)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class PlanRequest(BaseModel):
    """Accepts either free text (``input``) or the structured brief shape."""

    model_config = ConfigDict(extra="allow")

    input: str | None = None
    force: bool = False


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _stream(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    async for event in events:
        yield _sse(event)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "perfect-saturday-planner", "version": __version__, "llm": llm.enabled()}


@app.get("/api/health")
async def api_health() -> dict[str, Any]:
    return await health()


@app.post("/api/plan", response_model=None)
async def plan(request: Request) -> StreamingResponse | JSONResponse:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Request body must be a JSON object"}, status_code=400)

    force = bool(payload.get("force"))
    text, prefs = parse_payload(payload)

    if text is None and prefs is None:
        return JSONResponse({"error": "Please describe your Saturday first."}, status_code=400)

    events = run_agent_safe(text, force) if text is not None else run_agent_from_prefs(prefs, force)  # type: ignore[arg-type]
    return StreamingResponse(
        _stream(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def run() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("planner.main:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    run()
