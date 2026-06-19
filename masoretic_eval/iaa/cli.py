"""CLI for `python -m masoretic_eval.iaa`.

Inputs:

* ``--a-side`` / ``--b-side``: raw round-0 .txt files.
* ``--manifest``: path to ``phase_0_manifest.json``. Used to source the
  ``gt_hash`` (if present in the manifest's per-folio block) for metadata.
* ``--verse-folio-map``: path to a JSON file shaped as
  ``{"folios": {"<folio>": ["<verse_ref>", ...]}}`` (the shape produced by
  the upstream IAA ingest pipeline). The manifest does not (yet) carry the
  per-verse breakdown; this flag bridges the gap until that lands in the
  manifest.

Output:

* ``--output paper_iaa_results.json``: deterministic JSON. Re-running with
  the same inputs + same seed produces a byte-identical file. The CI test
  ``test_bootstrap_determinism.py`` pins this contract.

Pinning:

* If ``--output`` already exists and contains ``metadata.a_sha256`` /
  ``metadata.b_sha256`` values, the CLI checks the on-disk file SHAs against
  them. Mismatch raises ``IaaInputMismatch`` unless ``--force`` is passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from masoretic_eval.iaa.bootstrap import DEFAULT_B, DEFAULT_SEED
from masoretic_eval.iaa.compute import IaaInputMismatch, compute_iaa
from masoretic_eval.iaa.result import IaaResult


def _load_verse_folio_map(path: Path) -> list[tuple[str, str]]:
    """Load the verse_folio_map from JSON.

    Accepted shapes:

    * ``{"folios": {"F118B": ["Deut.32.1", ...], ...}}`` — preferred.
    * ``[["Deut.32.1", "F118B"], ...]`` — pass-through (rare; for direct list).
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [(v, f) for v, f in raw]
    if isinstance(raw, dict) and "folios" in raw:
        pairs: list[tuple[str, str]] = []
        for folio, verse_list in raw["folios"].items():
            for v in verse_list:
                pairs.append((v, folio))
        return pairs
    raise ValueError(f"unrecognised verse_folio_map shape in {path}")


def _gt_hash_from_manifest(manifest_path: Path | None) -> str | None:
    """Read a representative GT hash from the manifest, if present.

    Today the manifest stores `gt_hash` per-folio. We return the first
    non-null one as the result's `gt_hash` metadata — a hash binding without
    forcing a manifest change. If no folio carries a hash (current v0.2.0
    state), return None.
    """
    if manifest_path is None:
        return None
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    for folio in raw.get("folios", []):
        gh = folio.get("gt_hash")
        if gh:
            return str(gh)
    return None


def _to_dict(value: Any) -> Any:
    """Recursively convert frozen dataclasses → plain dicts for JSON.

    `asdict` would do this in one shot for the whole tree, but it loses the
    `MetricWithCI` shape pinning (ci_method/b come along, which is what we
    want). Plain recursion gives us explicit control over ordering when
    needed later.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _to_dict(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _to_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_dict(v) for v in value]
    return value


def serialize_result(result: IaaResult) -> str:
    """Produce the deterministic JSON output.

    ``sort_keys=True`` + fixed indent + UTF-8-no-ASCII-escape gives us byte
    stability. Floats serialize via Python's standard `repr`-stable encoding,
    which is deterministic across runs on a single platform; cross-platform
    determinism is not a SPEC requirement.
    """
    return json.dumps(
        _to_dict(result),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )


def _read_pinned_sha256s(output_path: Path) -> tuple[str | None, str | None]:
    """If `output_path` exists, return any pinned a/b SHA256 from its metadata."""
    if not output_path.exists():
        return (None, None)
    try:
        prev = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return (None, None)
    md = prev.get("metadata", {})
    return md.get("a_sha256"), md.get("b_sha256")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m masoretic_eval.iaa",
        description="Paper-grade IAA over Devarim 4-folio benchmark (SPEC 260619-n3u).",
    )
    parser.add_argument("--a-side", type=Path, required=True, help="A-side raw .txt")
    parser.add_argument("--b-side", type=Path, required=True, help="B-side raw .txt")
    parser.add_argument(
        "--verse-folio-map",
        type=Path,
        required=True,
        help="JSON file mapping folio → [verse_ref, ...]",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional phase_0_manifest.json (sourced for metadata.gt_hash).",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output JSON path")
    parser.add_argument("--bootstrap-b", type=int, default=DEFAULT_B, help="Bootstrap iterations")
    parser.add_argument(
        "--bootstrap-seed",
        type=lambda s: int(s, 0),
        default=DEFAULT_SEED,
        help="Bootstrap seed (default 0xBEEF); supports 0x/0b prefixes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip SHA256 input-pinning checks (re-run on intentionally-changed inputs)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    verse_folio_map = _load_verse_folio_map(args.verse_folio_map)
    gt_hash = _gt_hash_from_manifest(args.manifest)
    pinned_a, pinned_b = _read_pinned_sha256s(args.output)

    try:
        result = compute_iaa(
            a_side_path=args.a_side,
            b_side_path=args.b_side,
            verse_folio_map=verse_folio_map,
            bootstrap_b=args.bootstrap_b,
            bootstrap_seed=args.bootstrap_seed,
            expected_a_sha256=pinned_a,
            expected_b_sha256=pinned_b,
            gt_hash=gt_hash,
            force=args.force,
        )
    except IaaInputMismatch as exc:
        sys.stderr.write(f"ERROR: {exc}\nPass --force to override.\n")
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialize_result(result) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {args.output}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
