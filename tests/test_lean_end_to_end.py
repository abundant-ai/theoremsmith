import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from theoremsmith import dagcut, emit, lean

pytestmark = pytest.mark.skipif(shutil.which("lake") is None,
                                reason="needs a Lean toolchain on PATH")

TOOLCHAIN = os.getenv("THEOREMSMITH_TEST_TOOLCHAIN", "leanprover/lean4:v4.27.0")

PACKAGE = {
    "lean-toolchain": TOOLCHAIN + "\n",
    "lakefile.toml": 'name = "demo"\ndefaultTargets = ["Demo"]\n\n[[lean_lib]]\nname = "Demo"\n',
    "Demo.lean": "import Demo.Basic\n",
    "Demo/Basic.lean": (
        "namespace Demo\n"
        "\n"
        "theorem add_zero_left (n : Nat) : 0 + n = n := by\n"
        "  induction n with\n"
        "  | zero => rfl\n"
        "  | succ k ih => rw [Nat.add_succ, ih]\n"
        "\n"
        "theorem helper_succ (a b : Nat) : a + Nat.succ b = Nat.succ (a + b) := by\n"
        "  rfl\n"
        "\n"
        "theorem add_comm_demo (a b : Nat) : a + b = b + a := by\n"
        "  induction b with\n"
        "  | zero => rw [Nat.add_zero, add_zero_left]\n"
        "  | succ k ih => rw [helper_succ, ih, Nat.succ_add]\n"
        "\n"
        "end Demo\n"
    ),
}


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("demo")
    for name, body in PACKAGE.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    lean.build(root, lambda line: None, 900)
    return root


@pytest.fixture(scope="module")
def task(built, tmp_path_factory) -> Path:
    work = tmp_path_factory.mktemp("cut")
    source = work / "source"
    shutil.copytree(built, source, ignore=shutil.ignore_patterns(".lake"))
    library, modules = lean.package_modules(source)
    assert library == "Demo"
    rows = lean.probe(built, modules, ["Demo.add_comm_demo"], lambda line: None, 600)
    graph = dagcut.build_graph(rows)
    part = dagcut.partition(graph, ["Demo.add_comm_demo"])
    table = dagcut.spans(graph, part.cut, built)
    cut = dagcut.apply_cut(source, part, table)
    out = work / "task"
    emit.write_task(out, source, slug="demo", prose="A tiny Nat package.", slots=cut["slots"],
                    answers=cut["answers"], modules=modules, repo="local/demo", sha="0" * 8)
    return out


def staged(task: Path, dest: Path, *, solve: bool = False) -> Path:
    shutil.copytree(task, dest, symlinks=True)
    if solve:
        for answer in (dest / "solution").iterdir():
            shutil.copy(answer, dest / "answers" / answer.name)
    return dest


def grade(task: Path) -> str:
    env = {**os.environ, "THEOREMSMITH_LOGS": str(task / "logs")}
    apply = subprocess.run(["python3", str(task / "tests" / "apply_answers.py")],
                           cwd=task, capture_output=True, text=True, env=env)
    if apply.returncode != 0:
        return apply.stdout + apply.stderr
    graded = subprocess.run(["python3", str(task / "tests" / "grade.py")],
                            cwd=task, capture_output=True, text=True, env=env, timeout=1800)
    return graded.stdout + graded.stderr


def test_the_probe_finds_the_real_proof_dependencies(built):
    library, modules = lean.package_modules(built)
    rows = lean.probe(built, modules, ["Demo.add_comm_demo"], lambda line: None, 600)
    graph = dagcut.build_graph(rows)
    assert set(graph.nodes) == {"Demo.add_comm_demo", "Demo.add_zero_left", "Demo.helper_succ"}
    assert graph.body["Demo.add_comm_demo"] == {"Demo.add_zero_left", "Demo.helper_succ"}
    assert any(r.get("record") == "goal" and r["name"] == "Demo.add_comm_demo" for r in rows)


def test_the_cut_blanks_the_goal_and_everything_its_proof_needed(task):
    slots = json.loads((task / "tests" / "slots.json").read_text())
    assert [s["name"] for s in slots] == [
        "Demo.add_comm_demo", "Demo.add_zero_left", "Demo.helper_succ"]
    body = (task / "environment" / "Demo" / "Basic.lean").read_text()
    assert body.count(dagcut.MARKER) == 3
    assert "induction" not in body


def test_the_original_proofs_grade_to_one(task, tmp_path):
    out = grade(staged(task, tmp_path / "oracle", solve=True))
    assert "REWARD=1" in out, out[-3000:]


def test_a_smuggled_axiom_grades_to_zero(task, tmp_path):
    attack = staged(task, tmp_path / "attack", solve=True)
    (attack / "environment" / "Demo" / "Cheat.lean").write_text(
        "namespace Demo\naxiom cheat (P : Prop) : P\nend Demo\n", encoding="utf-8")
    basic = attack / "environment" / "Demo" / "Basic.lean"
    basic.write_text("import Demo.Cheat\n" + basic.read_text(), encoding="utf-8")
    slot = next(s for s in json.loads((attack / "tests" / "slots.json").read_text())
                if s["name"] == "Demo.add_comm_demo")
    (attack / "answers" / slot["answer_file"]).write_text("Demo.cheat _\n", encoding="utf-8")
    out = grade(attack)
    assert "REWARD=0" in out, out[-3000:]
    assert "Demo.cheat" in out


def test_a_sorry_answer_is_rejected_before_the_build(task, tmp_path):
    out = grade(staged(task, tmp_path / "sorry"))
    assert "forbidden mechanism" in out
    assert "REWARD=0" in out


def slot_of(task: Path, name: str) -> dict:
    return next(s for s in json.loads((task / "tests" / "slots.json").read_text())
                if s["name"] == name)


def test_weakening_the_statement_is_rejected(task, tmp_path):
    attack = staged(task, tmp_path / "weaken", solve=True)
    slot = slot_of(attack, "Demo.add_comm_demo")
    target = attack / "environment" / slot["file"]
    lines = target.read_text().splitlines()
    idx = lines.index(slot["marker"])
    lines[idx - 1] = "theorem add_comm_demo (a b : Nat) : True :="
    target.write_text("\n".join(lines) + "\n")
    (attack / "answers" / slot["answer_file"]).write_text("trivial\n")
    out = grade(attack)
    assert "was modified" in out
    assert "REWARD=0" in out


def test_removing_the_marker_is_rejected(task, tmp_path):
    attack = staged(task, tmp_path / "nomarker", solve=True)
    slot = slot_of(attack, "Demo.add_comm_demo")
    target = attack / "environment" / slot["file"]
    target.write_text(target.read_text().replace(slot["marker"], "Nat.add_comm a b"))
    out = grade(attack)
    assert "marker" in out and "missing" in out
    assert "REWARD=0" in out


@pytest.mark.parametrize("payload, token", [
    ("by native_decide\n", "native_decide"),
    ("set_option debug.skipKernelTC true in by trivial\n", "debug."),
    ("by exact (sorryAx _)\n", "sorry"),
    ("by exact @id _ (by admit)\n", "admit"),
])
def test_forbidden_mechanisms_are_rejected(task, tmp_path, payload, token):
    attack = staged(task, tmp_path / f"ban-{token.strip('.')}", solve=True)
    slot = slot_of(attack, "Demo.add_comm_demo")
    (attack / "answers" / slot["answer_file"]).write_text(payload)
    out = grade(attack)
    assert "forbidden mechanism" in out, out[-1500:]
    assert "REWARD=0" in out


def test_a_banned_word_inside_a_comment_or_string_is_not_a_false_positive(task, tmp_path):
    attack = staged(task, tmp_path / "innocent", solve=True)
    slot = slot_of(attack, "Demo.add_comm_demo")
    original = (attack / "solution" / slot["answer_file"]).read_text()
    (attack / "answers" / slot["answer_file"]).write_text(
        "-- this proof does not use sorry\n"
        '/- neither axiom nor native_decide appear here: "sorry" -/\n' + original)
    out = grade(attack)
    assert "REWARD=1" in out, out[-2000:]
