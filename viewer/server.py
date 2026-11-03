"""Viewer server: lists runs, serves their events, and streams runs live.

    python -m viewer.server              # http://127.0.0.1:8000, reads ./runs
    python -m viewer.server --runs other_dir --port 8001

The engine flushes one JSON line per event, so a run that is still in
progress can be followed live from its log file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"
RUN_NAME = re.compile(r"^[\w.-]+\.jsonl$")
POLL_SECONDS = 0.5


def read_events(path: Path, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """Complete JSON lines from byte `offset`. Returns events and the new offset.

    A partly written last line is left for the next read.
    """
    with path.open("rb") as f:
        f.seek(offset)
        data = f.read()
    end = data.rfind(b"\n") + 1
    events = [json.loads(line) for line in data[:end].splitlines() if line.strip()]
    return events, offset + end


def create_app(runs_dir: Path) -> FastAPI:
    app = FastAPI(title="s2devil viewer")
    runs_dir = runs_dir.resolve()

    @app.middleware("http")
    async def revalidate_static(request, call_next):
        """Make browsers check for a newer page/script instead of using a stale copy."""
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    def run_path(name: str) -> Path:
        if not RUN_NAME.match(name) or name.endswith("_trace.jsonl"):
            raise HTTPException(404, "unknown run")
        path = (runs_dir / name).resolve()
        if path.parent != runs_dir or not path.is_file():
            raise HTTPException(404, "unknown run")
        return path

    @app.get("/api/runs")
    def list_runs() -> list[dict[str, Any]]:
        runs = []
        for path in runs_dir.glob("*.jsonl"):
            if path.name.endswith("_trace.jsonl"):
                continue
            events, _ = read_events(path)
            last = events[-1] if events else None
            end = last["data"] if last and last["type"] == "tournament_end" else {}
            runs.append(
                {
                    "name": path.name,
                    "modified": path.stat().st_mtime,
                    "events": len(events),
                    "finished": bool(last and last["type"] == "tournament_end"),
                    "winner": end.get("winner"),
                    "aborted": end.get("aborted"),
                }
            )
        return sorted(runs, key=lambda r: r["modified"], reverse=True)

    @app.get("/api/runs/{name}/events")
    def run_events(name: str) -> list[dict[str, Any]]:
        events, _ = read_events(run_path(name))
        return events

    @app.post("/api/runs/{name}/stop")
    def stop_run(name: str, x_viewer: str | None = Header(default=None)) -> dict[str, str]:
        """Ask a running tournament to stop, by creating its stop file.

        The engine checks for the file before every agent request. The custom
        header means another website open in the browser cannot trigger this.
        """
        if x_viewer != "1":
            raise HTTPException(403, "missing X-Viewer header")
        path = run_path(name)
        events, _ = read_events(path)
        if events and events[-1]["type"] == "tournament_end":
            raise HTTPException(409, "run already finished")
        path.with_suffix(".stop").touch()
        return {"status": "stop requested"}

    @app.get("/api/runs/{name}/stream")
    async def run_stream(name: str) -> StreamingResponse:
        """Server-sent events: every event so far, then new ones as they are written."""
        path = run_path(name)

        async def stream() -> AsyncIterator[str]:
            offset = 0
            while True:
                events, offset = read_events(path, offset)
                for event in events:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event["type"] == "tournament_end":
                        yield "event: end\ndata: {}\n\n"
                        return
                if not events:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(POLL_SECONDS)

        return StreamingResponse(stream(), media_type="text/event-stream")

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Tournament viewer")
    parser.add_argument("--runs", default="runs")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(Path(args.runs)), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
