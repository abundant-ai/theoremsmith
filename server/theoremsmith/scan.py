from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import llm
from .config import Config

_NS = re.compile(r"^\s*namespace\s+(\S+)")
_SECTION = re.compile(r"^\s*section\b")
_END = re.compile(r"^\s*end\b\s*(\S*)\s*$")
_DECL = re.compile(
    r"^\s*(?:@\[[^\]]*\]\s*)*"
    r"(?P<mods>(?:(?:private|protected|noncomputable|nonrec|scoped|local|unsafe|partial)\s+)*)"
    r"(?:theorem|lemma)\s+(?P<name>[^\s:({\[⦃⟨]+)"
)
_STRUCTURAL = re.compile(r"^\s*(namespace|section|end|theorem|lemma|def|instance|structure|inductive|class|abbrev|example)\b")
_DOC = re.compile(r"/--(.*?)-/", re.S)


def _mask(text: str) -> str:
    out = list(text)
    i, n = 0, len(text)

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        two = text[i : i + 2]
        if two == "/-":
            depth, j = 1, i + 2
            while j < n and depth:
                if text[j : j + 2] == "/-":
                    depth, j = depth + 1, j + 2
                elif text[j : j + 2] == "-/":
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            blank(i, j)
            i = j
        elif two == "--":
            j = i
            while j < n and text[j] != "\n":
                j += 1
            blank(i, j)
            i = j
        elif text[i] == '"':
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                elif text[j] == '"':
                    j += 1
                    break
                else:
                    j += 1
            blank(i, j)
            i = j
        elif text[i] == "'":
            m = re.match(r"'(?:\\.|[^'\\\n])'", text[i:])
            if m:
                blank(i, i + m.end())
                i += m.end()
            else:
                i += 1
        else:
            i += 1
    return "".join(out)


@dataclass
class Candidate:
    name: str
    file: str
    line: int
    signature: str
    doc: str
    proof_lines: int
    has_sorry: bool = False
    is_private: bool = False


def _docs_by_end_line(text: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for m in _DOC.finditer(text):
        end_line = text.count("\n", 0, m.end()) + 1
        body = " ".join(m.group(1).split())
        if body:
            out[end_line] = body
    return out


def enumerate_file(rel: str, text: str) -> list[Candidate]:
    masked = _mask(text).splitlines()
    raw = text.splitlines()
    docs = _docs_by_end_line(text)
    frames: list[tuple[str, int]] = []
    ns: list[str] = []
    out: list[Candidate] = []

    for idx, line in enumerate(masked):
        m = _NS.match(line)
        if m:
            parts = [p for p in m.group(1).split(".") if p]
            ns += parts
            frames.append(("ns", len(parts)))
            continue
        if _SECTION.match(line):
            frames.append(("sec", 0))
            continue
        if _END.match(line):
            if frames:
                kind, k = frames.pop()
                if kind == "ns" and k:
                    del ns[len(ns) - k :]
            continue
        m = _DECL.match(line)
        if not m:
            continue
        end = idx + 1
        while end < len(masked) and not _STRUCTURAL.match(masked[end]):
            end += 1
        block = "\n".join(raw[idx:end])
        mblock = _mask(block)
        cut = re.search(r":=|\bby\b", mblock)
        sig = block[: cut.start()] if cut else block
        proof = mblock[cut.end() :] if cut else ""
        raw_name = m.group("name")
        name = raw_name[len("_root_.") :] if raw_name.startswith("_root_.") else ".".join([*ns, raw_name])
        out.append(Candidate(
            name=name,
            file=rel,
            line=idx + 1,
            signature=" ".join(sig.split())[:400],
            doc=docs.get(idx, ""),
            proof_lines=sum(1 for ln in raw[idx:end] if ln.strip()),
            has_sorry=bool(re.search(r"\b(sorry|sorryAx|admit)\b", proof)),
            is_private="private" in m.group("mods"),
        ))
    return out


def enumerate_theorems(root: Path) -> list[Candidate]:
    out: list[Candidate] = []
    for path in sorted(root.rglob("*.lean")):
        if ".lake" in path.parts or "test" in path.name.lower():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out += enumerate_file(path.relative_to(root).as_posix(), text)
    return out


def shortlist(cands: list[Candidate], limit: int = 40) -> list[Candidate]:
    seen: set[str] = set()
    keep: list[Candidate] = []
    for c in sorted(cands, key=lambda c: c.proof_lines, reverse=True):
        if c.proof_lines < 2 or c.name in seen or c.has_sorry or c.is_private:
            continue
        seen.add(c.name)
        keep.append(c)
    return keep[:limit]


SCAN_SYSTEM = (
    "You pick benchmark-worthy theorems from a Lean 4 repository and describe each one for a "
    "beginner. You are given candidate theorems with their signatures and any docstring. Choose "
    "the ones that state a real, self-contained result — not plumbing, not typeclass instances, "
    "not one-line restatements. For each, write ONE line saying, in the plainest possible "
    "language, what the theorem claims is true. No analogies, no metaphors, no 'like'. No jargon "
    "unless the statement forces it. A curious beginner should understand it. Reply with JSON only."
)

SCAN_USER = """Repository: {repo}

Candidates (name — proof length — signature — docstring):
{listing}

Choose the {count} best and describe each. Reply with exactly this JSON and nothing else:
{{"options": [{{"name": "Full.Name", "gloss": "one plain sentence of what it proves"}}]}}
"""


@dataclass
class Option:
    name: str
    file: str
    gloss: str


def curate(cfg: Config, repo: str, cands: list[Candidate], count: int,
           on_delta=lambda _p: None) -> list[Option]:
    by_name = {c.name: c for c in cands}
    listing = "\n".join(
        f"{c.name} — {c.proof_lines} lines — {c.signature}" + (f" — {c.doc[:200]}" if c.doc else "")
        for c in cands
    )
    raw = llm.chat(cfg, SCAN_SYSTEM,
                   SCAN_USER.format(repo=repo, listing=listing, count=count),
                   model=cfg.create_model, on_delta=on_delta, max_tokens=2000)
    picked = llm.json_block(raw).get("options") or []
    out: list[Option] = []
    for item in picked:
        name = (item or {}).get("name")
        c = by_name.get(name)
        if c and not any(o.name == name for o in out):
            out.append(Option(name=name, file=c.file, gloss=(item.get("gloss") or "").strip()))
    return out[:count]


def scan_repo(cfg: Config, repo: str, source: Path, count: int = 10,
              on_delta=lambda _p: None) -> list[Option]:
    cands = shortlist(enumerate_theorems(source))
    if not cands:
        return []
    return curate(cfg, repo, cands, count, on_delta)
