"""Perfect Saturday Planner — an AI agent that plans a fun Saturday.

The package is split so the agent is easy to reason about:

* ``planner.tools``  — small, individually testable tool functions.
* ``planner.agent``  — the orchestrator that calls the tools and emits a trace.
* ``planner.main``   — the FastAPI app that streams the trace to the web UI.
"""

__version__ = "1.0.0"
