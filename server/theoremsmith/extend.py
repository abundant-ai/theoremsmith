from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from . import lean, llm
from .config import Config


class ExtensionError(RuntimeError):
    pass


SYSTEM = """You extend an existing Lean 4 development with a tiny verified theorem chain.
Return only one complete Lean file in a ```lean block. Do not explain it."""

USER = """The repository already proves these targets:

{statements}

Write a complete Lean file with exactly these two new global theorem names:

- `{first}`: a useful consequence of one target above. Its proof must explicitly invoke that
  target by its full name.
- `{second}`: a further consequence whose proof explicitly invokes `{first}`.

Use only these imports:
{imports}

The whole file must compile. Do not use `sorry`, `admit`, `axiom`, `opaque`, `unsafe`,
`native_decide`, `run_tac`, `set_option`, or trusted-code attributes. Do not restate an existing
target under a new name. Return only the complete file in one ```lean block."""

REPAIR = """This generated Lean file did not compile.

```lean
{code}
```

Lean reported:
```
{error}
```

Fix it without changing the required theorem names or dependency chain. Keep the same imports and
the same forbidden-mechanism rules. Return only the complete file in one ```lean block."""

BANNED = re.compile(
    r"\b(sorry|admit|axiom|opaque|unsafe|native_decide|run_tac|set_option|implemented_by)\b"
)
IMPORT = re.compile(r"^\s*import\s+(.+)$", re.M)


def _code(raw: str) -> str:
    parts = raw.split("```")
    for part in parts[1::2]:
        body = part.strip()
        if body.lower().startswith("lean"):
            body = body.split("\n", 1)[1] if "\n" in body else ""
        if "theorem" in body:
            return body.strip() + "\n"
    raise ExtensionError("the model did not return a Lean code block")


def _visible(code: str) -> str:
    out = list(code)
    i = depth = 0
    string = False
    while i < len(code):
        if depth:
            if code.startswith("/-", i):
                depth += 1
                out[i:i + 2] = "  "
                i += 2
            elif code.startswith("-/", i):
                depth -= 1
                out[i:i + 2] = "  "
                i += 2
            else:
                if code[i] != "\n":
                    out[i] = " "
                i += 1
        elif string:
            if code[i] == '"' and (i == 0 or code[i - 1] != "\\"):
                string = False
            if code[i] != "\n":
                out[i] = " "
            i += 1
        elif code.startswith("--", i):
            end = code.find("\n", i)
            end = len(code) if end < 0 else end
            out[i:end] = " " * (end - i)
            i = end
        elif code.startswith("/-", i):
            depth = 1
            out[i:i + 2] = "  "
            i += 2
        elif code[i] == '"':
            string = True
            out[i] = " "
            i += 1
        else:
            i += 1
    return "".join(out)


def _proof(code: str, name: str, end: int | None = None) -> str:
    start = re.search(rf"\btheorem\s+{re.escape(name)}\b", code)
    if not start:
        return ""
    declaration = code[start.end():end]
    marker = declaration.find(":=")
    return declaration[marker + 2:] if marker >= 0 else ""


def _validate(code: str, names: tuple[str, str], targets: list[str], imports: list[str]) -> str:
    visible = _visible(code)
    hit = BANNED.search(visible)
    if hit:
        raise ExtensionError(f"the generated file used forbidden `{hit.group(1)}`")
    imported = {module for line in IMPORT.findall(visible) for module in line.split()}
    if imported - set(imports):
        raise ExtensionError("the generated file added an import")
    first, second = names
    for name in names:
        if len(re.findall(rf"\btheorem\s+{re.escape(name)}\b", visible)) != 1:
            raise ExtensionError(f"the generated file must declare `{name}` exactly once")
    second_start = re.search(rf"\btheorem\s+{re.escape(second)}\b", visible).start()
    first_proof = _proof(visible, first, second_start)
    second_proof = _proof(visible, second)
    dependency = next((target for target in targets if target in first_proof), "")
    if not dependency:
        raise ExtensionError("the first theorem did not name an original target")
    if first not in second_proof:
        raise ExtensionError("the second theorem did not build on the first")
    return dependency


def _compile(root: Path, code_path: Path, names: tuple[str, str], timeout: int) -> tuple[bool, str]:
    audit = code_path.with_name("CheckExtension.lean")
    audit.write_text(code_path.read_text() + "\n" +
                     "\n".join(f"#print axioms {name}" for name in names) + "\n")
    try:
        proc = subprocess.run(
            ["lake", "env", "lean", str(audit)], cwd=root, env=lean.lake_env(root),
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Lean exceeded {timeout}s"
    finally:
        audit.unlink(missing_ok=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, output
    used = set()
    for body in re.findall(r"depends on axioms:\s*\[(.*?)\]", output):
        used |= {name.strip() for name in body.split(",") if name.strip()}
    extra = used - {"propext", "Classical.choice", "Quot.sound"}
    if extra:
        return False, f"forbidden axioms reached: {sorted(extra)}"
    return True, output


def generate(cfg: Config, run: dict, run_dir: Path, sink=lambda _line: None) -> dict:
    result = run.get("result") or {}
    targets = result.get("targets") or []
    if not targets:
        raise ExtensionError("this task has no target theorem")
    task = run_dir / "task"
    slots_path = task / "tests" / "slots.json"
    source = run_dir / "source"
    if not slots_path.exists() or not source.is_dir():
        raise ExtensionError("the finished task is missing its Lean workspace")

    slots = json.loads(slots_path.read_text())
    imports = sorted({".".join(Path(slot["file"]).with_suffix("").parts)
                      for slot in slots if slot["name"] in targets})
    suffix = run["id"][:8]
    names = (f"theoremsmith_extension_{suffix}_step1",
             f"theoremsmith_extension_{suffix}_step2")
    statements = "\n\n".join(
        f"{name}:\n{(result.get('statements') or {}).get(name, '(statement unavailable)')}"
        for name in targets
    )
    prompt = USER.format(statements=statements, first=names[0], second=names[1],
                         imports="\n".join(f"import {module}" for module in imports))
    extension = run_dir / "extension"
    if extension.exists():
        shutil.rmtree(extension)
    extension.mkdir()
    code_path = extension / "TheoremSmithExtension.lean"
    error = ""
    for attempt in range(2):
        sink("asking the model for a synthetic extension" if attempt == 0 else
             "repairing the extension after Lean rejected it")
        raw = llm.chat(cfg, SYSTEM, prompt if attempt == 0 else REPAIR.format(
            code=code_path.read_text(), error=error[-3000:]), lambda _piece: None, max_tokens=5000)
        code = _code(raw)
        dependency = _validate(code, names, targets, imports)
        code_path.write_text(code)
        ok, error = _compile(source, code_path, names, min(cfg.build_timeout, 600))
        if ok:
            meta = {
                "status": "done",
                "file": "extension/TheoremSmithExtension.lean",
                "theorems": list(names),
                "depends_on": dependency,
                "summary": (f"Added 2 verified Lean theorems. The first uses `{dependency}`; "
                            f"the second builds on the first."),
            }
            (extension / "extension.json").write_text(json.dumps(meta, indent=2))
            return meta
        sink(error[-2000:])
    code_path.unlink(missing_ok=True)
    raise ExtensionError("the synthetic extension did not compile after one repair")
