import json
from pathlib import Path

from theoremsmith import lean


def _pkg(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "Pkg" / "tut").mkdir(parents=True)
    (root / "Pkg" / "tut" / "a.lean").write_text("theorem weird : True := trivial\n")
    (root / "Pkg" / "tut" / "b.lean").write_text("theorem weird : True := trivial\n")
    (root / "Pkg" / "tut" / "goal.lean").write_text("theorem commutativity : True := trivial\n")
    return root


def test_modules_defining_locates_the_goal_module(tmp_path):
    root = _pkg(tmp_path)
    mods = ["Pkg.tut.a", "Pkg.tut.b", "Pkg.tut.goal"]
    assert lean._modules_defining(root, mods, ["commutativity"]) == {"Pkg.tut.goal"}
    assert lean._modules_defining(root, mods, []) == set()


def test_probe_drops_a_clashing_module_but_never_the_goal(tmp_path, monkeypatch):
    root = _pkg(tmp_path)
    mods = ["Pkg.tut.a", "Pkg.tut.b", "Pkg.tut.goal"]
    calls: list[list[str]] = []

    def fake_stream(argv, cwd, sink, timeout, env=None):
        joined = argv[argv.index("--run") + 2]
        keep = joined.split(",")
        calls.append(keep)
        jsonl = Path(argv[argv.index("--run") + 3])
        if "Pkg.tut.a" in keep and "Pkg.tut.b" in keep:
            sink("import Pkg.tut.b failed, environment already contains 'weird' from Pkg.tut.a")
            return 1
        jsonl.write_text(json.dumps({"record": "decl", "name": "commutativity",
                                     "user": "commutativity", "kind": "theorem"}) + "\n")
        return 0

    monkeypatch.setattr(lean, "stream", fake_stream)
    rows = lean.probe(root, mods, ["commutativity"], lambda _l: None, 60)

    assert [r["name"] for r in rows] == ["commutativity"]
    assert "Pkg.tut.goal" in calls[-1]          # the goal module is never dropped
    assert "Pkg.tut.a" not in calls[-1]         # the clashing one was


def test_import_closure_follows_internal_imports_only(tmp_path):
    root = tmp_path / "r"
    (root / "P").mkdir(parents=True)
    (root / "P" / "goal.lean").write_text("import P.helper\nimport Mathlib.Data\ntheorem g : True := trivial\n")
    (root / "P" / "helper.lean").write_text("import P.deep\n")
    (root / "P" / "deep.lean").write_text("-- leaf\n")
    (root / "P" / "unrelated.lean").write_text("theorem u : True := trivial\n")
    mods = ["P.goal", "P.helper", "P.deep", "P.unrelated"]
    assert lean.import_closure(root, mods, {"P.goal"}) == {"P.goal", "P.helper", "P.deep"}


def test_probe_restricts_to_the_goal_closure(tmp_path, monkeypatch):
    root = tmp_path / "r"
    (root / "P").mkdir(parents=True)
    (root / "P" / "goal.lean").write_text("import P.helper\ntheorem g : True := trivial\n")
    (root / "P" / "helper.lean").write_text("-- leaf\n")
    (root / "P" / "other.lean").write_text("theorem weird : True := trivial\n")
    mods = ["P.goal", "P.helper", "P.other"]
    probed: list[list[str]] = []

    def fake_stream(argv, cwd, sink, timeout, env=None):
        keep = argv[argv.index("--run") + 2].split(",")
        probed.append(keep)
        Path(argv[argv.index("--run") + 3]).write_text(
            json.dumps({"record": "decl", "name": "g", "user": "g", "kind": "theorem"}) + "\n")
        return 0

    monkeypatch.setattr(lean, "stream", fake_stream)
    lean.probe(root, mods, ["g"], lambda _l: None, 60)
    assert probed[0] == ["P.goal", "P.helper"]      # 'P.other' (the clashing one) never imported


def test_probe_gives_up_rather_than_drop_the_only_module(tmp_path, monkeypatch):
    root = _pkg(tmp_path)
    monkeypatch.setattr(lean, "stream",
                        lambda *a, **k: (a[2]("import X failed, environment already contains 'y' from X"), 1)[1])
    try:
        lean.probe(root, ["Pkg.tut.goal"], ["commutativity"], lambda _l: None, 60)
        assert False, "expected LeanError"
    except lean.LeanError as exc:
        assert "probe exited 1" in str(exc)
