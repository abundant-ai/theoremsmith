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


def test_solvers_default_to_the_named_models(monkeypatch):
    monkeypatch.delenv("THEOREMSMITH_ODDISH_SOLVERS", raising=False)
    models = [s["model"] for s in config.Config.load().oddish_solvers]
    assert models == ["claude-haiku-4-5", "deepseek-v4-flash", "minimax-m3"]
    assert "claude-sonnet-4-6" not in models


def test_solvers_can_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("THEOREMSMITH_ODDISH_SOLVERS",
                       "Fast|deepseek-v4-flash, Big|claude-opus-5|claude-code")
    assert config.Config.load().oddish_solvers == [
        {"label": "Fast", "model": "deepseek-v4-flash", "agent": "claude-code"},
        {"label": "Big", "model": "claude-opus-5", "agent": "claude-code"},
    ]
