"""Tests for ``scripts/check_version_cascade.py``.

Hermetic: each test builds a tiny git repo under ``tmp_path`` with hand-rolled
pyproject.toml files. The check script is imported as a module and invoked
against that repo via the ``check_cascade`` API. We never depend on the actual
sibling repo's content.

The seven cases below mirror the spec in the originating PR:

1. No version changed -> no violations.
2. Version bumped, no pin consumers -> no violations.
3. Version bumped, all pin consumers compatible -> no violations.
4. Version bumped, one pin consumer violated -> violation surfaced.
5. Multi-package repo: bumping A doesn't trigger checks on B.
6. Self-pin handling: package's own pyproject isn't flagged.
7. Optional-dependencies pins are checked, not just main ``dependencies``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

# Load the script as a module without requiring it to be on sys.path or
# packaged. ``scripts/`` is intentionally not a package in this repo.
SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_version_cascade.py"
_spec = importlib.util.spec_from_file_location("check_version_cascade", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None, "could not load check_version_cascade"
cvc = importlib.util.module_from_spec(_spec)
sys.modules["check_version_cascade"] = cvc
_spec.loader.exec_module(cvc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    """Run a git command in ``repo`` and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _init_repo(repo: Path) -> None:
    """Initialize a git repo with deterministic identity (no global config leak)."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")


def _write(repo: Path, rel: str, content: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").strip()


def _pyproject(
    name: str,
    version: str,
    deps: list[str] | None = None,
    extras: dict[str, list[str]] | None = None,
) -> str:
    """Render a minimal pyproject.toml string."""
    lines = [
        "[build-system]",
        'requires = ["setuptools>=68"]',
        'build-backend = "setuptools.build_meta"',
        "",
        "[project]",
        f'name = "{name}"',
        f'version = "{version}"',
    ]
    if deps:
        lines.append("dependencies = [")
        for d in deps:
            lines.append(f'    "{d}",')
        lines.append("]")
    if extras:
        lines.append("[project.optional-dependencies]")
        for group, items in extras.items():
            lines.append(f"{group} = [")
            for d in items:
                lines.append(f'    "{d}",')
            lines.append("]")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_version_change_no_violations(tmp_path: Path) -> None:
    """Case 1: nothing changed -> no violations."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, "pyproject.toml", _pyproject("pkg-a", "0.1.0"))
    _write(
        repo,
        "consumer/pyproject.toml",
        _pyproject("pkg-consumer", "0.1.0", deps=["pkg-a>=0.1.0,<0.2"]),
    )
    base = _commit(repo, "initial")
    # No second commit; diffing HEAD against itself yields no version change.
    violations = cvc.check_cascade(repo, base)
    assert violations == []


def test_version_bumped_no_consumers_no_violations(tmp_path: Path) -> None:
    """Case 2: version bump but nobody pins this package -> no violations."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, "pyproject.toml", _pyproject("pkg-a", "0.1.0"))
    _write(repo, "other/pyproject.toml", _pyproject("pkg-other", "0.1.0"))
    base = _commit(repo, "initial")

    _write(repo, "pyproject.toml", _pyproject("pkg-a", "0.2.0"))
    _commit(repo, "bump pkg-a")

    violations = cvc.check_cascade(repo, base)
    assert violations == []


def test_version_bumped_consumer_compatible(tmp_path: Path) -> None:
    """Case 3: bump within the consumer's allowed range -> no violations."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, "pyproject.toml", _pyproject("pkg-a", "0.1.0"))
    _write(
        repo,
        "consumer/pyproject.toml",
        _pyproject("pkg-consumer", "0.1.0", deps=["pkg-a>=0.1.0,<1.0"]),
    )
    base = _commit(repo, "initial")

    _write(repo, "pyproject.toml", _pyproject("pkg-a", "0.2.0"))
    _commit(repo, "bump pkg-a within range")

    violations = cvc.check_cascade(repo, base)
    assert violations == []


def test_version_bumped_consumer_violated(tmp_path: Path) -> None:
    """Case 4: bump past the consumer's upper bound -> violation surfaced.

    Mirrors the originating Phase 03.1 W0 incident: ``masoretic-eval`` 0.1.0
    -> 0.2.0 against pin ``>=0.1.0,<0.2``.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, "pyproject.toml", _pyproject("pkg-a", "0.1.0"))
    _write(
        repo,
        "consumer/pyproject.toml",
        _pyproject("pkg-consumer", "0.1.0", deps=["pkg-a>=0.1.0,<0.2"]),
    )
    base = _commit(repo, "initial")

    _write(repo, "pyproject.toml", _pyproject("pkg-a", "0.2.0"))
    _commit(repo, "bump pkg-a past consumer ceiling")

    violations = cvc.check_cascade(repo, base)
    assert len(violations) == 1
    v = violations[0]
    assert v.pin_file == "consumer/pyproject.toml"
    assert v.package_name == "pkg-a"
    assert v.new_version == "0.2.0"
    assert v.extra is None
    assert v.pin_line > 0
    msg = v.format()
    assert "pkg-a" in msg
    assert "0.2.0" in msg
    assert "consumer/pyproject.toml" in msg
    assert "consider:" in msg  # suggestion appears


def test_multi_package_isolation(tmp_path: Path) -> None:
    """Case 5: bumping A shouldn't trigger checks on independent B's pins."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, "pyproject.toml", _pyproject("pkg-a", "0.1.0"))
    _write(repo, "pkg-b/pyproject.toml", _pyproject("pkg-b", "0.1.0"))
    # Consumer pins B (NOT A) with a tight ceiling. Bumping A must not flag.
    _write(
        repo,
        "consumer/pyproject.toml",
        _pyproject(
            "pkg-consumer",
            "0.1.0",
            deps=["pkg-b>=0.1.0,<0.2", "pkg-a>=0.1.0,<1.0"],
        ),
    )
    base = _commit(repo, "initial")

    _write(repo, "pyproject.toml", _pyproject("pkg-a", "0.2.0"))
    _commit(repo, "bump pkg-a only")

    violations = cvc.check_cascade(repo, base)
    # A is in range (<1.0), B was not bumped -> no violations.
    assert violations == []


def test_self_pin_not_flagged(tmp_path: Path) -> None:
    """Case 6: a package's own pyproject is excluded from its own bump check.

    Defensive: if the bumped package somehow lists itself as a dependency
    (rare but legal in some self-bootstrapping setups), we don't flag it.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(
        repo,
        "pyproject.toml",
        _pyproject(
            "pkg-a",
            "0.1.0",
            # Self-reference with a tight ceiling — would be a violation if
            # the self-pin guard were missing.
            deps=["pkg-a>=0.1.0,<0.2"],
        ),
    )
    base = _commit(repo, "initial")

    _write(
        repo,
        "pyproject.toml",
        _pyproject("pkg-a", "0.2.0", deps=["pkg-a>=0.1.0,<0.2"]),
    )
    _commit(repo, "bump pkg-a; self-pin still tight on purpose")

    violations = cvc.check_cascade(repo, base)
    assert violations == []


def test_optional_dependencies_pins_checked(tmp_path: Path) -> None:
    """Case 7: pins inside ``[project.optional-dependencies].<group>`` are caught."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo, "pyproject.toml", _pyproject("pkg-a", "0.1.0"))
    _write(
        repo,
        "consumer/pyproject.toml",
        _pyproject(
            "pkg-consumer",
            "0.1.0",
            deps=[],  # main deps clean
            extras={"all": ["pkg-a>=0.1.0,<0.2"]},  # but the extra pins tightly
        ),
    )
    base = _commit(repo, "initial")

    _write(repo, "pyproject.toml", _pyproject("pkg-a", "0.2.0"))
    _commit(repo, "bump pkg-a, breaking extras pin")

    violations = cvc.check_cascade(repo, base)
    assert len(violations) == 1
    v = violations[0]
    assert v.extra == "all"
    assert "[all]" in v.format()
