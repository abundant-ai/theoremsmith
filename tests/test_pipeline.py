import json
from pathlib import Path

import pytest

from theoremsmith import emit, events, lean, llm, pipeline
from theoremsmith.config import Config
from theoremsmith.store import Store

REAL_VERIFY = pipeline._verify

SOURCE = {
    "lakefile.lean": 'import Lake\nopen Lake DSL\npackage demo\nlean_lib Demo\n',
    "Demo.lean": "import Demo.Basic\n",
    "Demo/Basic.lean": (
        "theorem helper : True := by trivial\n"
        "theorem goal : True := by\n"
        "  exact helper\n"
    ),
}


def decl(user, kind="theorem", type_deps=(), value_deps=(), file="", start=1, end=1):
    return {"record": "decl", "name": user, "user": user, "kind": kind, "internal": False,
            "typeDeps": list(type_deps), "valueDeps": list(value_deps),
            "file": file, "startLine": start, "endLine": end, "module": "Demo.Basic"}


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(data_dir=tmp_path / "data", base_url="http://stub", api_key="k",
                  create_model="stub", max_runs=1,
                  build_timeout=10, probe_timeout=10, clone_timeout=10, examples=[])


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    def fake_clone(url, sha, dest, sink, timeout):
        for name, body in SOURCE.items():
            path = dest / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        sink(f"cloned {url}")
        return "abc123def456"

    def fake_build(root, sink, timeout):
        sink("lake build ok")

    def fake_probe(root, modules, goals, sink, timeout):
        basic = str(root / "Demo" / "Basic.lean")
        rows = [
            decl("goal", value_deps=["helper"], file=basic, start=2, end=3),
            decl("helper", file=basic, start=1, end=1),
        ]
        if goals:
            rows.append({"record": "goal", "name": "goal", "statement": "True"})
        sink(f"probe emitted {len(rows)} rows")
        return rows

    def fake_chat(config, system, user, on_delta, **kw):
        body = '{"targets": ["goal"], "why": "it has a helper"}' if "Candidate" in user \
            else "A tiny demo package with one theorem."
        for ch in body:
            on_delta(ch)
        return body

    def fake_stream(argv, cwd, sink, timeout, env=None):
        sink(" ".join(argv[:2]))
        return 0

    monkeypatch.setattr(lean, "clone", fake_clone)
    monkeypatch.setattr(lean, "build", fake_build)
    monkeypatch.setattr(lean, "probe", fake_probe)
    monkeypatch.setattr(lean, "stream", fake_stream)
    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(pipeline, "_verify",
                        lambda cfg, task, warm, sink: (True, "stubbed"))


def test_full_run_emits_a_verified_task(cfg, fakes):
    store = Store(cfg.data_dir)
    run = store.create("demo/demo", "", [], False)
    pipeline.execute(cfg, store, run["id"])

    final = store.read(run["id"])
    assert final["status"] == "done", final["error"]
    assert final["sha"] == "abc123def456"
    assert final["goals"] == ["goal"]
    assert all(state == "done" for state in final["stages"].values())
    assert final["result"]["verified"] is True

    task = store.dir(run["id"]) / "task"
    for name in ("instruction.md", "task.json", "tests/slots.json", "tests/grade.py",
                 "tests/apply_answers.py", "tests/run_test.sh", "tests/axioms.lean"):
        assert (task / name).exists(), name

    slots = json.loads((task / "tests" / "slots.json").read_text())
    assert [s["name"] for s in slots] == ["goal", "helper"]
    assert (task / "solution" / slots[0]["answer_file"]).read_text().strip() == "by\n  exact helper"

    cut = (task / "environment" / "Demo" / "Basic.lean").read_text()
    assert cut.count("THEOREMSMITH_SLOT") == 2
    assert "theorem helper" in cut
    assert "trivial" not in cut

    instruction = (task / "instruction.md").read_text()
    assert "goal" in instruction
    assert "tiny demo package" in instruction


def test_verification_never_leaves_the_answer_in_the_shipped_task(cfg, fakes, monkeypatch):
    store = Store(cfg.data_dir)
    run = store.create("demo/demo", "", [], False)
    pipeline.execute(cfg, store, run["id"])
    work = store.dir(run["id"])
    task = work / "task"

    class Ran:
        returncode = 0
        stdout = "applied goal\nREWARD=1\n"
        stderr = ""

    monkeypatch.setattr(pipeline.subprocess, "run", lambda *a, **k: Ran())
    ok, _ = REAL_VERIFY(cfg, task, work / "source", lambda line: None)
    assert ok

    cut = (task / "environment" / "Demo" / "Basic.lean").read_text()
    assert cut.count("THEOREMSMITH_SLOT") == 2
    assert "exact helper" not in cut
    slots = json.loads((task / "tests" / "slots.json").read_text())
    assert (task / "answers" / slots[0]["answer_file"]).read_text().strip() == "sorry"
    assert not (work / "verify").exists()


def test_a_model_that_cannot_write_the_description_does_not_fail_the_run(cfg, fakes, monkeypatch):
    def flaky(config, system, user, on_delta, **kw):
        if "Candidate" in user:
            body = '{"targets": ["goal"], "why": "it has a helper"}'
            for ch in body:
                on_delta(ch)
            return body
        raise llm.LlmError("stub is offline")

    monkeypatch.setattr(llm, "chat", flaky)
    store = Store(cfg.data_dir)
    run = store.create("demo/demo", "", [], False)
    pipeline.execute(cfg, store, run["id"])

    final = store.read(run["id"])
    assert final["status"] == "done", final["error"]
    instruction = (store.dir(run["id"]) / "task" / "instruction.md").read_text()
    assert "Proof targets taken from demo/demo" in instruction
    assert any("description unavailable" in (e.get("text") or "")
               for e in events.history(run["id"]))


def test_a_run_with_goals_given_up_front_never_asks_the_model_to_choose(cfg, fakes, monkeypatch):
    asked: list[str] = []
    real = llm.chat
    monkeypatch.setattr(llm, "chat", lambda c, s, u, d, **k: (asked.append(u), real(c, s, u, d, **k))[1])
    store = Store(cfg.data_dir)
    run = store.create("demo/demo", "", ["goal"], False)
    pipeline.execute(cfg, store, run["id"])

    assert store.read(run["id"])["status"] == "done"
    assert not any("Candidate" in u for u in asked)


def test_events_carry_model_deltas_and_stages(cfg, fakes):
    store = Store(cfg.data_dir)
    run = store.create("demo/demo", "", [], False)
    pipeline.execute(cfg, store, run["id"])

    log = events.history(run["id"])
    kinds = {e["kind"] for e in log}
    assert {"stage", "status", "model", "delta", "log", "end"} <= kinds
    text = "".join(e["text"] for e in log if e["kind"] == "delta" and e.get("phase") == "select")
    assert '"targets"' in text
    assert [e["seq"] for e in log] == sorted(e["seq"] for e in log)


def test_a_failing_stage_marks_the_run_failed(cfg, fakes, monkeypatch):
    monkeypatch.setattr(lean, "build", lambda *a, **k: (_ for _ in ()).throw(lean.LeanError("boom")))
    store = Store(cfg.data_dir)
    run = store.create("demo/demo", "", [], False)
    pipeline.execute(cfg, store, run["id"])

    final = store.read(run["id"])
    assert final["status"] == "failed"
    assert "boom" in final["error"]
    assert final["stages"]["build"] == "failed"
    assert final["stages"]["clone"] == "done"
    assert events.history(run["id"])[-1]["kind"] == "end"


def test_grader_rejects_a_sorry_answer(cfg, fakes, tmp_path):
    import subprocess
    store = Store(cfg.data_dir)
    run = store.create("demo/demo", "", [], False)
    pipeline.execute(cfg, store, run["id"])
    task = store.dir(run["id"]) / "task"
    slots = json.loads((task / "tests" / "slots.json").read_text())
    (task / "answers" / slots[0]["answer_file"]).write_text("sorry\n")
    proc = subprocess.run(["python3", str(task / "tests" / "apply_answers.py")],
                          capture_output=True, text=True)
    assert proc.returncode != 0
    assert "forbidden mechanism" in proc.stdout


def test_grader_rejects_an_unbalanced_answer(cfg, fakes):
    import subprocess
    store = Store(cfg.data_dir)
    run = store.create("demo/demo", "", [], False)
    pipeline.execute(cfg, store, run["id"])
    task = store.dir(run["id"]) / "task"
    slots = json.loads((task / "tests" / "slots.json").read_text())
    (task / "answers" / slots[0]["answer_file"]).write_text("by trivial\n'\"'\n)\naxiom cheat : False\n")
    proc = subprocess.run(["python3", str(task / "tests" / "apply_answers.py")],
                          capture_output=True, text=True)
    assert proc.returncode != 0
    assert "REWARD=0" in proc.stdout
