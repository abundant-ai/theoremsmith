from pathlib import Path

from theoremsmith import scan
from theoremsmith.config import Config

FIXTURE = """\
import Foo

namespace Alg

/-- Adding zero on the left changes nothing. -/
theorem zero_add (n : Nat) : 0 + n = n := by
  induction n with
  | zero => rfl
  | succ k ih => rw [Nat.add_succ, ih]

namespace Ring

theorem mul_comm (a b : Nat) : a * b = b * a := by
  -- a decoy: theorem not_real : True := trivial
  induction b with
  | zero => simp
  | succ k ih => rw [Nat.mul_succ, ih]

end Ring

lemma one_liner : True := trivial

end Alg

theorem toplevel (p : Prop) : p → p := fun h => h
"""


def test_enumeration_qualifies_names_by_namespace():
    cands = scan.enumerate_file("A/B.lean", FIXTURE)
    names = {c.name for c in cands}
    assert "Alg.zero_add" in names
    assert "Alg.Ring.mul_comm" in names
    assert "Alg.one_liner" in names
    assert "toplevel" in names
    assert "Alg.not_real" not in names
    assert "Alg.Ring.not_real" not in names


def test_enumeration_captures_signature_docstring_and_proof_size():
    cands = {c.name: c for c in scan.enumerate_file("A/B.lean", FIXTURE)}
    z = cands["Alg.zero_add"]
    assert z.doc == "Adding zero on the left changes nothing."
    assert z.signature == "theorem zero_add (n : Nat) : 0 + n = n"
    assert z.proof_lines >= 3
    assert cands["Alg.one_liner"].proof_lines == 1


def test_shortlist_drops_one_liners_and_ranks_by_proof_size():
    short = scan.shortlist(scan.enumerate_file("A/B.lean", FIXTURE))
    names = [c.name for c in short]
    assert "Alg.one_liner" not in names
    assert "toplevel" not in names
    assert names[0] == "Alg.Ring.mul_comm"


def test_curate_returns_named_options_with_glosses(monkeypatch):
    cands = scan.shortlist(scan.enumerate_file("A/B.lean", FIXTURE))

    def fake_chat(cfg, system, user, model=None, on_delta=None, **kw):
        assert model == "kimi"
        assert "no analogies" in system.lower()
        return ('{"options": ['
                '{"name": "Alg.Ring.mul_comm", "gloss": "order does not matter when multiplying"},'
                '{"name": "Alg.zero_add", "gloss": "zero plus a number is that number"},'
                '{"name": "Ghost.absent", "gloss": "should be dropped"}]}')

    monkeypatch.setattr(scan.llm, "chat", fake_chat)
    cfg = Config(data_dir=Path("/tmp"), base_url="x", api_key="k", create_model="kimi",
                 solve_model="glm", max_runs=1, build_timeout=1, probe_timeout=1, clone_timeout=1)
    opts = scan.curate(cfg, "demo/demo", cands, count=10)

    assert [o.name for o in opts] == ["Alg.Ring.mul_comm", "Alg.zero_add"]
    assert opts[0].gloss == "order does not matter when multiplying"
    assert opts[0].file == "A/B.lean"


def test_comment_masking_ignores_a_theorem_inside_a_block_comment():
    text = "namespace N\n/- theorem hidden : True := trivial -/\ntheorem real : True := by trivial\nend N\n"
    names = {c.name for c in scan.enumerate_file("C.lean", text)}
    assert names == {"N.real"}
