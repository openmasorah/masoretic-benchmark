from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "reject_private_paths.py"
PRIVATE_PATTERNS = (
    "Workspace/" + "baalshem",
    "/Users/" + "benlamm",
)


@pytest.fixture()
def reject_private_paths():
    spec = importlib.util.spec_from_file_location("reject_private_paths", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_main_accepts_clean_file(tmp_path, reject_private_paths):
    clean = tmp_path / "clean.txt"
    clean.write_text("public benchmark metadata only\n", encoding="utf-8")

    assert reject_private_paths.main([str(clean)]) == 0


def test_main_rejects_private_path_leaks(tmp_path, reject_private_paths, capsys):
    leaking = tmp_path / "leaking.txt"
    leaking.write_text(
        f"do not publish {PRIVATE_PATTERNS[0]} or {PRIVATE_PATTERNS[1]}\n",
        encoding="utf-8",
    )

    assert reject_private_paths.main([str(leaking)]) == 1
    stderr = capsys.readouterr().err
    assert "REJECT" in stderr
    assert str(leaking) in stderr


def test_main_skips_missing_paths(tmp_path, reject_private_paths):
    missing = tmp_path / "deleted.txt"

    assert reject_private_paths.main([str(missing)]) == 0


def test_main_without_args_scans_git_ls_files(tmp_path, reject_private_paths, monkeypatch):
    clean = tmp_path / "clean.txt"
    clean.write_text("clean\n", encoding="utf-8")
    leaking = tmp_path / "leaking.txt"
    leaking.write_text(f"leak: {PRIVATE_PATTERNS[0]}\n", encoding="utf-8")
    missing = tmp_path / "missing.txt"

    monkeypatch.setattr(
        reject_private_paths,
        "_git_ls_files",
        lambda: [str(clean), str(leaking), str(missing)],
    )

    assert reject_private_paths.main([]) == 1
