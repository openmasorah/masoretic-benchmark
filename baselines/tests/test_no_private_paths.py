from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_BOUND_PATHS = [
    REPO_ROOT / "baselines",
    REPO_ROOT / "results",
    REPO_ROOT / "masoretic_eval",
    REPO_ROOT / "schemas",
    REPO_ROOT / "scripts",
    REPO_ROOT / "tests",
    REPO_ROOT / ".github",
    REPO_ROOT / ".pre-commit-config.yaml",
]

FORBIDDEN_PATTERNS = (
    "Workspace/" + "openmesorah",
    "/Users/" + "benlamm",
)


def _iter_text_files(root: Path):
    if root.is_file():
        yield root
        return
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", ".pytest_cache", "__pycache__"} for part in path.parts):
            continue
        yield path


def test_public_bound_files_do_not_contain_private_workspace_paths():
    violations: list[str] = []
    for root in PUBLIC_BOUND_PATHS:
        for path in _iter_text_files(root):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in text:
                    violations.append(f"{path.relative_to(REPO_ROOT)} contains {pattern!r}")

    assert violations == []
