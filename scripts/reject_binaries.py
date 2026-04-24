"""Pre-commit hook: reject binaries + anything under scans/ + files >5 MB.

**Target repo:** ``~/Workspace/masoretic-benchmark/`` (the public sibling repo).
This file is COPY-READY; it is maintained here in baalshem's
``gt-infra/sibling_hooks/`` but is not installed in baalshem itself.

Defense in depth against the private Cairo Shmuel / El Códice / personal mss
ever leaking into the public repo. Paired with BL-08 (baseline content filter)
and REL-09 (release-time egress audit).

Usage in sibling repo's ``.pre-commit-config.yaml``::

    - repo: local
      hooks:
        - id: reject-binary-extensions
          entry: python scripts/reject_binaries.py
          language: python
          pass_filenames: true
"""

from __future__ import annotations

import sys
from pathlib import Path

REJECTED_EXT: frozenset[str] = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".pdf",
        ".png",
        ".tif",
        ".tiff",
        ".gif",
        ".bmp",
        ".psd",
    }
)
MAX_BYTES: int = 5 * 1024 * 1024  # 5 MB


def main(argv: list[str]) -> int:
    """Return 0 if all staged paths are allowed, 1 otherwise.

    Writes one ``REJECT (...)`` line per violating path to stderr, then a
    trailing GT-10 explanatory note.
    """
    errors: list[str] = []
    for f in argv:
        p = Path(f)
        # Skip deleted/missing paths (pre-commit passes them too); the hook
        # should not veto removal of a previously-committed binary.
        if not p.exists():
            continue
        if p.suffix.lower() in REJECTED_EXT:
            errors.append(f"REJECT (extension {p.suffix}): {f}")
            continue
        parts = p.parts
        if "scans" in parts:
            errors.append(f"REJECT (under scans/): {f}")
            continue
        try:
            sz = p.stat().st_size
        except OSError:
            continue
        if sz > MAX_BYTES:
            errors.append(f"REJECT (size {sz} > {MAX_BYTES} bytes): {f}")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(
            "\nGT-10: sibling public repo (masoretic-benchmark) does not commit "
            "binaries or files under scans/.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via pre-commit
    sys.exit(main(sys.argv[1:]))
