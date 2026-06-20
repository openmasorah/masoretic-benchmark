"""CLI for `python -m masoretic_eval.iaa`.

Two input paths produce the byte-identical headline output:

* **Raw .txt path** (``--a-side`` / ``--b-side``): private round-0
  transcriptions in Yosef's layout-preserving format. ``--verse-folio-map``
  is required (the manifest does not yet carry the per-verse breakdown).
* **Positional-projection path** (``--a-positional`` / ``--b-positional``):
  CC-BY-4.0 projection JSONs at ``iaa_data/devarim_4folio/``. The
  ``verse_folio_map`` is sourced from the projections themselves;
  ``--verse-folio-map`` is unused.

Output:

* ``--output paper_iaa_results.json``: deterministic JSON. Re-running with
  the same inputs + same seed produces a byte-identical file. The CI tests
  ``test_bootstrap_determinism.py`` and
  ``test_positional_projection_round_trip.py`` pin this contract.

Pinning:

* If ``--output`` already exists and contains ``metadata.a_sha256`` /
  ``metadata.b_sha256`` values, the CLI checks the on-disk file SHAs against
  them. Mismatch raises ``IaaInputMismatch`` unless ``--force`` is passed.
  The SHAs identify the input file — raw .txt and projection JSON have
  different bytes (hence different SHAs), but every downstream number is
  identical.
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
from masoretic_eval.iaa.projection import (
    PositionalProjectionInvalid,
    compute_iaa_from_positional,
)
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
    # Raw .txt path — private round-0 transcriptions.
    parser.add_argument("--a-side", type=Path, default=None, help="A-side raw .txt")
    parser.add_argument("--b-side", type=Path, default=None, help="B-side raw .txt")
    parser.add_argument(
        "--verse-folio-map",
        type=Path,
        default=None,
        help="JSON file mapping folio → [verse_ref, ...] (required for raw .txt path)",
    )
    # Positional-projection path — CC-BY-4.0 publication surface.
    parser.add_argument(
        "--a-positional",
        type=Path,
        default=None,
        help="A-side positional projection JSON (CC-BY-4.0)",
    )
    parser.add_argument(
        "--b-positional",
        type=Path,
        default=None,
        help="B-side positional projection JSON (CC-BY-4.0)",
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


def _select_input_mode(args: argparse.Namespace) -> str:
    """Validate the input flags and return ``"raw"`` or ``"positional"``."""
    raw_set = args.a_side is not None or args.b_side is not None
    pos_set = args.a_positional is not None or args.b_positional is not None
    if raw_set and pos_set:
        raise SystemExit(
            "ERROR: cannot mix raw (--a-side/--b-side) and positional "
            "(--a-positional/--b-positional) inputs in one run.\n"
        )
    if pos_set:
        if args.a_positional is None or args.b_positional is None:
            raise SystemExit("ERROR: --a-positional and --b-positional must both be provided.\n")
        return "positional"
    if args.a_side is None or args.b_side is None:
        raise SystemExit(
            "ERROR: provide either --a-side/--b-side (raw .txt) or "
            "--a-positional/--b-positional (CC-BY projection).\n"
        )
    if args.verse_folio_map is None:
        raise SystemExit("ERROR: --verse-folio-map is required for the raw .txt path.\n")
    return "raw"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    mode = _select_input_mode(args)
    gt_hash = _gt_hash_from_manifest(args.manifest)
    pinned_a, pinned_b = _read_pinned_sha256s(args.output)

    try:
        if mode == "raw":
            verse_folio_map = _load_verse_folio_map(args.verse_folio_map)
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
        else:
            result = compute_iaa_from_positional(
                a_projection_path=args.a_positional,
                b_projection_path=args.b_positional,
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
    except PositionalProjectionInvalid as exc:
        sys.stderr.write(f"ERROR: invalid positional projection: {exc}\n")
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialize_result(result) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {args.output}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
