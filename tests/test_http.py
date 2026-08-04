import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("THEOREMSMITH_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("THEOREMSMITH_API_KEY", "test-key")
    monkeypatch.setenv("THEOREMSMITH_MAX_RUNS", "1")
    from theoremsmith import app as module
    module = importlib.reload(module)
    monkeypatch.setattr(module.pool, "submit", lambda *a, **k: None)
    with TestClient(module.app) as c:
        yield c, module


def test_config_reports_the_model_and_whether_a_key_is_set(client):
    c, _ = client
    body = c.get("/api/config").json()
    assert body["configured"] is True
    assert body["max_runs"] == 1
    assert body["model"]


@pytest.mark.parametrize("repo", [
    "https://github.com/owner/name",
    "https://github.com/owner/name.git",
    "owner/name",
])
def test_a_github_repo_is_accepted_in_any_of_its_spellings(client, repo):
    c, _ = client
    assert c.post("/api/runs", json={"repo": repo}).json()["repo"] == "owner/name"


@pytest.mark.parametrize("repo", [
    "file:///etc/passwd",
    "https://169.254.169.254/latest/meta-data",
    "../../etc",
    "https://gitlab.com/owner/name",
    "owner",
    "owner/name/extra",
])
def test_anything_that_is_not_a_github_slug_is_refused(client, repo):
    c, _ = client
    assert c.post("/api/runs", json={"repo": repo}).status_code == 400


def test_the_run_cap_is_enforced(client):
    c, _ = client
    assert c.post("/api/runs", json={"repo": "owner/one"}).status_code == 200
    refused = c.post("/api/runs", json={"repo": "owner/two"})
    assert refused.status_code == 429
    assert "already going" in refused.json()["detail"]


def test_an_unknown_run_is_a_404_everywhere(client):
    c, _ = client
    for path in ("/api/runs/nope", "/api/runs/nope/events", "/api/runs/nope/task"):
        assert c.get(path).status_code == 404
    assert c.delete("/api/runs/nope").status_code == 404


def test_an_unknown_api_path_does_not_fall_through_to_the_page(client):
    c, _ = client
    response = c.get("/api/definitely-not-a-route")
    assert response.status_code == 404
    assert "no such endpoint" in response.json()["detail"]


def test_a_run_can_be_listed_read_and_deleted(client):
    c, _ = client
    created = c.post("/api/runs", json={"repo": "owner/name", "goals": ["Ns.thm"]}).json()
    assert c.get("/api/runs").json()["runs"][0]["id"] == created["id"]
    assert c.get(f"/api/runs/{created['id']}").json()["goals"] == ["Ns.thm"]
    assert c.delete(f"/api/runs/{created['id']}").json()["deleted"] == created["id"]
    assert c.get("/api/runs").json()["runs"] == []


def test_a_run_cannot_be_created_without_a_model_key(tmp_path, monkeypatch):
    monkeypatch.setenv("THEOREMSMITH_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("THEOREMSMITH_API_KEY", "")
    from theoremsmith import app as module
    module = importlib.reload(module)
    with TestClient(module.app) as c:
        assert c.get("/api/config").json()["configured"] is False
        assert c.post("/api/runs", json={"repo": "owner/name"}).status_code == 400


def test_the_event_stream_replays_history_and_ends(client):
    c, module = client
    from theoremsmith import events
    created = c.post("/api/runs", json={"repo": "owner/name"}).json()
    events.emit(created["id"], "log", text="hello")
    events.emit(created["id"], "end")
    with c.stream("GET", f"/api/runs/{created['id']}/events") as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert "hello" in body
    assert '"kind": "end"' in body


def test_a_finished_run_with_no_events_left_still_closes_the_stream(client):
    c, module = client
    created = c.post("/api/runs", json={"repo": "owner/name"}).json()
    run = module.store.read(created["id"])
    run["status"] = "done"
    module.store.write(run)
    with c.stream("GET", f"/api/runs/{created['id']}/events") as response:
        body = "".join(response.iter_text())
    assert '"kind": "end"' in body
