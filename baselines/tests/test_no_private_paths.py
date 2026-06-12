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
    "baal" + "shem",
    "Workspace/" + "masorah",
    "Workspace/" + "openmasorah",
    "/Users/" + "benlamm",
)

# Per-(token, repo-relative path) exemptions, mirroring scripts/reject_private_paths.py.
# The recovered release-audit machinery legitimately carries the codename token:
# audit_release.py + its red-team test reference it as detection logic, and the
# planted fixture IS an intentional leak the red-team test must detect. Pinned to
# (token, exact path): any OTHER token in these files still trips, and the token
# in any OTHER file still trips — not a blanket file skip.
_PATH_EXEMPTIONS: dict[str, frozenset[str]] = {
    "baal" + "shem": frozenset(
        {
            "scripts/audit_release.py",
            "tests/release/test_audit_release_red_team.py",
            "tests/release/fixtures/planted_" + "baal" + "shem" + "_string.txt",
        }
    ),
}


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
            rel = path.relative_to(REPO_ROOT).as_posix()
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in text and rel not in _PATH_EXEMPTIONS.get(pattern, frozenset()):
                    violations.append(f"{rel} contains {pattern!r}")

    assert violations == []
