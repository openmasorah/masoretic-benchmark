"""Pre-commit hook: ``phase_0_manifest.json`` is append-only-immutable (Pattern 4).

**Target repo:** ``~/Workspace/masoretic-benchmark/`` (the public sibling repo).
This file is COPY-READY; baalshem does not edit the sibling repo directly
(see CLAUDE.md + Pitfall 8 of .planning/phases/01-gt-infra/01-RESEARCH.md).

Allowed mutations:
  - Append a new ``folios[]`` entry (new ``id``).
  - Flip ``in_frozen_scope`` on an existing folio from ``true -> false``
    (a fuse event narrowing scope).
  - Append to ``fuses_fired[]``.
  - Update top-level ``frozen_at`` timestamp (fuse events bump it).

Rejected mutations:
  - Change any of :data:`IMMUTABLE_FIELDS` on an existing folio entry.
  - Flip ``in_frozen_scope`` ``false -> true`` (a narrowed scope cannot be
    restored; the folio is out forever and only a new entry with a new id
    can re-include work).
  - Remove a previously-committed folio entry.

Usage in sibling repo's ``.pre-commit-config.yaml``::

    - repo: local
      hooks:
        - id: manifest-append-only
          entry: python scripts/manifest_immutable.py
          language: python
          files: ^phase_0_manifest\\.json$
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

IMMUTABLE_FIELDS: tuple[str, ...] = (
    "manuscript",
    "book",
    "folio",
    "image_url",
    "iaa_folio",
    "gt_hash",
)


def main(manifest_path: str = "phase_0_manifest.json") -> int:
    """Return 0 if the staged manifest is a legal successor of HEAD, 1 otherwise."""
    path = Path(manifest_path)
    if not path.exists():
        # Nothing to check (the file was deleted or never existed).
        return 0

    staged = json.loads(path.read_text())
    try:
        head_raw = subprocess.check_output(
            ["git", "show", f"HEAD:{manifest_path}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        # First commit of the manifest: nothing to diff against.
        return 0

    head = json.loads(head_raw)
    head_ids: dict[str, dict[str, object]] = {f["id"]: f for f in head.get("folios", [])}
    staged_ids: dict[str, dict[str, object]] = {f["id"]: f for f in staged.get("folios", [])}

    errors: list[str] = []

    # Detect removals.
    for fid in head_ids:
        if fid not in staged_ids:
            errors.append(
                f"REJECT: folio {fid!r} was removed; phase_0_manifest.json is append-only-immutable"
            )

    # Detect field mutations + illegal scope flips on existing entries.
    for fid, fstaged in staged_ids.items():
        fhead = head_ids.get(fid)
        if fhead is None:
            # New folio — allowed.
            continue
        for field in IMMUTABLE_FIELDS:
            prev = fhead.get(field)
            cur = fstaged.get(field)
            if prev is not None and prev != cur:
                errors.append(
                    f"REJECT: folio {fid!r} field {field!r} mutated from {prev!r} to {cur!r}"
                )
        prev_scope = fhead.get("in_frozen_scope")
        cur_scope = fstaged.get("in_frozen_scope")
        if prev_scope is False and cur_scope is True:
            errors.append(
                f"REJECT: folio {fid!r} cannot restore in_frozen_scope "
                "true after a fuse flipped it false"
            )

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via pre-commit
    arg = sys.argv[1] if len(sys.argv) > 1 else "phase_0_manifest.json"
    sys.exit(main(arg))
