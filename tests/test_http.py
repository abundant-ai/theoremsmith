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
    assert body["create_model"]
    assert body["oddish_agent"] == "claude-code"
    assert body["oddish_model"] == "openrouter/deepseek/deepseek-v4-flash"
    assert body["oddish_agent"] == "claude-code"
    assert body["oddish_timeout"] == 1800
    assert "oddish_available" in body
    assert any(e["repo"] == "stepchowfun/proofs" for e in body["examples"])


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


def test_scan_clones_curates_and_returns_options(client, monkeypatch):
    c, module = client
    monkeypatch.setattr(module.lean, "clone", lambda *a, **k: "deadbeef")
    monkeypatch.setattr(module.scan, "scan_repo",
                        lambda *a, **k: [module.scan.Option("N.thm", "N/A.lean", "it is true")])
    body = c.post("/api/scan", json={"repo": "owner/name"}).json()
    assert body["repo"] == "owner/name"
    assert body["options"] == [{"name": "N.thm", "file": "N/A.lean", "gloss": "it is true"}]


def test_scan_refuses_a_non_github_repo(client):
    c, _ = client
    assert c.post("/api/scan", json={"repo": "file:///etc"}).status_code == 400


def test_scan_surfaces_a_clone_failure_as_422(client, monkeypatch):
    c, module = client

    def boom(*a, **k):
        raise module.lean.LeanError("clone failed: owner/name")

    monkeypatch.setattr(module.lean, "clone", boom)
    r = c.post("/api/scan", json={"repo": "owner/name"})
    assert r.status_code == 422
    assert "clone failed" in r.json()["detail"]


def test_scan_serves_a_cached_result_without_recloning(client, monkeypatch):
    c, module = client
    from theoremsmith import scan

    scan.write_cache(module.cfg, "owner/name", [scan.Option("N.thm", "N/A.lean", "cached gloss")])

    def fail(*a, **k):
        raise AssertionError("should not reclone when a cache exists")

    monkeypatch.setattr(module, "_scan", fail)
    body = c.post("/api/scan", json={"repo": "owner/name"}).json()
    assert body["cached"] is True
    assert body["options"] == [{"name": "N.thm", "file": "N/A.lean", "gloss": "cached gloss"}]


def test_scan_writes_a_cache_for_next_time(client, monkeypatch):
    c, module = client
    from theoremsmith import scan

    monkeypatch.setattr(module, "_scan",
                        lambda repo, sha: [scan.Option("N.thm", "N/A.lean", "fresh")])
    body = c.post("/api/scan", json={"repo": "owner/fresh"}).json()
    assert body["cached"] is False
    assert scan.read_cache(module.cfg, "owner/fresh")[0].gloss == "fresh"


def test_prebuild_starts_warming_the_examples(client, monkeypatch):
    c, module = client
    monkeypatch.setattr(module, "_prewarm_examples", lambda: None)
    body = c.post("/api/scan/prebuild").json()
    assert body["warming"] is True
    assert "stepchowfun/proofs" in body["cached"]


def test_scan_stream_serves_the_cache_instantly(client):
    c, module = client
    from theoremsmith import scan

    scan.write_cache(module.cfg, "owner/name", [scan.Option("N.thm", "N/A.lean", "cached")])
    with c.stream("GET", "/api/scan/stream?repo=owner/name") as r:
        body = "".join(r.iter_text())
    assert '"cached": true' in body
    assert "N.thm" in body


def test_scan_stream_relays_model_deltas_then_options(client, monkeypatch):
    c, module = client
    from theoremsmith import scan

    def fake_scan(repo, sha, on_delta=lambda _p: None):
        on_delta("choosing ")
        on_delta("theorems")
        return [scan.Option("N.thm", "N/A.lean", "gloss")]

    monkeypatch.setattr(module, "_scan", fake_scan)
    with c.stream("GET", "/api/scan/stream?repo=owner/fresh") as r:
        body = "".join(r.iter_text())
    assert "choosing" in body and "theorems" in body
    assert "N.thm" in body
    assert scan.read_cache(module.cfg, "owner/fresh")[0].name == "N.thm"


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


@pytest.mark.parametrize("run_id", [".", "..", "%2e", "a" * 12 + "/..", "ABCDEF123456", "../../etc"])
def test_a_run_id_that_is_not_a_run_id_can_never_reach_the_disk(client, run_id):
    c, module = client
    created = c.post("/api/runs", json={"repo": "owner/name"}).json()
    assert c.delete(f"/api/runs/{run_id}").status_code != 200
    assert module.store.read(created["id"]) is not None
    assert module.store.dir(created["id"]).exists()
    assert module.store.runs_dir.exists()


def test_the_store_refuses_a_run_id_that_is_not_twelve_hex_digits(tmp_path):
    from theoremsmith.store import BadRunId, Store
    store = Store(tmp_path)
    real = store.create("owner/name", "", [], False)
    for bad in (".", "..", "", "../x", "A" * 12, "0" * 11, "0" * 13):
        assert store.read(bad) is None
        assert store.delete(bad) is False
        with pytest.raises(BadRunId):
            store.dir(bad)
    assert store.read(real["id"]) is not None


def test_the_task_of_a_run_that_did_not_finish_is_not_offered(client):
    c, module = client
    created = c.post("/api/runs", json={"repo": "owner/name"}).json()
    run = module.store.read(created["id"])
    run["status"] = "failed"
    module.store.write(run)
    assert c.get(f"/api/runs/{created['id']}/task").status_code == 409


def test_a_run_stranded_by_a_restart_is_marked_failed(client):
    c, module = client
    created = c.post("/api/runs", json={"repo": "owner/name"}).json()
    run = module.store.read(created["id"])
    run["status"] = "running"
    run["stages"]["build"] = "running"
    module.store.write(run)

    assert module.store.fail_orphans() == 1
    recovered = module.store.read(created["id"])
    assert recovered["status"] == "failed"
    assert recovered["stages"]["build"] == "failed"
    assert "restarted" in recovered["error"]
    assert module.store.active() == 0


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


def _finished_run(module, verified=True):
    created = module.store.create("owner/name", "sha", [], False)
    (module.store.dir(created["id"]) / "task").mkdir()
    run = module.store.read(created["id"])
    run["status"] = "done"
    run["result"] = {"targets": ["Foo.bar"], "verified": verified}
    module.store.write(run)
    return created["id"]


def test_submit_returns_immediately_and_stores_the_link_in_the_background(client, monkeypatch):
    c, module = client
    rid = _finished_run(module)
    info = {"public_url": "https://oddish.app/share/tok", "agent": "claude-code", "model": "m"}
    monkeypatch.setattr(module.oddish, "available", lambda _cfg: True)
    monkeypatch.setattr(module.harbor, "pack", lambda cfg, task, dest, nonce="": dest)
    monkeypatch.setattr(module.oddish, "submit", lambda cfg, packed, log: info)
    monkeypatch.setattr(module, "_spawn", lambda target, *a: target(*a))  # run inline

    assert c.post(f"/api/runs/{rid}/submit").json() == {"submitting": True}
    assert module.store.read(rid)["result"]["oddish"]["public_url"] == "https://oddish.app/share/tok"


def test_submit_refuses_a_run_that_did_not_verify(client, monkeypatch):
    c, module = client
    monkeypatch.setattr(module.oddish, "available", lambda _cfg: True)
    rid = _finished_run(module, verified=False)
    assert c.post(f"/api/runs/{rid}/submit").status_code == 409


def test_submit_is_unavailable_without_the_oddish_cli(client, monkeypatch):
    c, module = client
    monkeypatch.setattr(module.oddish, "available", lambda _cfg: False)
    rid = _finished_run(module)
    assert c.post(f"/api/runs/{rid}/submit").status_code == 503


def test_submit_records_an_oddish_failure_on_the_run(client, monkeypatch):
    c, module = client
    rid = _finished_run(module)
    monkeypatch.setattr(module.oddish, "available", lambda _cfg: True)
    monkeypatch.setattr(module.harbor, "pack", lambda cfg, task, dest, nonce="": dest)

    def boom(cfg, packed, log):
        raise module.oddish.OddishError("publishing is disabled")

    monkeypatch.setattr(module.oddish, "submit", boom)
    monkeypatch.setattr(module, "_spawn", lambda target, *a: target(*a))
    assert c.post(f"/api/runs/{rid}/submit").json() == {"submitting": True}
    assert "publishing is disabled" in module.store.read(rid)["result"]["oddish_error"]


def test_submit_404s_for_an_unknown_run(client):
    c, _ = client
    assert c.post("/api/runs/nope/submit").status_code == 404


def test_solve_events_404s_for_an_unknown_run(client):
    c, _ = client
    assert c.get("/api/runs/nope/solve/events").status_code == 404


def test_solve_events_409_before_a_run_is_sent_to_oddish(client):
    c, module = client
    rid = _finished_run(module)  # done + verified, but never submitted
    assert c.get(f"/api/runs/{rid}/solve/events").status_code == 409


def test_solve_events_503_without_the_oddish_cli(client, monkeypatch):
    c, module = client
    rid = _finished_run(module)
    run = module.store.read(rid)
    run["result"]["oddish"] = {"task_id": "t_demo", "agent": "claude-code", "model": "claude-haiku-4-5"}
    module.store.write(run)
    monkeypatch.setattr(module.oddish, "available", lambda _cfg: False)
    assert c.get(f"/api/runs/{rid}/solve/events").status_code == 503
