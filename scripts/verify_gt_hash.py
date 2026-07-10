#!/usr/bin/env python3
"""Fuse and verify each frozen folio's `gt_hash` against the artifact it covers.

A digest is worthless if nobody can say what bytes it was taken over. D-28 named
`adjudicated_gt_<folio>.json` as canonical GT and it was never produced, so
`gt_hash` is computed over the per-folio consensus **golden** -- itself a
projection of `iaa_data/devarim_4folio/consensus_gold_positional.json`, the
artifact the released paper pins.

`gt_source` therefore records the exact file the digest covers, and the source it
was projected from. This script parses that path back out and re-hashes it, so
the manifest cannot drift from the bytes it claims to pin.

Digest: **sha256 of the file bytes, truncated to 16 lowercase hex chars.** Same
convention as `manifest_hash`, `kraken_model_hash`, `nakdimon_model_hash`. It is
NOT a full SHA-256, and the manifest must never claim it is -- the paper already
had to retract exactly that overclaim.

Usage
-----
    python scripts/verify_gt_hash.py --check   # exit 1 on drift (CI / pre-commit)
    python scripts/verify_gt_hash.py --fuse    # one-time: perform the W2 fuse

Exit codes
----------
    0  every frozen folio's gt_hash matches its gt_source bytes
    1  drift, or --fuse refused because gt_hash is already set
    2  integrity error (missing artifact, unparseable gt_source)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "phase_0_manifest.json"
GOLDEN_DIR = Path("iaa_data/devarim_4folio/goldens")
SOURCE_PATH = Path("iaa_data/devarim_4folio/consensus_gold_positional.json")

GT_HASH_RE = re.compile(r"^[0-9a-f]{16}$")


class GtHashError(RuntimeError):
    """Integrity problem. Never swallowed, never defaulted."""


def digest(path: Path) -> str:
    """sha256[:16] of the file's bytes. The repo's pin convention."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def golden_for(folio_id: str) -> Path:
    return GOLDEN_DIR / f"{folio_id}.gt_adapter_golden.json"


def covered_path(gt_source: str) -> Path:
    """The file a gt_source string says the digest was taken over.

    Format: '<path>@<rev> (projection of <path>@<rev>)'. We hash the first path;
    the parenthetical records where it came from.
    """
    head = gt_source.split(" ", 1)[0]
    if "@" not in head:
        raise GtHashError(f"gt_source has no '<path>@<rev>' head: {gt_source!r}")
    return Path(head.rsplit("@", 1)[0])


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def check(manifest: dict) -> list[str]:
    errors: list[str] = []
    frozen = [f for f in manifest["folios"] if f.get("in_frozen_scope")]
    if not frozen:
        return ["no folios are in frozen scope"]

    for folio in frozen:
        fid = folio["id"]
        gt_hash, gt_source = folio.get("gt_hash"), folio.get("gt_source")

        if gt_hash is None:
            errors.append(f"{fid}: gt_hash is null (manifest not fused)")
            continue
        if not GT_HASH_RE.fullmatch(gt_hash):
            errors.append(
                f"{fid}: gt_hash={gt_hash!r} is not 16 lowercase hex chars. "
                "The repo convention is sha256[:16] -- a full SHA-256 here would "
                "reintroduce the pin overclaim the paper retracted."
            )
            continue
        if not gt_source:
            errors.append(
                f"{fid}: gt_hash is set but gt_source is missing; "
                "a digest with no stated source is not provenance"
            )
            continue

        try:
            path = REPO_ROOT / covered_path(gt_source)
        except GtHashError as exc:
            errors.append(f"{fid}: {exc}")
            continue

        if not path.exists():
            errors.append(
                f"{fid}: gt_source points at a missing file: {path.relative_to(REPO_ROOT)}"
            )
            continue

        actual = digest(path)
        if actual != gt_hash:
            errors.append(
                f"{fid}: gt_hash={gt_hash} but sha256[:16] of "
                f"{path.relative_to(REPO_ROOT)} is {actual}"
            )
    return errors


def fuse(manifest: dict, new_frozen_at: str, source_rev: str, golden_rev: str) -> dict:
    """One-time W2 fuse. Refuses if any frozen folio already carries a gt_hash."""
    frozen = [f for f in manifest["folios"] if f.get("in_frozen_scope")]
    already = [f["id"] for f in frozen if f.get("gt_hash") is not None]
    if already:
        raise GtHashError(
            f"refusing to re-fuse; gt_hash already set on {already}. "
            "gt_hash is immutable once non-null (scripts/manifest_immutable.py)."
        )

    prev_frozen_at = manifest["frozen_at"]

    for folio in frozen:
        fid = folio["id"]
        golden = REPO_ROOT / golden_for(fid)
        if not golden.exists():
            raise GtHashError(f"{fid}: consensus golden not found at {golden_for(fid)}")
        folio["gt_hash"] = digest(golden)
        folio["gt_source"] = (
            f"{golden_for(fid)}@{golden_rev} (projection of {SOURCE_PATH}@{source_rev})"
        )

    import masoretic_eval  # noqa: PLC0415

    prev_scorer_version = manifest["scorer_version"]
    manifest["scorer_version"] = masoretic_eval.__version__
    manifest["frozen_at"] = new_frozen_at
    manifest["manifest_changelog"].append(
        {
            "prev_frozen_at": prev_frozen_at,
            "new_frozen_at": new_frozen_at,
            "reason": (
                "phase 04: v0.1 gt_hash fuse (Option A). Per-folio gt_hash = sha256[:16] "
                f"of iaa_data/devarim_4folio/goldens/<folio>.gt_adapter_golden.json@{golden_rev}, "
                f"each a projection of consensus_gold_positional.json@{source_rev} (Ginsberg A + "
                "Moster B, adjudicated 2026-06-19). gt_source records the covered file. "
                "D-28's adjudicated_gt_<folio>.json was never produced, hence the projection. "
                f"scorer_version corrected {prev_scorer_version} -> {masoretic_eval.__version__} "
                "(stale since 0a58c1d, 2026-04-26). This field is not inert: "
                "baselines/src/baselines/_base.py cascades it into every emitted run_meta.json, "
                "so the four promoted run_meta.json files recorded scorer_version "
                f"{prev_scorer_version} even though each pins a sibling_git_sha at which "
                f"masoretic_eval.__version__ was already {masoretic_eval.__version__}. "
                "Correcting those emitted records is a separate change; no score depends on "
                "this field."
            ),
        }
    )
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify; exit 1 on drift")
    mode.add_argument("--fuse", action="store_true", help="one-time W2 fuse")
    ap.add_argument("--frozen-at", help="ISO8601 Z timestamp for the fuse")
    ap.add_argument("--source-rev", help="git rev of consensus_gold_positional.json")
    ap.add_argument("--golden-rev", help="git rev of the goldens")
    args = ap.parse_args()

    manifest = load_manifest()

    if args.check:
        errors = check(manifest)
        if errors:
            print(f"gt_hash verification FAILED ({len(errors)}):", file=sys.stderr)
            for err in errors:
                print(f"  {err}", file=sys.stderr)
            return 1
        n = sum(1 for f in manifest["folios"] if f.get("in_frozen_scope"))
        print(f"ok: {n} frozen folios; every gt_hash matches its gt_source bytes")
        return 0

    if not (args.frozen_at and args.source_rev and args.golden_rev):
        print("--fuse requires --frozen-at, --source-rev and --golden-rev", file=sys.stderr)
        return 2
    try:
        fused = fuse(manifest, args.frozen_at, args.source_rev, args.golden_rev)
    except GtHashError as exc:
        print(f"gt-hash-error: {exc}", file=sys.stderr)
        return 1

    MANIFEST_PATH.write_text(
        json.dumps(fused, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"fused {sum(1 for f in fused['folios'] if f.get('in_frozen_scope'))} folios:")
    for folio in fused["folios"]:
        if folio.get("in_frozen_scope"):
            print(f"  {folio['id']:34} {folio['gt_hash']}")
    print(f"\nfrozen_at -> {fused['frozen_at']}   scorer_version -> {fused['scorer_version']}")
    print("\nNEXT: python scripts/rebind_manifest_hash.py  (the 11 promoted artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
