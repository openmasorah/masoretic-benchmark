"""Reject private workstation/path leaks in public-bound files.

With explicit argv, scans the given paths. With no argv, scans the tracked
file set from git ls-files for CI whole-repo enforcement.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DENYLIST: tuple[str, ...] = (
    "Workspace/" + "openmasorah",
    "/Users/" + "benlamm",
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
    return [f"REJECT (private path {pattern!r}): {path}" for pattern in DENYLIST if pattern in text]


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
            "not contain private openmasorah workspace or local user path leaks.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via pre-commit/CI
    sys.exit(main(sys.argv[1:]))
