from theoremsmith import config


def test_examples_default_to_the_three_verified_repos(monkeypatch):
    monkeypatch.delenv("THEOREMSMITH_EXAMPLES", raising=False)
    repos = [e["repo"] for e in config.Config.load().examples]
    assert repos == [
        "stepchowfun/proofs",
        "leanprover-community/batteries",
        "leanprover/TensorLib",
    ]


def test_examples_can_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("THEOREMSMITH_EXAMPLES", "owner/one|a note, owner/two")
    examples = config.Config.load().examples
    assert examples == [
        {"repo": "owner/one", "note": "a note"},
        {"repo": "owner/two", "note": ""},
    ]


def test_a_blank_override_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("THEOREMSMITH_EXAMPLES", "   ")
    assert config.Config.load().examples == config.DEFAULT_EXAMPLES


def test_the_solver_defaults_to_minimax(monkeypatch):
    monkeypatch.delenv("THEOREMSMITH_ODDISH_MODEL", raising=False)
    cfg = config.Config.load()
    assert cfg.oddish_agent == "claude-code"
    assert cfg.oddish_model == "minimax-m3"
