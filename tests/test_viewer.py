import json

import pytest
from fastapi.testclient import TestClient

from agents.bots import GenerousBot, LiarBot, RandomBot
from engine.events import EventLog
from games.schedule import DEFAULT_SCHEDULE
from tests.helpers import run
from viewer.server import create_app, read_events


@pytest.fixture
def runs_dir(tmp_path):
    with EventLog(tmp_path / "finished.jsonl") as log:
        run([RandomBot(0), LiarBot(1), GenerousBot(2), RandomBot(3), RandomBot(4)], DEFAULT_SCHEDULE, log=log)
    (tmp_path / "finished_trace.jsonl").write_text("{}\n")
    return tmp_path


@pytest.fixture
def client(runs_dir):
    return TestClient(create_app(runs_dir))


def test_lists_runs_but_not_traces(client):
    runs = client.get("/api/runs").json()
    assert [r["name"] for r in runs] == ["finished.jsonl"]
    assert runs[0]["finished"] and runs[0]["winner"]


def test_serves_events(client, runs_dir):
    events = client.get("/api/runs/finished.jsonl/events").json()
    assert events == [json.loads(line) for line in (runs_dir / "finished.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("name", ["../secret.jsonl", "finished_trace.jsonl", "missing.jsonl", "x.txt"])
def test_rejects_bad_names(client, runs_dir, name):
    (runs_dir.parent / "secret.jsonl").write_text("{}\n")
    assert client.get(f"/api/runs/{name}/events").status_code == 404


def test_stream_sends_all_events_then_ends(client, runs_dir):
    with client.stream("GET", "/api/runs/finished.jsonl/stream") as response:
        body = "".join(response.iter_text())
    data = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: {\"")]
    assert len(data) == len((runs_dir / "finished.jsonl").read_text().splitlines())
    assert "event: end" in body


def test_partial_last_line_is_left_for_later(tmp_path):
    path = tmp_path / "live.jsonl"
    path.write_text('{"seq": 0}\n{"seq": 1, "par')
    events, offset = read_events(path)
    assert events == [{"seq": 0}]
    with path.open("a") as f:
        f.write('tial": true}\n')
    more, _ = read_events(path, offset)
    assert more == [{"seq": 1, "partial": True}]


def test_serves_the_page(client):
    page = client.get("/")
    assert page.status_code == 200 and "Tournament Viewer" in page.text


# ------------------------------------------------------------- stop button


@pytest.fixture
def unfinished(runs_dir):
    path = runs_dir / "live.jsonl"
    lines = (runs_dir / "finished.jsonl").read_text().splitlines()[:50]
    path.write_text("\n".join(lines) + "\n")
    return path


def test_stop_requires_the_viewer_header(client, unfinished):
    assert client.post("/api/runs/live.jsonl/stop").status_code == 403
    assert not unfinished.with_suffix(".stop").exists()


def test_stop_creates_the_stop_file(client, unfinished):
    response = client.post("/api/runs/live.jsonl/stop", headers={"X-Viewer": "1"})
    assert response.status_code == 200
    assert unfinished.with_suffix(".stop").exists()


def test_cannot_stop_a_finished_run(client, runs_dir):
    response = client.post("/api/runs/finished.jsonl/stop", headers={"X-Viewer": "1"})
    assert response.status_code == 409
    assert not (runs_dir / "finished.stop").exists()


@pytest.mark.parametrize("name", ["..%2Fx.jsonl", "x.txt", "finished_trace.jsonl", "missing.jsonl"])
def test_stop_rejects_bad_names(client, runs_dir, name):
    response = client.post(f"/api/runs/{name}/stop", headers={"X-Viewer": "1"})
    assert response.status_code in (404, 405)
    assert not list(runs_dir.rglob("*.stop"))
