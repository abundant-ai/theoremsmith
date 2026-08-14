import json
import subprocess
from pathlib import Path

import pytest

from theoremsmith import oddish
from theoremsmith.config import Config


def _cfg(**over) -> Config:
    return Config(data_dir=Path("/tmp"), base_url="x", api_key="k", create_model="kimi",
                  max_runs=1, build_timeout=1, probe_timeout=1, clone_timeout=1,
                  examples=[], **over)


def _fake_run(monkeypatch, *, returncode=0, stdout="", stderr="", capture=None):
    def run(cmd, **kwargs):
        if "logs" in cmd:  # a resolve_trial probe
            return subprocess.CompletedProcess(cmd, 1, stdout="Trial not found", stderr="")
        if capture is not None:
            capture.extend(cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
    monkeypatch.setattr(oddish.shutil, "which", lambda _b: "/usr/bin/oddish")
    monkeypatch.setattr(oddish.subprocess, "run", run)


def test_submit_returns_the_public_link(monkeypatch):
    _fake_run(monkeypatch, stdout=json.dumps({
        "experiment": "demo",
        "experiment_url": "https://oddish.app/experiments/demo",
        "public_experiment_url": "https://oddish.app/share/tok123",
        "tasks": [{"id": "t_demo", "trials_count": 1}],
    }), stderr="starting daytona\n")
    monkeypatch.setattr(oddish, "resolve_trial", lambda cfg, tid: f"{tid}-0")
    seen = []
    info = oddish.submit(_cfg(), Path("/task"), seen.append)
    assert info["public_url"] == "https://oddish.app/share/tok123"
    assert info["experiment"] == "demo"
    assert info["task_id"] == "t_demo"
    assert info["trial_id"] == "t_demo-0"
    assert info["agent"] == "claude-code"
    assert info["model"] == "fireworks/minimax-m3"
    assert any("starting daytona" in line for line in seen)


def test_extract_json_ignores_surrounding_text():
    raw = ('Submitting task...\nuploading\n'
           '{"public_experiment_url": "u", "tasks": [{"id": "t-0"}]}\n'
           'Running in background.')
    d = oddish._extract_json(raw)
    assert d["public_experiment_url"] == "u"
    assert d["tasks"][0]["id"] == "t-0"


def test_resolve_trial_picks_the_newest(monkeypatch):
    def run(cmd, **kwargs):
        trial = cmd[2]  # ["oddish", "logs", "<trial>"]
        out = "Trial not found" if trial.endswith("-2") else "No live events"
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
    monkeypatch.setattr(oddish.subprocess, "run", run)
    assert oddish.resolve_trial(_cfg(), "task") == "task-1"


def test_clean_line_strips_rich_markup():
    assert oddish.clean_line("[dim]$0.01 · 12 tokens[/dim]") == "$0.01 · 12 tokens"
    assert oddish.clean_line("[bold red]Trial x not found[/bold red]") == "Trial x not found"
    assert oddish.clean_line("plain text   ") == "plain text"


def test_logs_command_follows_the_trial():
    assert oddish.logs_command(_cfg(), "t_demo-0") == ["oddish", "logs", "t_demo-0", "--follow"]


def test_submit_builds_the_expected_command(monkeypatch):
    cmd = []
    _fake_run(monkeypatch, stdout=json.dumps(
        {"public_experiment_url": "https://oddish.app/share/x"}), capture=cmd)
    oddish.submit(_cfg(oddish_env="daytona"), Path("/task"))
    assert cmd[:3] == ["oddish", "run", "/task"]
    for flag in ("-a", "claude-code", "-m", "fireworks/minimax-m3", "--publish", "--background", "--json"):
        assert flag in cmd
    assert cmd[cmd.index("--env") + 1] == "daytona"


def test_missing_cli_is_a_clean_error(monkeypatch):
    monkeypatch.setattr(oddish.shutil, "which", lambda _b: None)
    assert not oddish.available(_cfg())
    with pytest.raises(oddish.OddishError, match="not on the server's PATH"):
        oddish.submit(_cfg(), Path("/task"))


def test_a_nonzero_exit_is_reported(monkeypatch):
    _fake_run(monkeypatch, returncode=1, stderr="boom: bad task")
    with pytest.raises(oddish.OddishError, match="boom"):
        oddish.submit(_cfg(), Path("/task"))


def test_a_run_without_a_public_link_is_an_error(monkeypatch):
    _fake_run(monkeypatch, stdout=json.dumps({"experiment": "demo"}))
    with pytest.raises(oddish.OddishError, match="no public link"):
        oddish.submit(_cfg(), Path("/task"))
