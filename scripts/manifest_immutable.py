"""Pre-commit hook: ``phase_0_manifest.json`` is append-only-immutable (Pattern 4).

**Target repo:** ``~/Workspace/masoretic-benchmark/`` (the public sibling repo).
This file is COPY-READY; openmasorah does not edit the sibling repo directly
(see CLAUDE.md + Pitfall 8 of .planning/phases/01-gt-infra/01-RESEARCH.md).

Allowed mutations:
  - Append a new ``folios[]`` entry (new ``id``).
  - Flip ``in_frozen_scope`` on an existing folio from ``true -> false``
    (a fuse event narrowing scope).
  - Append to ``fuses_fired[]``.
  - Update top-level ``frozen_at`` timestamp (fuse events bump it).
  - Remove a folio entry IFF the staged commit appends exactly one new
    ``manifest_changelog`` row whose ``reason`` matches ``^phase \\d+(\\.\\d+)?: ``
    AND the removed folio in HEAD has ``iaa_folio: false`` AND
    ``gt_hash: null`` (a fuse-event regime change retiring a scaffold folio
    that never carried adjudicated GT).

Rejected mutations:
  - Change any of :data:`IMMUTABLE_FIELDS` on an existing folio entry.
  - Flip ``in_frozen_scope`` ``false -> true`` (a narrowed scope cannot be
    restored; the folio is out forever and only a new entry with a new id
    can re-include work).
  - Remove a previously-committed folio entry, except under the
    fuse-event exemption above (which is narrow on purpose: it never
    permits removing a folio whose GT has been hashed in).

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
import re
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

TOP_LEVEL_TRACKED_FIELDS: tuple[str, ...] = (
    "cost_caps_usd",
    "kraken_model_hash",
    "dictabert_model_revision",
    "scorer_version",
    "nakdimon_model_hash",
    "baselines",
    "baselines_seeded",
    "expected_reports_per_baseline",
    "expected_total_reports",
)

CHANGELOG_REASON_RE = re.compile(r"^phase \d+(\.\d+)?: ")


def _manifest_changelog_rows(doc: dict[str, object]) -> list[object]:
    rows = doc.get("manifest_changelog", [])
    return rows if isinstance(rows, list) else []


def _appended_changelog_rows(
    head: dict[str, object], staged: dict[str, object], errors: list[str]
) -> list[object]:
    head_changelog = _manifest_changelog_rows(head)
    staged_changelog = _manifest_changelog_rows(staged)

    if len(staged_changelog) < len(head_changelog):
        errors.append("REJECT: removed changelog row from manifest_changelog")
        return []

    staged_prefix = staged_changelog[: len(head_changelog)]
    if staged_prefix != head_changelog:
        errors.append("REJECT: edited changelog prefix row; manifest_changelog is append-only")
        return staged_changelog[len(head_changelog) :]

    return staged_changelog[len(head_changelog) :]


def _validate_append_only_rows(
    field: str, head: dict[str, object], staged: dict[str, object], errors: list[str]
) -> None:
    head_rows = head.get(field, [])
    staged_rows = staged.get(field, [])
    if not isinstance(head_rows, list) or not isinstance(staged_rows, list):
        return
    if len(staged_rows) < len(head_rows):
        errors.append(f"REJECT: removed row from {field}; {field} is append-only")
        return
    if staged_rows[: len(head_rows)] != head_rows:
        errors.append(f"REJECT: edited prefix row; {field} is append-only")


def _has_phase_reason(row: object) -> bool:
    if not isinstance(row, dict):
        return False
    reason = row.get("reason")
    if not isinstance(reason, str):
        return False
    return reason.startswith("phase 03.3:") or CHANGELOG_REASON_RE.match(reason) is not None


def _validate_changelog_chain(
    head: dict[str, object], staged: dict[str, object], new_rows: list[object], errors: list[str]
) -> None:
    expected_prev = head.get("frozen_at")
    for index, row in enumerate(new_rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"REJECT: manifest_changelog appended row {index} is not an object")
            continue
        prev_frozen_at = row.get("prev_frozen_at")
        new_frozen_at = row.get("new_frozen_at")
        if prev_frozen_at is not None and prev_frozen_at != expected_prev:
            errors.append(
                "REJECT: manifest_changelog prev_frozen_at chain mismatch "
                f"at appended row {index}: expected {expected_prev!r}, got {prev_frozen_at!r}"
            )
        if new_frozen_at is not None:
            expected_prev = new_frozen_at

    if new_rows and expected_prev != staged.get("frozen_at"):
        errors.append(
            "REJECT: manifest_changelog new_frozen_at chain does not end at "
            f"staged frozen_at {staged.get('frozen_at')!r}"
        )


def validate_manifest_successor(head: dict[str, object], staged: dict[str, object]) -> list[str]:
    """Return rejection messages for illegal manifest mutations."""
    head_ids: dict[str, dict[str, object]] = {f["id"]: f for f in head.get("folios", [])}
    staged_ids: dict[str, dict[str, object]] = {f["id"]: f for f in staged.get("folios", [])}

    errors: list[str] = []
    new_rows = _appended_changelog_rows(head, staged, errors)
    _validate_append_only_rows("fuses_fired", head, staged, errors)
    _validate_changelog_chain(head, staged, new_rows, errors)

    changed_tracked_fields = [
        field for field in TOP_LEVEL_TRACKED_FIELDS if head.get(field) != staged.get(field)
    ]
    if changed_tracked_fields:
        if not new_rows:
            errors.append(
                "REJECT: tracked top-level field change requires an appended "
                "manifest_changelog row: " + ", ".join(changed_tracked_fields)
            )
        elif not any(_has_phase_reason(row) for row in new_rows):
            errors.append(
                "REJECT: tracked top-level field change requires a new "
                "manifest_changelog reason beginning with 'phase 03.3:' or "
                "matching '^phase N(.N)?: '"
            )

    # Detect removals (with narrow fuse-event exemption).
    removed_ids = [fid for fid in head_ids if fid not in staged_ids]
    if removed_ids:
        is_fuse_event = (
            len(new_rows) == 1 and isinstance(new_rows[0], dict) and _has_phase_reason(new_rows[0])
        )
        for fid in removed_ids:
            fhead = head_ids[fid]
            removed_iaa = fhead.get("iaa_folio")
            removed_hash = fhead.get("gt_hash")
            if not is_fuse_event:
                errors.append(
                    f"REJECT: folio {fid!r} was removed without a fuse-event "
                    f"manifest_changelog row; phase_0_manifest.json is "
                    f"append-only-immutable except under fuse-event exemption "
                    f"(reason must match '^phase NN: ')"
                )
            elif removed_iaa is True:
                errors.append(
                    f"REJECT: folio {fid!r} cannot be removed under "
                    f"fuse-event exemption: iaa_folio=true (folio carries "
                    f"or will carry adjudicated GT)"
                )
            elif removed_hash is not None:
                errors.append(
                    f"REJECT: folio {fid!r} cannot be removed under "
                    f"fuse-event exemption: gt_hash is non-null "
                    f"(folio's GT has been hashed in)"
                )

    # Detect field mutations + illegal scope flips on existing entries.
    for fid, fstaged in staged_ids.items():
        fhead = head_ids.get(fid)
        if fhead is None:
            # New folio -- allowed.
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

    return errors


def main(manifest_path: str = "phase_0_manifest.json", base_ref: str = "HEAD") -> int:
    """Return 0 if the staged manifest is a legal successor of HEAD, 1 otherwise."""
    path = Path(manifest_path)
    if not path.exists():
        # Nothing to check (the file was deleted or never existed).
        return 0

    staged = json.loads(path.read_text())
    try:
        head_raw = subprocess.check_output(
            ["git", "show", f"{base_ref}:{manifest_path}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        # First commit of the manifest: nothing to diff against.
        return 0

    head = json.loads(head_raw)
    errors = validate_manifest_successor(head, staged)

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via pre-commit
    arg = sys.argv[1] if len(sys.argv) > 1 else "phase_0_manifest.json"
    base = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
    sys.exit(main(arg, base))
