import json
from pathlib import Path

from theoremsmith import harbor
from theoremsmith.config import Config


def _task(root: Path) -> Path:
    task = root / "task"
    (task / "environment").mkdir(parents=True)
    (task / "environment" / "lakefile.lean").write_text("package demo\n")
    (task / "environment" / "lean-toolchain").write_text("leanprover/lean4:v4.32.0\n")
    (task / "environment" / "Foo.lean").write_text("theorem bar : True := by\nMARKER\n")
    (task / "environment" / ".lake").mkdir()
    (task / "environment" / ".lake" / "junk").write_text("built artifact")
    (task / "answers").mkdir()
    (task / "answers" / "foo.lean").write_text("sorry\n")
    (task / "tests").mkdir()
    for name in ("run_test.sh", "apply_answers.py", "grade.py"):
        (task / "tests" / name).write_text("# grader\n")
    (task / "tests" / "slots.json").write_text("[]")
    (task / "tests" / "axioms.lean").write_text("import Foo\n")
    (task / "instruction.md").write_text("# demo\n")
    (task / "task.json").write_text(json.dumps(
        {"repo": "owner/name", "sha": "deadbeef", "targets": ["Foo.bar"]}))
    return task


def _cfg(tmp_path: Path) -> Config:
    return Config(data_dir=tmp_path, base_url="x", api_key="k", create_model="kimi",
                  max_runs=1, build_timeout=3600, probe_timeout=1, clone_timeout=1,
                  examples=[], oddish_timeout=1800)


def test_pack_produces_a_harbor_task(tmp_path):
    task = _task(tmp_path)
    dest = harbor.pack(_cfg(tmp_path), task, tmp_path / "out")

    assert (dest / "task.toml").exists()
    assert (dest / "instruction.md").exists()
    assert (dest / "environment" / "Dockerfile").exists()
    assert (dest / "environment" / "repo" / "lakefile.lean").exists()
    assert (dest / "environment" / "answers" / "foo.lean").read_text() == "sorry\n"

    test_sh = dest / "tests" / "test.sh"
    assert test_sh.exists()
    assert test_sh.stat().st_mode & 0o111  # executable
    assert (dest / "tests" / "run_test.sh").exists()


def test_pack_omits_build_artifacts_from_the_context(tmp_path):
    dest = harbor.pack(_cfg(tmp_path), _task(tmp_path), tmp_path / "out")
    assert not (dest / "environment" / "repo" / ".lake").exists()


def test_task_toml_carries_the_thirty_minute_agent_limit_and_network_modes(tmp_path):
    dest = harbor.pack(_cfg(tmp_path), _task(tmp_path), tmp_path / "out")
    toml = (dest / "task.toml").read_text()

    assert "timeout_sec = 1800.0" in toml
    # the agent solves offline; setup and grading get the network
    agent = toml.split("[agent]", 1)[1]
    assert 'network_mode = "no-network"' in agent
    env = toml.split("[environment]", 1)[1]
    assert 'network_mode = "public"' in env
    assert 'source_repo = "owner/name"' in toml


def test_task_toml_justifies_open_internet_for_the_preflight(tmp_path):
    # Oddish's closed_internet preflight rejects a public phase without a written
    # justification of at least 20 characters; the agent phase stays no-network.
    dest = harbor.pack(_cfg(tmp_path), _task(tmp_path), tmp_path / "out")
    toml = (dest / "task.toml").read_text()
    marker = "open_internet_justification = "
    assert marker in toml
    value = toml.split(marker, 1)[1].split("\n", 1)[0].strip().strip('"')
    assert len(value) >= 20


def test_test_sh_reconstructs_the_tree_the_grader_expects(tmp_path):
    dest = harbor.pack(_cfg(tmp_path), _task(tmp_path), tmp_path / "out")
    body = (dest / "tests" / "test.sh").read_text()
    # the pristine environment plus the agent's answers, graded under one root
    assert "/opt/theoremsmith/environment" in body
    assert "/app/answers" in body
    assert "run_test.sh" in body
    assert "/logs/verifier/reward.txt" in body


def test_a_nonce_makes_each_submit_a_distinct_task(tmp_path):
    # Oddish content-addresses the task id, so two submits of the same repo must
    # differ or the second inherits the first's (maybe cancelled) task.
    task = _task(tmp_path)
    a = (harbor.pack(_cfg(tmp_path), task, tmp_path / "a", nonce="run-aaa")
         / "task.toml").read_text()
    b = (harbor.pack(_cfg(tmp_path), task, tmp_path / "b", nonce="run-bbb")
         / "task.toml").read_text()
    assert 'run_nonce = "run-aaa"' in a
    assert 'run_nonce = "run-bbb"' in b
    assert a != b
