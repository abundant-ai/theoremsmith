from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

_GENERATED = re.compile(
    r"(^|\.)(_|match_\d|proof_\d|eq_\d|rec|recOn|casesOn|brecOn|below|ibelow|binductionOn|"
    r"noConfusion|noConfusionType|ofNat|toCtorIdx|sizeOf|instDecidableEq|induct|"
    r"eq_def|def_eq|unsafe_rec|elim|inj|injEq|ctorIdx)($|\.)"
)


class CutError(RuntimeError):
    def __init__(self, reason: str, detail: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or {}


def authored(row: dict) -> bool:
    if row.get("internal"):
        return False
    name = row.get("user") or row.get("name") or ""
    if not name or _GENERATED.search(name):
        return False
    if row.get("kind") in {"ctor", "rec", "quot"}:
        return False
    return bool(row.get("file")) and row.get("startLine") is not None


@dataclass
class Graph:
    nodes: dict[str, dict] = field(default_factory=dict)
    stmt: dict[str, set[str]] = field(default_factory=dict)
    body: dict[str, set[str]] = field(default_factory=dict)
    incoming: dict[str, set[str]] = field(default_factory=dict)
    byraw: dict[str, dict] = field(default_factory=dict)


def build_graph(rows: Iterable[dict]) -> Graph:
    g = Graph()
    decls = [r for r in rows if r.get("record") == "decl"]
    for r in decls:
        g.byraw[r.get("name") or ""] = r
    for r in decls:
        if not authored(r):
            continue
        g.nodes[r["user"]] = r
    def canon(raw: str) -> str | None:
        row = g.byraw.get(raw)
        user = (row.get("user") if row else None) or raw
        return user if user in g.nodes else None
    for name, r in g.nodes.items():
        s = {c for d in (r.get("typeDeps") or []) if (c := canon(d)) and c != name}
        b = {c for d in (r.get("valueDeps") or []) if (c := canon(d)) and c != name}
        g.stmt[name] = s
        g.body[name] = b - s
        for d in s | b:
            g.incoming.setdefault(d, set()).add(name)
    return g


def closure(start: Iterable[str], edges: Callable[[str], Iterable[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(start)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(edges(n))
    return seen


@dataclass
class Partition:
    goals: list[str]
    surface: set[str]
    sealed: set[str]
    support: set[str]
    targets: set[str]

    @property
    def cut(self) -> set[str]:
        return self.targets | self.support

    def summary(self) -> dict:
        return {
            "goals": sorted(self.goals),
            "surface": len(self.surface),
            "sealed": len(self.sealed),
            "support": len(self.support),
        }


def partition(g: Graph, goals: list[str]) -> Partition:
    missing = [x for x in goals if x not in g.nodes]
    if missing:
        near = {
            m: sorted(n for n in g.nodes if m.rsplit(".", 1)[-1].lower() in n.lower())[:5]
            for m in missing
        }
        raise CutError("goals absent from the authored graph", {"missing": missing, "nearest": near})
    if not goals:
        raise CutError("no goals selected")

    def both(x: str) -> set[str]:
        return g.stmt.get(x, set()) | g.body.get(x, set())

    surface = closure(goals, both)
    seed: set[str] = set()
    for x in goals:
        seed |= g.stmt.get(x, set())
    targets = set(goals)
    sealed = closure(seed, both) & surface
    while True:
        cand = surface - sealed - targets
        outside = {d for d in cand if g.incoming.get(d, set()) - surface}
        if not outside:
            break
        sealed |= closure(outside, both) & surface
    sealed -= targets
    cut = surface - sealed - targets
    for name in sorted(cut):
        if g.nodes[name].get("kind") != "theorem":
            cut.discard(name)
            sealed.add(name)
    return Partition(list(goals), surface, sealed, cut, targets)


@dataclass(frozen=True)
class Span:
    name: str
    file: str
    start: int
    end: int


def spans(g: Graph, names: Iterable[str], root: Path) -> dict[str, Span]:
    out: dict[str, Span] = {}
    for n in names:
        r = g.nodes.get(n)
        if not r or not r.get("file") or r.get("startLine") is None:
            continue
        try:
            rel = Path(r["file"]).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
        out[n] = Span(n, rel, int(r["startLine"]) - 1, int(r.get("endLine") or r["startLine"]) - 1)
    return out


MARKER = "-- THEOREMSMITH_SLOT"


def find_delimiter(text: str) -> tuple[int, int] | None:
    depth = 0
    i, n = 0, len(text)
    while i < n:
        two = text[i : i + 2]
        if two == "/-":
            level, i = 1, i + 2
            while i < n and level:
                if text[i : i + 2] == "/-":
                    level, i = level + 1, i + 2
                elif text[i : i + 2] == "-/":
                    level, i = level - 1, i + 2
                else:
                    i += 1
            continue
        if two == "--":
            while i < n and text[i] != "\n":
                i += 1
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
        if text[i] == "'":
            m = re.match(r"'(?:\\.|[^'\\\n])'", text[i:])
            if m:
                i += m.end()
                continue
        if text[i] in "([{⟨⦃":
            depth += 1
        elif text[i] in ")]}⟩⦄":
            depth -= 1
        elif depth == 0 and two == ":=":
            return i, i + 2
        i += 1
    return None


def split_declaration(lines: list[str], span: Span) -> tuple[str, str]:
    joined = "\n".join(lines[span.start : span.end + 1])
    found = find_delimiter(joined)
    if found is None:
        raise CutError(f"no proof delimiter in {span.name}", {"file": span.file})
    start, end = found
    return joined[:start].rstrip(), joined[end:].strip()


def apply_cut(root: Path, part: Partition, table: dict[str, Span]) -> dict:
    byfile: dict[str, list[Span]] = {}
    for name in part.cut:
        span = table.get(name)
        if span:
            byfile.setdefault(span.file, []).append(span)
    slots: list[dict] = []
    answers: dict[str, str] = {}
    for rel, group in byfile.items():
        path = root / rel
        lines = path.read_text(encoding="utf-8").splitlines()
        for span in sorted(group, key=lambda s: s.start, reverse=True):
            head, proof = split_declaration(lines, span)
            head_lines = head.splitlines()
            head_lines[-1] += " :="
            marker = f"sorry {MARKER}:{span.name}"
            lines[span.start : span.end + 1] = head_lines + [marker]
            answers[span.name] = proof
            slots.append({
                "name": span.name,
                "file": rel,
                "head": head,
                "head_lines": len(head_lines),
                "marker": marker,
                "answer_file": span.name.replace(".", "_") + ".lean",
                "goal": span.name in part.targets,
            })
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    slots.sort(key=lambda s: (not s["goal"], s["name"]))
    return {"slots": slots, "answers": answers, "files": sorted(byfile)}
