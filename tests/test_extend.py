import json
from pathlib import Path

import pytest

from theoremsmith import extend
from theoremsmith.config import Config


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(data_dir=tmp_path, base_url="http://stub", api_key="k", create_model="stub",
                  max_runs=1, build_timeout=10, probe_timeout=10, clone_timeout=10, examples=[])


def setup_run(tmp_path: Path):
    run_dir = tmp_path / "run"
    (run_dir / "source").mkdir(parents=True)
    (run_dir / "task" / "tests").mkdir(parents=True)
    (run_dir / "task" / "tests" / "slots.json").write_text(json.dumps([{
        "name": "Demo.target", "file": "Demo/Basic.lean",
    }]))
    run = {"id": "abcdef123456", "result": {
        "targets": ["Demo.target"], "statements": {"Demo.target": "theorem target : True"},
    }}
    return run, run_dir


def test_generate_saves_a_verified_two_theorem_chain(cfg, tmp_path, monkeypatch):
    run, run_dir = setup_run(tmp_path)
    code = """```lean
import Demo.Basic
theorem theoremsmith_extension_abcdef12_step1 : True := by
  exact Demo.target
theorem theoremsmith_extension_abcdef12_step2 : True := by
  exact theoremsmith_extension_abcdef12_step1
```"""
    monkeypatch.setattr(extend.llm, "chat", lambda *a, **k: code)
    monkeypatch.setattr(extend, "_compile", lambda *a, **k: (True, "ok"))

    meta = extend.generate(cfg, run, run_dir)

    assert meta["status"] == "done"
    assert meta["depends_on"] == "Demo.target"
    assert len(meta["theorems"]) == 2
    assert (run_dir / "extension" / "TheoremSmithExtension.lean").exists()


def test_generate_repairs_one_compile_failure(cfg, tmp_path, monkeypatch):
    run, run_dir = setup_run(tmp_path)
    code = """```lean
import Demo.Basic
theorem theoremsmith_extension_abcdef12_step1 : True := by exact Demo.target
theorem theoremsmith_extension_abcdef12_step2 : True := by
  exact theoremsmith_extension_abcdef12_step1
```"""
    calls = []
    monkeypatch.setattr(extend.llm, "chat", lambda *a, **k: (calls.append(a[2]), code)[1])
    outcomes = iter([(False, "type mismatch"), (True, "ok")])
    monkeypatch.setattr(extend, "_compile", lambda *a, **k: next(outcomes))

    assert extend.generate(cfg, run, run_dir)["status"] == "done"
    assert len(calls) == 2 and "type mismatch" in calls[1]


def test_generate_rejects_a_chain_that_does_not_use_the_target(cfg, tmp_path, monkeypatch):
    run, run_dir = setup_run(tmp_path)
    code = """```lean
import Demo.Basic
theorem theoremsmith_extension_abcdef12_step1 : True := by trivial
theorem theoremsmith_extension_abcdef12_step2 : True := by
  exact theoremsmith_extension_abcdef12_step1
```"""
    monkeypatch.setattr(extend.llm, "chat", lambda *a, **k: code)
    with pytest.raises(extend.ExtensionError, match="original target"):
        extend.generate(cfg, run, run_dir)


def test_validation_ignores_dependencies_in_comments_and_rejects_extra_imports():
    names = ("new_step1", "new_step2")
    commented = """import Demo.Basic
theorem new_step1 : True := by
  -- Demo.target
  trivial
theorem new_step2 : True := by exact new_step1
"""
    with pytest.raises(extend.ExtensionError, match="original target"):
        extend._validate(commented, names, ["Demo.target"], ["Demo.Basic"])

    extra_import = commented.replace("import Demo.Basic", "import Demo.Basic Secret.Module")
    with pytest.raises(extend.ExtensionError, match="added an import"):
        extend._validate(extra_import, names, ["Demo.target"], ["Demo.Basic"])
