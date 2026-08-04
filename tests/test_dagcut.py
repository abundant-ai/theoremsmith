from pathlib import Path

import pytest

from theoremsmith import dagcut


def decl(user, kind="theorem", type_deps=(), value_deps=(), file="A/B.lean", start=1, end=3):
    return {
        "record": "decl", "name": user, "user": user, "kind": kind, "internal": False,
        "typeDeps": list(type_deps), "valueDeps": list(value_deps),
        "file": file, "startLine": start, "endLine": end, "module": "A.B",
    }


def test_generated_names_are_not_authored():
    assert not dagcut.authored(decl("Foo.bar.match_1"))
    assert not dagcut.authored(decl("Foo.rec", kind="rec"))
    assert not dagcut.authored({**decl("Foo.bar"), "internal": True})
    assert dagcut.authored(decl("Foo.bar"))


def test_body_edges_exclude_statement_edges():
    g = dagcut.build_graph([decl("A", type_deps=["S"], value_deps=["S", "H"]), decl("S"), decl("H")])
    assert g.stmt["A"] == {"S"}
    assert g.body["A"] == {"H"}


def test_partition_cuts_helpers_used_only_by_the_goal():
    rows = [
        decl("Goal", type_deps=["Stmt"], value_deps=["Helper"]),
        decl("Stmt", kind="def"),
        decl("Helper", value_deps=["Deep"]),
        decl("Deep"),
    ]
    part = dagcut.partition(dagcut.build_graph(rows), ["Goal"])
    assert part.targets == {"Goal"}
    assert "Stmt" in part.sealed
    assert {"Helper", "Deep"} <= part.support


def test_a_helper_used_from_outside_the_surface_is_sealed_not_deleted():
    rows = [
        decl("Goal", value_deps=["Helper"]),
        decl("Helper"),
        decl("Other", value_deps=["Helper"]),
    ]
    part = dagcut.partition(dagcut.build_graph(rows), ["Goal"])
    assert "Helper" in part.sealed
    assert not part.support


def test_a_multi_line_signature_keeps_a_single_line_marker(tmp_path: Path):
    src = tmp_path / "A"
    src.mkdir()
    (src / "B.lean").write_text(
        "theorem wide (a : Nat)\n"
        "    (h : a = a) :\n"
        "    a = a := by\n"
        "  exact h\n",
        encoding="utf-8")
    rows = [decl("wide", file=str(src / "B.lean"), start=1, end=4)]
    graph = dagcut.build_graph(rows)
    part = dagcut.partition(graph, ["wide"])
    cut = dagcut.apply_cut(tmp_path, part, dagcut.spans(graph, part.cut, tmp_path))

    slot = cut["slots"][0]
    assert "\n" not in slot["marker"]
    assert slot["head_lines"] == 3
    lines = (src / "B.lean").read_text().splitlines()
    idx = lines.index(slot["marker"])
    stated = "\n".join(lines[idx - slot["head_lines"]:idx]).rstrip()
    assert stated.endswith(":=")
    assert stated[:-2].rstrip() == slot["head"]


def test_missing_goal_reports_near_matches():
    g = dagcut.build_graph([decl("Ns.real_theorem")])
    with pytest.raises(dagcut.CutError) as exc:
        dagcut.partition(g, ["Ns.real_theorm"])
    assert exc.value.detail["missing"] == ["Ns.real_theorm"]


def test_split_declaration_finds_the_delimiter():
    lines = ["theorem foo : 1 = 1 := by", "  rfl"]
    span = dagcut.Span("foo", "A.lean", 0, 1)
    head, proof = dagcut.split_declaration(lines, span)
    assert head == "theorem foo : 1 = 1"
    assert "rfl" in proof


@pytest.mark.parametrize("source, head", [
    ("theorem t [Std.TransCmp (α := α) cmp] : P := by simp",
     "theorem t [Std.TransCmp (α := α) cmp] : P"),
    ("theorem t (h : Q := by trivial) : P := h",
     "theorem t (h : Q := by trivial) : P"),
    ("theorem byte_count : P := rfl", "theorem byte_count : P"),
    ("theorem t : P :=\n  fun x => x", "theorem t : P"),
    ("theorem t /- := decoy -/ : P := rfl", "theorem t /- := decoy -/ : P"),
    ('theorem t : name = ":=" := rfl', 'theorem t : name = ":="'),
    ("theorem t : P := by\n  exact ⟨fun h := h, rfl⟩", "theorem t : P"),
])
def test_split_declaration_ignores_a_nested_or_quoted_delimiter(source, head):
    lines = source.splitlines()
    span = dagcut.Span("t", "A.lean", 0, len(lines) - 1)
    assert dagcut.split_declaration(lines, span)[0] == head


def test_apply_cut_blanks_the_target_and_its_support(tmp_path: Path):
    src = tmp_path / "A"
    src.mkdir()
    (src / "B.lean").write_text(
        "theorem helper : True := by trivial\n"
        "theorem goal : True := by\n"
        "  exact helper\n",
        encoding="utf-8")
    rows = [
        decl("goal", value_deps=["helper"], file=str(src / "B.lean"), start=2, end=3),
        decl("helper", file=str(src / "B.lean"), start=1, end=1),
    ]
    graph = dagcut.build_graph(rows)
    part = dagcut.partition(graph, ["goal"])
    table = dagcut.spans(graph, part.cut, tmp_path)
    cut = dagcut.apply_cut(tmp_path, part, table)

    text = (src / "B.lean").read_text()
    assert text.count(dagcut.MARKER) == 2
    assert "by trivial" not in text
    assert "theorem helper : True :=" in text
    assert all(s["head_lines"] == 1 for s in cut["slots"])
    assert [s["name"] for s in cut["slots"]] == ["goal", "helper"]
    assert cut["slots"][0]["goal"] is True
    assert cut["slots"][1]["goal"] is False
    assert "exact helper" in cut["answers"]["goal"]
    assert "trivial" in cut["answers"]["helper"]
