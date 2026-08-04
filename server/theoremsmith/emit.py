from __future__ import annotations

import json
import shutil
from pathlib import Path

RUN_TEST = """#!/usr/bin/env bash
set -uo pipefail
cd /task
python3 tests/apply_answers.py || exit 0
python3 tests/grade.py
"""

REWARD = r'''

def write_reward(value):
    for base in (os.getenv("THEOREMSMITH_LOGS"), "/logs/verifier", str(ROOT / "logs")):
        if not base:
            continue
        try:
            out = Path(base)
            out.mkdir(parents=True, exist_ok=True)
            (out / "reward.txt").write_text(str(value))
            return
        except OSError:
            continue

'''

APPLY = r'''import json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
__REWARD__
SLOTS = json.loads((ROOT / "tests" / "slots.json").read_text())
BANNED = re.compile(r"\b(sorry|sorryAx|admit|axiom|native_decide|implemented_by|"
                    r"skipKernelTC|trustCompiler|debug\.)\w*")


def strip_lean(text):
    out, i, n = [], 0, len(text)
    while i < n:
        two = text[i:i + 2]
        if two == "/-":
            depth, i = 1, i + 2
            while i < n and depth:
                if text[i:i + 2] == "/-":
                    depth, i = depth + 1, i + 2
                elif text[i:i + 2] == "-/":
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            continue
        if two == "--":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text[i] == "'":
            m = re.match(r"'(?:\\.|[^'\\\n])'", text[i:])
            if m:
                i += m.end()
                continue
        if text[i] == '"':
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                elif text[i] == '"':
                    i += 1
                    break
                else:
                    i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def balanced(text):
    depth = 0
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def reject(msg):
    write_reward(0)
    print(f"REJECTED: {msg}")
    print("REWARD=0")
    sys.exit(1)


for slot in SLOTS:
    path = ROOT / "answers" / slot["answer_file"]
    if not path.exists():
        reject(f"missing answer file answers/{slot['answer_file']}")
    answer = path.read_text()
    clean = strip_lean(answer)
    hit = BANNED.search(clean)
    if hit:
        reject(f"answers/{slot['answer_file']} uses a forbidden mechanism: {hit.group(0)}")
    if not balanced(clean):
        reject(f"answers/{slot['answer_file']} has unbalanced delimiters")
    target = ROOT / "environment" / slot["file"]
    lines = target.read_text().splitlines()
    idx = next((i for i, ln in enumerate(lines) if ln.strip() == slot["marker"].strip()), None)
    if idx is None:
        reject(f"slot marker for {slot['name']} is missing from {slot['file']}")
    lines[idx] = slot["head"] + " := (\n" + answer.rstrip() + "\n)"
    target.write_text("\n".join(lines) + "\n")
    print(f"applied {slot['name']}")
'''

GRADE = r'''import json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / "environment"
__REWARD__
SLOTS = json.loads((ROOT / "tests" / "slots.json").read_text())
ALLOWED = {"propext", "Classical.choice", "Quot.sound"}


def finish(value, why=""):
    write_reward(value)
    if why:
        print(why)
    print(f"REWARD={value}")
    sys.exit(0 if value == 1 else 1)


build = subprocess.run(["lake", "build"], cwd=ENV, capture_output=True, text=True)
print(build.stdout[-6000:])
if build.returncode != 0:
    finish(0, build.stderr[-4000:])

audit = subprocess.run(["lake", "env", "lean", "--run", str(ROOT / "tests" / "axioms.lean")],
                       cwd=ENV, capture_output=True, text=True)
print(audit.stdout[-4000:])
if audit.returncode != 0:
    finish(0, audit.stderr[-4000:])

used = {line.strip() for line in audit.stdout.splitlines() if line.strip()}
extra = sorted(used - ALLOWED)
if extra:
    finish(0, f"forbidden axioms reached: {extra}")
finish(1)
'''

AXIOMS = """import Lean
{imports}
open Lean

def targets : List Name := [{names}]

def main : IO Unit := do
  let env <- importModules #[{modules}] {{}} 0
  for t in targets do
    match env.find? t with
    | none => IO.println s!"MISSING {{t}}"
    | some _ =>
      let (_, s) := ((CollectAxioms.collect t).run env).run {{}}
      for a in s.axioms do IO.println a
"""


def _instruction(slug: str, repo: str, slots: list[dict], prose: str) -> str:
    goals = [s for s in slots if s.get("goal")]
    support = [s for s in slots if not s.get("goal")]
    lines = [f"# {slug}", "", prose.strip(), "", "## What to do", ""]
    lines.append("Every proof below has been removed from the source tree and replaced by "
                 "`sorry`. Write a Lean 4 proof for each one. The repository does not build "
                 "until they are all filled in.")
    lines.append("")
    lines.append("Targets:")
    lines.append("")
    for s in goals:
        lines.append(f"- `{s['name']}` in `environment/{s['file']}` "
                     f"-> `answers/{s['answer_file']}`")
    if support:
        lines.append("")
        lines.append("Supporting lemmas these proofs used, also removed:")
        lines.append("")
        for s in support:
            lines.append(f"- `{s['name']}` in `environment/{s['file']}` "
                         f"-> `answers/{s['answer_file']}`")
    lines.append("")
    lines.append("## Rules")
    lines.append("")
    lines.append("- An answer file holds ONE Lean expression. It is spliced in after `:=`, "
                 "so a tactic block starting with `by` and a bare proof term both work.")
    lines.append("- `sorry`, `admit`, `axiom`, `native_decide`, and the kernel-trust options "
                 "are rejected before the build runs.")
    lines.append("- The statements are fixed and are taken from the task, not from your answer, "
                 "so they cannot be weakened.")
    lines.append("- Every target's axiom closure must stay inside `propext`, "
                 "`Classical.choice`, and `Quot.sound`.")
    lines.append("- Build with `lake build` in `environment/`. There is no network.")
    lines.append("")
    lines.append(f"Source: `{repo}`.")
    return "\n".join(lines) + "\n"


def write_task(dest: Path, source: Path, *, slug: str, prose: str, slots: list[dict],
               answers: dict[str, str], modules: list[str], repo: str, sha: str) -> dict:
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "tests").mkdir(parents=True)
    (dest / "answers").mkdir(parents=True)
    (dest / "solution").mkdir(parents=True)
    shutil.copytree(source, dest / "environment", symlinks=True,
                    ignore=shutil.ignore_patterns(".git", ".lake", "build", "*.olean"))
    (dest / "instruction.md").write_text(_instruction(slug, repo, slots, prose), encoding="utf-8")
    (dest / "tests" / "slots.json").write_text(json.dumps(slots, indent=2), encoding="utf-8")
    (dest / "tests" / "apply_answers.py").write_text(
        APPLY.replace("__REWARD__\n", REWARD.lstrip("\n")), encoding="utf-8")
    (dest / "tests" / "grade.py").write_text(
        GRADE.replace("__REWARD__\n", REWARD.lstrip("\n")), encoding="utf-8")
    keep = modules[:64]
    (dest / "tests" / "axioms.lean").write_text(
        AXIOMS.format(
            imports="\n".join(f"import {m}" for m in keep),
            names=", ".join(f"`{s['name']}" for s in slots),
            modules=", ".join("{ module := `%s }" % m for m in keep),
        ), encoding="utf-8")
    runner = dest / "tests" / "run_test.sh"
    runner.write_text(RUN_TEST, encoding="utf-8")
    runner.chmod(0o755)
    for slot in slots:
        (dest / "answers" / slot["answer_file"]).write_text("sorry\n", encoding="utf-8")
        (dest / "solution" / slot["answer_file"]).write_text(
            (answers.get(slot["name"]) or "sorry").strip() + "\n", encoding="utf-8")
    meta = {
        "slug": slug,
        "repo": repo,
        "sha": sha,
        "targets": [s["name"] for s in slots],
        "reward": "binary",
        "network": {"solve": "none", "verify": "none"},
    }
    (dest / "task.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta
