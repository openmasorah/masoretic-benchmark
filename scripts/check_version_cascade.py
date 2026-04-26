"""Pre-merge check: pyproject.toml ``[project].version`` bumps must not silently
violate pin consumers in sibling pyproject.toml files in the same repo.

**Target repo:** ``~/Workspace/masoretic-benchmark/`` (the public sibling repo).

Originating incident: Phase 03.1 W0 bumped ``masoretic-eval`` 0.1.0 -> 0.2.0
in the root ``pyproject.toml``. Two pin consumers (``oracles/pyproject.toml``
and ``baselines/pyproject.toml``) pinned ``masoretic-eval>=0.1.0,<0.2``. The
bump silently violated those pins; local tests passed because they don't
install the consumer subprojects. Sibling CI caught it after the fact.

This check is the deterministic pre-merge gate that catches that class of
failure with no human judgment.

Behavior
--------
1. Walk all tracked ``pyproject.toml`` files via ``git ls-files``.
2. Diff against ``--base <ref>`` (PR base SHA in CI; ``HEAD~1`` for push to
   main). Detect which pyproject.toml files had their ``[project].version``
   line changed.
3. For each version-changed package, parse the new version from the working
   tree, then scan all pyproject.toml files for entries in
   ``[project].dependencies`` and ``[project.optional-dependencies].*`` that
   pin that package. The package's own pyproject is excluded (self-pin guard).
4. For each pin consumer, evaluate ``Specifier.contains(new_version)``.
   Mismatches are violations.
5. Exit 0 if no violations; non-zero with stderr listing every violation
   (file, line number, pin string, new version, suggested bumped pin range).

Usage::

    python scripts/check_version_cascade.py --base origin/main
    python scripts/check_version_cascade.py --base HEAD~1
    python scripts/check_version_cascade.py            # defaults to origin/main

The script never modifies the working tree; it only reads.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import InvalidVersion, Version

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionChange:
    """A package whose ``[project].version`` was changed by this PR/push."""

    pyproject_path: str  # repo-relative
    package_name: str
    new_version: str


@dataclass(frozen=True)
class PinViolation:
    """A pin consumer whose specifier rejects a new version."""

    pin_file: str  # repo-relative
    pin_line: int  # 1-indexed
    package_name: str
    pin_specifier: str  # e.g. ">=0.1.0,<0.2"
    new_version: str
    extra: str | None  # which optional-dependencies group, or None for main deps

    def format(self) -> str:
        loc = f"{self.pin_file}:{self.pin_line}"
        scope = f"[{self.extra}]" if self.extra else "[dependencies]"
        suggested = _suggest_pin(self.pin_specifier, self.new_version)
        suggestion = f" -- consider: {self.package_name}{suggested}" if suggested else ""
        return (
            f"{loc} {scope}: {self.package_name}{self.pin_specifier} "
            f"does not allow new version {self.new_version}{suggestion}"
        )


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------


def _run_git(args: list[str], cwd: Path) -> str:
    """Run a git command and return stdout, raising on non-zero exit."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _list_tracked_pyprojects(repo_root: Path) -> list[Path]:
    """Return all tracked ``pyproject.toml`` files (repo-relative paths)."""
    out = _run_git(["ls-files", "*pyproject.toml"], cwd=repo_root)
    return [Path(line) for line in out.splitlines() if line.strip()]


def _file_at_ref(repo_root: Path, ref: str, path: Path) -> str | None:
    """Return file contents at a given ref, or None if the file didn't exist."""
    try:
        return _run_git(["show", f"{ref}:{path.as_posix()}"], cwd=repo_root)
    except subprocess.CalledProcessError:
        return None


# ---------------------------------------------------------------------------
# pyproject parsing
# ---------------------------------------------------------------------------


def _parse_project_table(content: str) -> tuple[str | None, str | None]:
    """Return ``(name, version)`` from ``[project]`` of a pyproject.toml string.

    Returns ``(None, None)`` if the file has no parseable ``[project]`` table
    (e.g. workspace-only pyprojects with no ``[project]``).
    """
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        return None, None
    project = data.get("project")
    if not isinstance(project, dict):
        return None, None
    name = project.get("name")
    version = project.get("version")
    if not isinstance(name, str):
        name = None
    if not isinstance(version, str):
        version = None
    return name, version


def _detect_version_changes(
    repo_root: Path,
    base_ref: str,
    pyprojects: list[Path],
) -> list[VersionChange]:
    """Return packages whose ``[project].version`` differs from ``base_ref``."""
    changes: list[VersionChange] = []
    for rel in pyprojects:
        new_content_path = repo_root / rel
        if not new_content_path.exists():
            # File was deleted in working tree; skip — not a version bump.
            continue
        new_content = new_content_path.read_text(encoding="utf-8")
        new_name, new_version = _parse_project_table(new_content)
        if new_name is None or new_version is None:
            continue
        old_content = _file_at_ref(repo_root, base_ref, rel)
        if old_content is None:
            # New pyproject in this PR — treat as a "bump" from nothing so its
            # initial pins are still validated against the live tree.
            changes.append(
                VersionChange(
                    pyproject_path=rel.as_posix(),
                    package_name=new_name,
                    new_version=new_version,
                )
            )
            continue
        _, old_version = _parse_project_table(old_content)
        if old_version != new_version:
            changes.append(
                VersionChange(
                    pyproject_path=rel.as_posix(),
                    package_name=new_name,
                    new_version=new_version,
                )
            )
    return changes


# ---------------------------------------------------------------------------
# pin scanning
# ---------------------------------------------------------------------------


def _iter_dependency_strings(
    pyproject_data: dict,
) -> list[tuple[str, str | None]]:
    """Yield ``(requirement_string, extra_name_or_None)`` from a project table.

    ``extra_name`` is None for main ``[project].dependencies`` entries, or the
    extras group name for ``[project.optional-dependencies].<group>`` entries.
    """
    items: list[tuple[str, str | None]] = []
    project = pyproject_data.get("project")
    if not isinstance(project, dict):
        return items
    main = project.get("dependencies")
    if isinstance(main, list):
        for entry in main:
            if isinstance(entry, str):
                items.append((entry, None))
    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for extra_name, group in optional.items():
            if not isinstance(group, list):
                continue
            for entry in group:
                if isinstance(entry, str):
                    items.append((entry, extra_name))
    return items


def _find_pin_line(content: str, requirement_string: str) -> int:
    """Best-effort line lookup for a requirement string in a pyproject.

    Falls back to ``0`` if not found. Multiple matches return the first.
    """
    needle = requirement_string.strip()
    for idx, line in enumerate(content.splitlines(), start=1):
        if needle in line:
            return idx
    return 0


def _scan_pin_consumers(
    repo_root: Path,
    pyprojects: list[Path],
    changed: VersionChange,
) -> list[PinViolation]:
    """Return all pin violations of ``changed`` across the repo."""
    violations: list[PinViolation] = []
    try:
        new_version_obj = Version(changed.new_version)
    except InvalidVersion:
        # If the new version is unparseable, that's a separate problem; we
        # cannot evaluate specifier containment, so skip.
        return violations

    for rel in pyprojects:
        # Self-pin guard: a package's own pyproject is never flagged against
        # its own version bump.
        if rel.as_posix() == changed.pyproject_path:
            continue
        full = repo_root / rel
        if not full.exists():
            continue
        content = full.read_text(encoding="utf-8")
        try:
            data = tomllib.loads(content)
        except tomllib.TOMLDecodeError:
            continue
        for req_str, extra in _iter_dependency_strings(data):
            try:
                req = Requirement(req_str)
            except InvalidRequirement:
                continue
            # Canonicalize names (PEP 503): match case-insensitively, treating
            # ``-`` and ``_`` as equivalent.
            if _canonicalize(req.name) != _canonicalize(changed.package_name):
                continue
            spec = req.specifier
            if not spec:
                # Unpinned consumer ("masoretic-eval" with no specifier) is
                # vacuously compatible.
                continue
            if spec.contains(new_version_obj, prereleases=True):
                continue
            line_no = _find_pin_line(content, req_str)
            violations.append(
                PinViolation(
                    pin_file=rel.as_posix(),
                    pin_line=line_no,
                    package_name=changed.package_name,
                    pin_specifier=str(spec),
                    new_version=changed.new_version,
                    extra=extra,
                )
            )
    return violations


def _canonicalize(name: str) -> str:
    """PEP 503 name normalization (lowercase, ``-``/``_``/``.`` -> ``-``)."""
    return name.lower().replace("_", "-").replace(".", "-")


# ---------------------------------------------------------------------------
# Suggestion helper
# ---------------------------------------------------------------------------


def _suggest_pin(old_specifier: str, new_version: str) -> str:
    """Suggest a bumped pin range for the violation message.

    Heuristic: if the old specifier looks like ``>=A,<B``, produce
    ``>={new_version},<{next_major_or_minor}``. Otherwise return empty.
    The suggestion is informational; the human still owns the actual pin.
    """
    try:
        new_v = Version(new_version)
    except InvalidVersion:
        return ""
    # Naive next-minor bump: 0.2.0 -> 0.3, 1.4.2 -> 1.5
    parts = list(new_v.release)
    if len(parts) < 2:
        return ""
    next_minor = f"{parts[0]}.{parts[1] + 1}"
    return f">={new_version},<{next_minor}"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def check_cascade(repo_root: Path, base_ref: str) -> list[PinViolation]:
    """Run the full check and return all violations found (test-friendly API)."""
    pyprojects = _list_tracked_pyprojects(repo_root)
    if not pyprojects:
        return []
    version_changes = _detect_version_changes(repo_root, base_ref, pyprojects)
    if not version_changes:
        return []
    all_violations: list[PinViolation] = []
    for change in version_changes:
        all_violations.extend(_scan_pin_consumers(repo_root, pyprojects, change))
    return all_violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check that pyproject.toml [project].version bumps do not "
            "silently violate pin consumers elsewhere in the repo."
        )
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Base ref to diff against (default: origin/main).",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root (default: cwd).",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    try:
        violations = check_cascade(repo_root, args.base)
    except subprocess.CalledProcessError as exc:
        # Surface git failure with the actual stderr so CI logs are useful.
        stderr = (exc.stderr or "").strip()
        sys.stderr.write(
            f"check_version_cascade: git command failed: {' '.join(exc.cmd)}\n{stderr}\n"
        )
        return 2

    if not violations:
        return 0

    sys.stderr.write(
        "Version cascade check FAILED: "
        f"{len(violations)} pin consumer(s) would be broken by version bumps:\n"
    )
    for v in violations:
        sys.stderr.write(f"  - {v.format()}\n")
    sys.stderr.write(
        "\nFix: bump the pin specifier(s) in the listed file(s) to allow the "
        "new version, in the same PR as the version bump.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
