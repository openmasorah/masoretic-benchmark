"""Reject private workstation/path leaks in public-bound files.

With explicit argv, scans the given paths. With no argv, scans the tracked
file set from git ls-files for CI whole-repo enforcement.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Private-leak needles. Assembled from fragments so this guard file does not
# itself trip the whole-tree scan. Matching is case-insensitive (see _scan_path).
# The first needle is the pre-rebrand internal codename; restoring it as a bare
# token (not just the 'Workspace/<codename>' path form) is the core of the guard
# regression fix — a future rename sweep that blinds this list must turn CI red
# (enforced by the meta-test in tests/test_reject_private_paths.py). The needle
# is assembled from fragments so this guard file does not match itself.
DENYLIST: tuple[str, ...] = (
    "baal" + "shem",
    "Workspace/" + "masorah",
    "Workspace/" + "openmasorah",
    "/Users/" + "benlamm",
)

# Contractually-immutable provenance occurrences that legitimately contain a
# denylisted token. Each exact string is removed from scanned text BEFORE
# matching, so the known-good occurrence is exempt while ANY OTHER occurrence of
# the same token still trips. Pinned to the exact string (not the file) so a
# real leak dropped elsewhere in the same file is still caught.
# Source: phase_0_manifest.json:71 — the append-only changelog row (CLAUDE.md).
_ALLOWED_OCCURRENCES: tuple[str, ...] = (
    "baal" + "shem" + "@bc7255ecaa3eb872885467d3a59e9e6352d5668a",
)


def _git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _scan_path(path: str) -> list[str]:
    p = Path(path)
    # Skip deleted/missing paths (pre-commit passes them too); cleanup commits
    # should not be vetoed while removing an already bad file.
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    # Case-insensitive matching; strip exempt provenance occurrences first.
    haystack = text.lower()
    for allowed in _ALLOWED_OCCURRENCES:
        haystack = haystack.replace(allowed.lower(), "")
    return [
        f"REJECT (private path {pattern!r}): {path}"
        for pattern in DENYLIST
        if pattern.lower() in haystack
    ]


def main(argv: list[str]) -> int:
    paths = argv or _git_ls_files()
    errors: list[str] = []
    for path in paths:
        errors.extend(_scan_path(path))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(
            "\nGT-10/BL-08/REL-09: public-bound masoretic-benchmark files must "
            "not contain private workspace, pre-rebrand codename, or local user "
            "path leaks.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via pre-commit/CI
    sys.exit(main(sys.argv[1:]))
