from __future__ import annotations

from pathlib import Path

MAX_BYTES = 512 * 1024
MAX_NODES = 3000
SKIP = {".git", ".lake", "node_modules", "__pycache__", "solution", "tests", "verify"}
TASK_ITEMS = {"instruction.md", "environment", "answers", "task.json"}


def _inside(root: Path, path: Path) -> bool:
    root, path = root.resolve(), path.resolve()
    return path == root or root in path.parents


def _roots(run_dir: Path) -> dict[str, Path]:
    roots = {}
    task = run_dir / "task"
    extension = run_dir / "extension"
    if task.is_dir():
        roots["task"] = task
    if extension.is_dir():
        roots["extension"] = extension
    return roots


def _target(run_dir: Path, rel: str) -> Path:
    parts = Path(rel).parts
    roots = _roots(run_dir)
    if not parts or parts[0] not in roots:
        raise ValueError("invalid path")
    root = roots[parts[0]]
    if parts[0] == "task" and len(parts) > 1 and parts[1] not in TASK_ITEMS:
        raise ValueError("private task path")
    target = root
    for part in parts[1:]:
        target /= part
        if target.is_symlink():
            raise ValueError("symlinks are not available")
    target = target.resolve()
    if not _inside(root, target):
        raise ValueError("path escapes run")
    return target


def _node(root: Path, path: Path, budget: list[int]) -> dict:
    rel = path.relative_to(root).as_posix()
    display = root.name if rel == "." else path.name
    if path.is_dir():
        children = []
        for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name in SKIP or child.is_symlink() or budget[0] <= 0:
                continue
            if not _inside(root, child):
                continue
            budget[0] -= 1
            children.append(_node(root, child, budget))
        return {"name": display, "path": rel, "type": "dir", "children": children}
    return {"name": display, "path": rel, "type": "file", "size": path.stat().st_size}


def tree(run_dir: Path) -> dict:
    children = []
    budget = [MAX_NODES]
    for label, root in _roots(run_dir).items():
        if label == "task":
            entries = [root / name for name in sorted(TASK_ITEMS) if (root / name).exists()]
            children.append({"name": label, "path": label, "type": "dir",
                             "children": [_prefix(_node(root, p, budget), label) for p in entries]})
        else:
            children.append(_prefix(_node(root, root, budget), label))
    return {"name": run_dir.name, "path": "", "type": "dir", "children": children}


def _prefix(node: dict, prefix: str) -> dict:
    node["path"] = prefix if node["path"] == "." else f"{prefix}/{node['path']}"
    for child in node.get("children", []):
        _prefix(child, prefix)
    return node


def read(run_dir: Path, rel: str) -> dict:
    target = _target(run_dir, rel)
    if not target.is_file():
        raise FileNotFoundError(rel)
    size = target.stat().st_size
    result = {"name": target.name, "path": rel, "size": size}
    if size > MAX_BYTES:
        return {**result, "kind": "too_large"}
    raw = target.read_bytes()
    if b"\0" in raw:
        return {**result, "kind": "binary"}
    return {**result, "kind": "text", "content": raw.decode("utf-8", errors="replace")}
