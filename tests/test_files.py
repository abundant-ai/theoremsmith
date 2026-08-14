from pathlib import Path

import pytest

from theoremsmith import files


def test_tree_only_exposes_solver_visible_task_files(tmp_path: Path):
    task = tmp_path / "task"
    (task / "environment").mkdir(parents=True)
    (task / "solution").mkdir()
    (task / "tests").mkdir()
    (task / "environment" / "Main.lean").write_text("theorem x : True := by trivial\n")
    (task / "instruction.md").write_text("prove x")
    (task / "solution" / "x.lean").write_text("by trivial")
    (task / "tests" / "secret.json").write_text("{}")

    tree = files.tree(tmp_path)
    text = str(tree)
    assert "Main.lean" in text and "instruction.md" in text
    assert "solution" not in text and "secret.json" not in text
    assert files.read(tmp_path, "task/environment/Main.lean")["kind"] == "text"


def test_read_rejects_private_and_escaping_paths(tmp_path: Path):
    task = tmp_path / "task"
    (task / "solution").mkdir(parents=True)
    (task / "solution" / "proof.lean").write_text("secret")
    with pytest.raises(ValueError):
        files.read(tmp_path, "task/solution/proof.lean")
    with pytest.raises(ValueError):
        files.read(tmp_path, "../outside")


def test_read_rejects_a_symlink_that_leaves_the_task(tmp_path: Path):
    task = tmp_path / "task" / "environment"
    task.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (task / "leak").symlink_to(outside)
    with pytest.raises(ValueError):
        files.read(tmp_path, "task/environment/leak")


def test_read_rejects_a_symlink_into_the_hidden_solution(tmp_path: Path):
    environment = tmp_path / "task" / "environment"
    solution = tmp_path / "task" / "solution"
    environment.mkdir(parents=True)
    solution.mkdir()
    (solution / "proof.lean").write_text("secret")
    (environment / "leak.lean").symlink_to(solution / "proof.lean")

    assert "leak.lean" not in str(files.tree(tmp_path))
    with pytest.raises(ValueError):
        files.read(tmp_path, "task/environment/leak.lean")
