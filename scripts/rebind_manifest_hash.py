#!/usr/bin/env python3
"""Rebind promoted result artifacts to the current phase_0_manifest.json hash.

`manifest_hash` is *derived* from the canonical manifest bytes
(`masoretic_eval.manifest._canonical_manifest_hash`), not stored inside it. Any
manifest edit -- a `gt_hash` fuse, a `frozen_at` bump, a new tracked field --
re-fingerprints the manifest and strands every promoted artifact that carries
the old value.

Two consumers enforce the binding:

* ``tests/test_manifest_hash_artifacts.py`` -- strict, checks all 11 artifacts.
* ``scripts/audit_release.py::check_results_manifest_hash`` -- REL-09 gate.

Both go red on the fuse commit itself, so a fuse is only landable as an atomic
(manifest + rebind) change. This happened once already: manifest fuse
``fdc5879`` forced consumer-rewire ``daf2c86`` ("bind 11 F118B result artifacts
to manifest 062a2a6c8646e831"), which was done by hand. This script exists so
the second fuse is a command, not an archaeology exercise.

**Scope.** Only the ``manifest_hash`` field is rewritten. Predictions, scores,
and every other field are byte-untouched. If a manifest change alters what the
numbers *mean* (e.g. the 2026-06-11 maqaf-convention fuse), the affected
artifacts must be genuinely re-emitted from a real re-run *first* -- see
``4e6768a`` -- and only then rebound. **Rebinding is a provenance update, not a
substitute for recomputation.**

Usage
-----
    python scripts/rebind_manifest_hash.py --check   # dry-run; exit 1 on drift
    python scripts/rebind_manifest_hash.py           # rewrite in place

``--check`` is wired into pre-commit and CI so a stale binding cannot land.

Exit codes
----------
    0  all artifacts bound to the current manifest hash (or rewritten)
    1  drift detected in --check mode
    2  usage / integrity error (e.g. an artifact has no manifest_hash field)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from masoretic_eval.manifest import Manifest  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "phase_0_manifest.json"
RESULTS_DIR = REPO_ROOT / "results"
MANIFEST_HASH_RE = re.compile(r"^[0-9a-f]{16}$")

# Matches exactly the top-level, 2-space-indented emission the writers produce:
#   "manifest_hash": "062a2a6c8646e831",
_FIELD_RE = re.compile(r'^(?P<pre>\s*"manifest_hash"\s*:\s*")(?P<val>[^"]*)(?P<post>".*)$')


class RebindError(RuntimeError):
    """Integrity problem that must not be silently tolerated."""


def _rel(path: Path) -> str:
    """Repo-relative display path; falls back to the absolute path.

    `Path.relative_to` raises for anything outside REPO_ROOT, which would turn
    an error *message* into a crash. Error paths must not have error paths.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def discover_artifacts() -> list[Path]:
    """Every JSON under results/ carrying a top-level manifest_hash.

    Deliberately discovery-based rather than a hardcoded list: the strict test
    pins the *expected set*, so if this walk and that list ever diverge, the
    test fails loudly rather than this script silently skipping a file.

    Note the rglob: audit_release.py historically used ``glob("*/*.json")``,
    which is one level deep and misses ``results/<baseline>/diagnostic/*.json``.
    """
    if not RESULTS_DIR.exists():
        return []
    found: list[Path] = []
    for path in sorted(RESULTS_DIR.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RebindError(f"{_rel(path)} is not valid JSON: {exc}") from exc
        if isinstance(payload, dict) and "manifest_hash" in payload:
            found.append(path)
    return found


def current_manifest_hash() -> str:
    digest = Manifest.load(MANIFEST_PATH).manifest_hash
    if not MANIFEST_HASH_RE.fullmatch(digest or ""):
        raise RebindError(f"manifest hash is not 16 lowercase hex chars: {digest!r}")
    return digest


def rewrite(path: Path, expected: str) -> bool:
    """Rewrite the manifest_hash line only. Returns True if the file changed.

    Line-level substitution rather than a json round-trip: a round-trip would
    reformat the whole file and bury the one-field change in noise. The
    precedent commit (daf2c86) shows exactly 1 insertion + 1 deletion per file,
    and that is the diff a reviewer should see.
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if _FIELD_RE.match(line)]

    if not hits:
        raise RebindError(f"{_rel(path)}: no manifest_hash line found")
    if len(hits) > 1:
        raise RebindError(
            f"{_rel(path)}: {len(hits)} manifest_hash lines; expected exactly 1 (is it nested?)"
        )

    idx = hits[0]
    m = _FIELD_RE.match(lines[idx])
    assert m is not None
    if m.group("val") == expected:
        return False
    lines[idx] = (
        f"{m.group('pre')}{expected}{m.group('post')}\n"
        if lines[idx].endswith("\n")
        else f"{m.group('pre')}{expected}{m.group('post')}"
    )
    path.write_text("".join(lines), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="report drift and exit 1; write nothing (for pre-commit / CI)",
    )
    args = ap.parse_args()

    try:
        expected = current_manifest_hash()
        artifacts = discover_artifacts()
    except RebindError as exc:
        print(f"rebind-error: {exc}", file=sys.stderr)
        return 2

    if not artifacts:
        print("no promoted artifacts carry manifest_hash; nothing to do")
        return 0

    stale: list[Path] = []
    for path in artifacts:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["manifest_hash"] != expected:
            stale.append(path)

    if args.check:
        if stale:
            print(
                f"manifest_hash drift: {len(stale)}/{len(artifacts)} artifacts stale",
                file=sys.stderr,
            )
            print(f"  expected: {expected}", file=sys.stderr)
            for path in stale:
                actual = json.loads(path.read_text(encoding="utf-8"))["manifest_hash"]
                print(f"  {_rel(path)}: {actual}", file=sys.stderr)
            print("\nfix: python scripts/rebind_manifest_hash.py", file=sys.stderr)
            print(
                "WARNING: rebinding only updates provenance. If the manifest change altered\n"
                "what these numbers MEAN, re-emit them from a real re-run first (cf. 4e6768a).",
                file=sys.stderr,
            )
            return 1
        print(f"ok: {len(artifacts)} artifacts bound to manifest_hash={expected}")
        return 0

    try:
        changed = [p for p in artifacts if rewrite(p, expected)]
    except RebindError as exc:
        print(f"rebind-error: {exc}", file=sys.stderr)
        return 2

    if not changed:
        print(f"ok: {len(artifacts)} artifacts already bound to manifest_hash={expected}")
        return 0

    print(f"rebound {len(changed)}/{len(artifacts)} artifacts to manifest_hash={expected}:")
    for path in changed:
        print(f"  {_rel(path)}")
    print(
        "\nNOTE: provenance only. If the manifest change altered what these numbers mean,\n"
        "re-emit them from a real re-run (cf. 4e6768a) — rebinding is not recomputation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
