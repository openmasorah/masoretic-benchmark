"""Public `compute_iaa()` orchestrator.

This composes the per-metric modules into the headline IAA table:

* Tier 4: F1 (exact + ±1 tolerance), Krippendorff α (full/positive × raw/canon),
  per-type Cohen's κ, signed-offset distribution over matched circellus pairs.
* Tier 1/2/3: per-folio macro CER + overall, plus bootstrap CIs.

All CIs come from `bootstrap_metric` (`random.Random` with seeded RNG).
Determinism contract: same inputs + same seed → byte-identical JSON when
serialized through `cli.serialize_result`.

`IaaInputMismatch` is raised when the caller passes expected SHA256 hashes
that disagree with the on-disk file contents — the byte-pinned reproducibility
guard from SPEC 260619-n3u.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from masoretic_eval.iaa.alpha import (
    krippendorff_alpha_nominal,
    units_per_verse,
)
from masoretic_eval.iaa.bootstrap import DEFAULT_B, DEFAULT_SEED, bootstrap_metric
from masoretic_eval.iaa.cer import per_verse_cer
from masoretic_eval.iaa.f1 import (
    Detection,
    F1Result,
    detections_covering_type,
    detections_from_records,
    f1_with_tolerance,
)
from masoretic_eval.iaa.offset import offset_distribution
from masoretic_eval.iaa.parse import (
    Tier4Record,
    count_consonants,
    extract_positional,
    split_chunks,
)
from masoretic_eval.iaa.result import (
    IaaResult,
    MetricWithCI,
    Tier4Result,
    TierCERResult,
)


class IaaInputMismatch(Exception):
    """Raised when an input file's SHA256 doesn't match the caller's expectation.

    The byte-pinned reproducibility guard from SPEC 260619-n3u. Caller can
    bypass with ``force=True`` (or the CLI's ``--force`` flag) when they
    intentionally re-run on different inputs.
    """


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _records_per_verse(
    records: list[Tier4Record],
) -> dict[str, list[Tier4Record]]:
    out: dict[str, list[Tier4Record]] = defaultdict(list)
    for r in records:
        out[r.verse_ref].append(r)
    return dict(out)


def _detections_per_verse(
    records_by_verse: dict[str, list[Tier4Record]],
) -> dict[str, list[Detection]]:
    return {v: detections_from_records(rs) for v, rs in records_by_verse.items()}


def _f1_over_verses(
    verse_payloads: Sequence[tuple[list[Detection], list[Detection]]],
    *,
    tolerance: int,
) -> F1Result:
    a_all: list[Detection] = []
    b_all: list[Detection] = []
    for a_dets, b_dets in verse_payloads:
        a_all.extend(a_dets)
        b_all.extend(b_dets)
    return f1_with_tolerance(a_all, b_all, tolerance=tolerance)


def _alpha_over_verses(
    verse_payloads: Sequence[
        tuple[
            list[Tier4Record], list[Tier4Record], str, int
        ]  # (a_records, b_records, verse_ref, n_cons)
    ],
    *,
    canonicalize: bool,
    positive_only: bool,
) -> float:
    units: list[tuple[str, str]] = []
    for a_recs, b_recs, vref, n_cons in verse_payloads:
        verse_units = units_per_verse(a_recs, b_recs, n_cons, vref, canonicalize=canonicalize)
        if positive_only:
            verse_units = [u for u in verse_units if u != ("none", "none")]
        units.extend(verse_units)
    return krippendorff_alpha_nominal(units)


def _f1_for_type_over_verses(
    verse_payloads: Sequence[tuple[list[Detection], list[Detection]]],
    *,
    t: str,
    tolerance: int,
) -> F1Result:
    """Per-type F1 across resampled verses.

    Filters each side's per-verse detections to those covering type ``t``
    (treating ``"both"`` as covering both types), relabels them to a single
    bucket, and runs the headline bipartite-matching F1. This keeps the
    matching algorithm identical to the headline F1 — only the input
    detection set changes.
    """
    a_all: list[Detection] = []
    b_all: list[Detection] = []
    for a_dets, b_dets in verse_payloads:
        a_all.extend(detections_covering_type(a_dets, t))
        b_all.extend(detections_covering_type(b_dets, t))
    return f1_with_tolerance(a_all, b_all, tolerance=tolerance)


def _macro_cer(per_verse: list[float]) -> float:
    if not per_verse:
        return float("nan")
    return sum(per_verse) / len(per_verse)


def compute_iaa(
    a_side_path: Path,
    b_side_path: Path,
    verse_folio_map: list[tuple[str, str]],
    *,
    bootstrap_b: int = DEFAULT_B,
    bootstrap_seed: int = DEFAULT_SEED,
    expected_a_sha256: str | None = None,
    expected_b_sha256: str | None = None,
    gt_hash: str | None = None,
    force: bool = False,
) -> IaaResult:
    """Compute paper-grade IAA between two annotator deliveries.

    Parameters
    ----------
    a_side_path, b_side_path
        Raw round-0 .txt files (one chunk per verse, separated by sof-pasuq).
    verse_folio_map
        ``[(verse_ref, folio), ...]`` in the order verses appear in both files.
        Length must equal the number of chunks parsed from each side.
    bootstrap_b, bootstrap_seed
        Bootstrap configuration. Seed is threaded through `random.Random` so
        same seed + same inputs → byte-identical output (the determinism
        contract).
    expected_a_sha256, expected_b_sha256
        If set, raise `IaaInputMismatch` when the on-disk SHA256 differs.
    gt_hash
        Optional GT-hash field recorded in the result metadata (the manifest's
        `gt_hash` for provenance). Not validated here.
    force
        Skip the SHA256 mismatch check. Use only when intentionally re-running
        on changed inputs (e.g. a new annotator delivery during development).
    """
    a_path = Path(a_side_path)
    b_path = Path(b_side_path)
    a_sha = _sha256(a_path)
    b_sha = _sha256(b_path)
    if not force:
        if expected_a_sha256 is not None and a_sha != expected_a_sha256:
            raise IaaInputMismatch(
                f"A-side SHA256 mismatch: expected {expected_a_sha256}, got {a_sha}"
            )
        if expected_b_sha256 is not None and b_sha != expected_b_sha256:
            raise IaaInputMismatch(
                f"B-side SHA256 mismatch: expected {expected_b_sha256}, got {b_sha}"
            )

    a_text = a_path.read_text(encoding="utf-8")
    b_text = b_path.read_text(encoding="utf-8")

    a_chunks = split_chunks(a_text)
    b_chunks = split_chunks(b_text)

    n_verses = len(verse_folio_map)
    if not (len(a_chunks) == len(b_chunks) == n_verses):
        raise ValueError(
            f"verse-count mismatch: verse_folio_map={n_verses}, "
            f"a_chunks={len(a_chunks)}, b_chunks={len(b_chunks)}"
        )

    # Build per-verse records, detections, and consonant counts. The reference
    # consonant count uses the A-side chunk (matches the falsification's
    # "both sides agree at tier-1 to ~0.1%" convention).
    a_records_all: list[Tier4Record] = []
    b_records_all: list[Tier4Record] = []
    a_records_by_verse: dict[str, list[Tier4Record]] = {}
    b_records_by_verse: dict[str, list[Tier4Record]] = {}
    n_cons_by_verse: dict[str, int] = {}
    for (vref, _folio), a_chunk, b_chunk in zip(verse_folio_map, a_chunks, b_chunks, strict=True):
        a_recs = extract_positional(a_chunk, vref)
        b_recs = extract_positional(b_chunk, vref)
        a_records_all.extend(a_recs)
        b_records_all.extend(b_recs)
        a_records_by_verse[vref] = a_recs
        b_records_by_verse[vref] = b_recs
        n_cons_by_verse[vref] = count_consonants(a_chunk)

    a_detections_by_verse = _detections_per_verse(a_records_by_verse)
    b_detections_by_verse = _detections_per_verse(b_records_by_verse)

    # --- Tier 4 ---
    # F1: payload per verse = (a_detections, b_detections). Statistic counts
    # TP/FP/FN across the resampled verses and computes F1.
    f1_payloads: list[tuple[list[Detection], list[Detection]]] = [
        (a_detections_by_verse.get(v, []), b_detections_by_verse.get(v, []))
        for v, _ in verse_folio_map
    ]
    f1_exact = bootstrap_metric(
        f1_payloads,
        lambda ps: _f1_over_verses(ps, tolerance=0).f1,
        b=bootstrap_b,
        seed=bootstrap_seed,
    )
    f1_tol1 = bootstrap_metric(
        f1_payloads,
        lambda ps: _f1_over_verses(ps, tolerance=1).f1,
        b=bootstrap_b,
        seed=bootstrap_seed,
    )

    # α: payload per verse = (a_records, b_records, verse_ref, n_cons).
    alpha_payloads = [
        (
            a_records_by_verse.get(v, []),
            b_records_by_verse.get(v, []),
            v,
            n_cons_by_verse[v],
        )
        for v, _ in verse_folio_map
    ]
    alpha_full_canon = bootstrap_metric(
        alpha_payloads,
        lambda ps: _alpha_over_verses(ps, canonicalize=True, positive_only=False),
        b=bootstrap_b,
        seed=bootstrap_seed,
    )
    alpha_positive_canon = bootstrap_metric(
        alpha_payloads,
        lambda ps: _alpha_over_verses(ps, canonicalize=True, positive_only=True),
        b=bootstrap_b,
        seed=bootstrap_seed,
    )
    alpha_full_raw = bootstrap_metric(
        alpha_payloads,
        lambda ps: _alpha_over_verses(ps, canonicalize=False, positive_only=False),
        b=bootstrap_b,
        seed=bootstrap_seed,
    )
    alpha_positive_raw = bootstrap_metric(
        alpha_payloads,
        lambda ps: _alpha_over_verses(ps, canonicalize=False, positive_only=True),
        b=bootstrap_b,
        seed=bootstrap_seed,
    )

    # Per-type F1 (replaces the κ-per-type breakouts that this module used
    # to ship). κ was dropped because Cohen's prevalence paradox produced
    # spurious negative values under extreme positive-class skew; F1 is
    # interpretable directly. Bootstrap reuses the headline F1 payloads
    # and bootstrap config.
    f1_by_type: dict[str, dict[str, MetricWithCI]] = {}
    for t in ("circellus", "rafe"):
        f1_by_type[t] = {
            "exact": bootstrap_metric(
                f1_payloads,
                lambda ps, t=t: _f1_for_type_over_verses(ps, t=t, tolerance=0).f1,
                b=bootstrap_b,
                seed=bootstrap_seed,
            ),
            "tolerance_1": bootstrap_metric(
                f1_payloads,
                lambda ps, t=t: _f1_for_type_over_verses(ps, t=t, tolerance=1).f1,
                b=bootstrap_b,
                seed=bootstrap_seed,
            ),
        }

    # Offset distribution — single computation over the full data's matched
    # circellus pairs at tolerance=1.
    full_f1_tol1 = _f1_over_verses(f1_payloads, tolerance=1)
    offset = offset_distribution(full_f1_tol1.matched)

    tier4 = Tier4Result(
        f1_exact=f1_exact,
        f1_tolerance_1=f1_tol1,
        f1_by_type=f1_by_type,
        alpha_full_canon=alpha_full_canon,
        alpha_positive_canon=alpha_positive_canon,
        alpha_full_raw=alpha_full_raw,
        alpha_positive_raw=alpha_positive_raw,
        offset_distribution=offset,
    )

    # --- Tier 1/2/3 ---
    # Per-verse CER list; per-folio aggregates macro-average those.
    chunks_by_verse: dict[str, tuple[str, str, str]] = {}
    for (vref, folio), a_chunk, b_chunk in zip(verse_folio_map, a_chunks, b_chunks, strict=True):
        chunks_by_verse[vref] = (folio, a_chunk, b_chunk)

    verses_by_folio: dict[str, list[str]] = defaultdict(list)
    for vref, folio in verse_folio_map:
        verses_by_folio[folio].append(vref)

    tier_results: dict[int, TierCERResult] = {}
    for tier in (1, 2, 3):
        per_verse_cers: dict[str, float] = {
            v: per_verse_cer(chunks_by_verse[v][1], chunks_by_verse[v][2], tier=tier)
            for v, _ in verse_folio_map
        }
        # Per-folio bootstrap CI: resample verses within that folio.
        per_folio: dict[str, MetricWithCI] = {}
        for folio, verse_list in verses_by_folio.items():
            folio_payloads = [per_verse_cers[v] for v in verse_list]
            per_folio[folio] = bootstrap_metric(
                folio_payloads,
                _macro_cer,
                b=bootstrap_b,
                seed=bootstrap_seed,
            )
        # Overall bootstrap CI: resample verses across the whole set.
        overall_payloads = [per_verse_cers[v] for v, _ in verse_folio_map]
        overall = bootstrap_metric(
            overall_payloads,
            _macro_cer,
            b=bootstrap_b,
            seed=bootstrap_seed,
        )
        tier_results[tier] = TierCERResult(cer_per_folio=per_folio, cer_overall=overall)

    metadata = {
        "a_sha256": a_sha,
        "b_sha256": b_sha,
        "gt_hash": gt_hash,
        "n_verses": n_verses,
        "n_folios": len(verses_by_folio),
        "bootstrap_b": bootstrap_b,
        "bootstrap_seed": bootstrap_seed,
        "bootstrap_seed_hex": f"0x{bootstrap_seed:X}",
    }

    return IaaResult(
        tier1=tier_results[1],
        tier2=tier_results[2],
        tier3=tier_results[3],
        tier4=tier4,
        metadata=metadata,
    )
