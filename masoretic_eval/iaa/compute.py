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
    MatchedPair,
    detections_covering_type,
    detections_from_records,
    f1_with_tolerance,
)
from masoretic_eval.iaa.kappa import (
    BinaryAgreementUnit,
    cohens_kappa_binary,
    gwet_ac1_binary,
    pabak_binary,
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


def _aggregate_f1(per_verse_results: list[F1Result]) -> F1Result:
    """Sum per-verse TP/FP/FN and recompute precision/recall/F1 from totals.

    The bipartite matcher in :mod:`masoretic_eval.iaa.f1` assumes each
    ``(verse_ref, type, ordinal)`` triple is unique — its phase-1 ``b_used``
    set deduplicates on ordinal value, which is correct on the original data
    (one detection per ordinal) but silently collapses duplicates under a
    bootstrap resample that draws the same verse multiple times. To preserve
    verse-multiplicity, we run the matcher one verse at a time and sum
    TP/FP/FN over the resampled list, so a verse drawn N times contributes
    its per-verse counts N times. Equivalent to the previous global-flatten
    aggregation on unique-verse input (the point estimate); diverges only
    under resampling, which is the bug surface FINDING 1 documents.
    """
    matched: list[MatchedPair] = []
    tp = fp = fn = 0
    for r in per_verse_results:
        tp += r.tp
        fp += r.fp
        fn += r.fn
        matched.extend(r.matched)
    if tp + fp == 0:
        precision = 1.0 if tp + fn == 0 else 0.0
    else:
        precision = tp / (tp + fp)
    if tp + fn == 0:
        recall = 1.0 if tp + fp == 0 else 0.0
    else:
        recall = tp / (tp + fn)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return F1Result(
        f1=f1,
        precision=precision,
        recall=recall,
        tp=tp,
        fp=fp,
        fn=fn,
        matched=matched,
    )


def _f1_over_verses(
    verse_payloads: Sequence[tuple[list[Detection], list[Detection]]],
    *,
    tolerance: int,
) -> F1Result:
    per_verse = [
        f1_with_tolerance(a_dets, b_dets, tolerance=tolerance) for a_dets, b_dets in verse_payloads
    ]
    return _aggregate_f1(per_verse)


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
    (treating ``"both"`` as covering both types) and runs the headline
    bipartite-matching F1 per verse, then aggregates TP/FP/FN. Uses the
    same per-verse aggregation as :func:`_f1_over_verses` so verse
    multiplicity under resampling is preserved (FINDING 1).
    """
    per_verse = [
        f1_with_tolerance(
            detections_covering_type(a_dets, t),
            detections_covering_type(b_dets, t),
            tolerance=tolerance,
        )
        for a_dets, b_dets in verse_payloads
    ]
    return _aggregate_f1(per_verse)


def _macro_cer(per_verse: list[float]) -> float:
    if not per_verse:
        return float("nan")
    return sum(per_verse) / len(per_verse)


def _tier_cer_result(
    per_verse_cers: dict[str, float],
    verse_folio_map: Sequence[tuple[str, str]],
    verses_by_folio: dict[str, list[str]],
    *,
    bootstrap_b: int,
    bootstrap_seed: int,
    cer_vs_gold: dict[str, TierCERResult] | None = None,
) -> TierCERResult:
    """Build a per-folio + overall ``TierCERResult`` from per-verse CERs.

    Per-folio CIs resample verses within that folio; the overall CI resamples
    over the full verse pool (verse-bootstrap percentile, matching the headline
    convention). Shared by the pair-CER path and the A2a human-vs-gold path so
    the two cannot drift in aggregation or CI method.
    """
    per_folio: dict[str, MetricWithCI] = {}
    for folio, verse_list in verses_by_folio.items():
        folio_payloads = [per_verse_cers[v] for v in verse_list]
        per_folio[folio] = bootstrap_metric(
            folio_payloads, _macro_cer, b=bootstrap_b, seed=bootstrap_seed
        )
    overall_payloads = [per_verse_cers[v] for v, _ in verse_folio_map]
    overall = bootstrap_metric(overall_payloads, _macro_cer, b=bootstrap_b, seed=bootstrap_seed)
    return TierCERResult(cer_per_folio=per_folio, cer_overall=overall, cer_vs_gold=cer_vs_gold)


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

    # Build per-verse records, chunks, and consonant counts. The reference
    # consonant count uses the A-side chunk (matches the falsification's
    # "both sides agree at tier-1 to ~0.1%" convention).
    a_records_by_verse: dict[str, list[Tier4Record]] = {}
    b_records_by_verse: dict[str, list[Tier4Record]] = {}
    n_cons_by_verse: dict[str, int] = {}
    chunks_by_verse: dict[str, tuple[str, str, str]] = {}
    for (vref, folio), a_chunk, b_chunk in zip(verse_folio_map, a_chunks, b_chunks, strict=True):
        a_records_by_verse[vref] = extract_positional(a_chunk, vref)
        b_records_by_verse[vref] = extract_positional(b_chunk, vref)
        n_cons_by_verse[vref] = count_consonants(a_chunk)
        chunks_by_verse[vref] = (folio, a_chunk, b_chunk)

    return _compute_from_verse_data(
        verse_folio_map=verse_folio_map,
        a_records_by_verse=a_records_by_verse,
        b_records_by_verse=b_records_by_verse,
        n_cons_by_verse=n_cons_by_verse,
        chunks_by_verse=chunks_by_verse,
        bootstrap_b=bootstrap_b,
        bootstrap_seed=bootstrap_seed,
        metadata_extra={
            "a_sha256": a_sha,
            "b_sha256": b_sha,
            "gt_hash": gt_hash,
            "uxlc_anchored": False,
        },
    )


def _compute_from_verse_data(
    *,
    verse_folio_map: Sequence[tuple[str, str]],
    a_records_by_verse: dict[str, list[Tier4Record]],
    b_records_by_verse: dict[str, list[Tier4Record]],
    n_cons_by_verse: dict[str, int],
    chunks_by_verse: dict[str, tuple[str, str, str]],
    bootstrap_b: int,
    bootstrap_seed: int,
    metadata_extra: dict[str, object],
    gold_chunks_by_verse: dict[str, str] | None = None,
) -> IaaResult:
    """Shared post-parse kernel for raw-.txt and positional-projection paths.

    Both ``compute_iaa`` (raw .txt) and ``compute_iaa_from_positional``
    (CC-BY-4.0 projection JSON) build the same intermediate
    per-verse state and route through here. This is what makes their
    outputs byte-identical given the same source data — there is no
    second copy of the bootstrap / α / F1 / CER orchestration to drift.
    """
    a_detections_by_verse = _detections_per_verse(a_records_by_verse)
    b_detections_by_verse = _detections_per_verse(b_records_by_verse)
    n_verses = len(verse_folio_map)

    # Cluster labels parallel to per-verse payloads. NOT used for headline
    # CIs (see methodology note below). Retained on the helper so callers
    # who want a sensitivity check can request cluster-by-folio explicitly.
    #
    # METHODOLOGY (post-adversarial-review pivot, 260619-n3u):
    # Headline CIs use verse-bootstrap (cluster_by=None) — point estimates
    # are contained, intervals are mathematically well-defined at n=96.
    # Folio-clustering was tried as a headline CI per architect review;
    # adversarial review (Cameron–Miller / MacKinnon–Webb) showed G=4 outer
    # clusters does NOT support nominal-coverage CI estimation. The
    # cluster-bootstrap CIs ran ~20% wider than verse-only (confirming real
    # within-folio correlation, a sensitivity finding) but two metrics had
    # point > CI_upper under the percentile method (the small-G downward
    # bias artifact), and BCa over-corrected at G=4 (point < CI_lower).
    # We document within-folio correlation as a paper limitation rather
    # than report a broken CI as if it were nominal. Verse-bootstrap is
    # the published interval; cluster-bootstrap remains available as a
    # diagnostic via the public ``bootstrap_metric`` API.
    verse_folios = [folio for _, folio in verse_folio_map]  # noqa: F841 (kept for API symmetry / future use)

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

    # Per-type F1 — headline detection metric per type.
    f1_by_type: dict[str, dict[str, MetricWithCI]] = {}
    for t in ("circellus", "rafe"):

        def _exact(ps: list[tuple[list[Detection], list[Detection]]], t: str = t) -> float:
            return _f1_for_type_over_verses(ps, t=t, tolerance=0).f1

        def _tol1(ps: list[tuple[list[Detection], list[Detection]]], t: str = t) -> float:
            return _f1_for_type_over_verses(ps, t=t, tolerance=1).f1

        f1_by_type[t] = {
            "exact": bootstrap_metric(
                f1_payloads,
                _exact,
                b=bootstrap_b,
                seed=bootstrap_seed,
            ),
            "tolerance_1": bootstrap_metric(
                f1_payloads,
                _tol1,
                b=bootstrap_b,
                seed=bootstrap_seed,
            ),
        }

    # Per-type chance-corrected agreement: Cohen's κ + PABAK + Gwet's AC1.
    # Payload per verse = a list of `BinaryAgreementUnit` per type, where each
    # unit recodes one consonant ordinal as (positive | negative) for that
    # type. The headline F1 reads directly for DH/philology audiences; these
    # three coefficients are reported alongside to surface the prevalence-
    # paradox interaction. Cohen's κ understates agreement on Devarim (~5%
    # positive class); PABAK and AC1 are stable in that regime. Methodology
    # prose calls out the three together.
    units_by_type: dict[str, list[list[BinaryAgreementUnit]]] = {
        t: [] for t in ("circellus", "rafe")
    }
    for v, _folio in verse_folio_map:
        n_cons = n_cons_by_verse[v]
        a_ords: dict[str, set[int]] = {"circellus": set(), "rafe": set()}
        b_ords: dict[str, set[int]] = {"circellus": set(), "rafe": set()}
        for r in a_records_by_verse[v]:
            # double_rafe codes positive for rafe (the canonicalization
            # decision from the paper SPEC); "both" codes positive for both.
            if r.type in ("rafe", "double_rafe", "both"):
                a_ords["rafe"].add(r.ordinal)
            if r.type in ("circellus", "both"):
                a_ords["circellus"].add(r.ordinal)
        for r in b_records_by_verse[v]:
            if r.type in ("rafe", "double_rafe", "both"):
                b_ords["rafe"].add(r.ordinal)
            if r.type in ("circellus", "both"):
                b_ords["circellus"].add(r.ordinal)
        for t in ("circellus", "rafe"):
            verse_units = [
                BinaryAgreementUnit(
                    a_positive=(o in a_ords[t]),
                    b_positive=(o in b_ords[t]),
                )
                for o in range(1, n_cons + 1)
            ]
            units_by_type[t].append(verse_units)

    def _flatten(payloads: list[list[BinaryAgreementUnit]]) -> list[BinaryAgreementUnit]:
        out: list[BinaryAgreementUnit] = []
        for p in payloads:
            out.extend(p)
        return out

    kappa_by_type: dict[str, dict[str, MetricWithCI]] = {}
    for t in ("circellus", "rafe"):
        kappa_payloads = units_by_type[t]
        kappa_by_type[t] = {
            "cohen": bootstrap_metric(
                kappa_payloads,
                lambda ps: cohens_kappa_binary(_flatten(ps)),
                b=bootstrap_b,
                seed=bootstrap_seed,
            ),
            "pabak": bootstrap_metric(
                kappa_payloads,
                lambda ps: pabak_binary(_flatten(ps)),
                b=bootstrap_b,
                seed=bootstrap_seed,
            ),
            "ac1": bootstrap_metric(
                kappa_payloads,
                lambda ps: gwet_ac1_binary(_flatten(ps)),
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
        kappa_by_type=kappa_by_type,
        alpha_full_canon=alpha_full_canon,
        alpha_positive_canon=alpha_positive_canon,
        alpha_full_raw=alpha_full_raw,
        alpha_positive_raw=alpha_positive_raw,
        offset_distribution=offset,
    )

    # --- Tier 1/2/3 ---
    # Per-verse CER list; per-folio aggregates macro-average those.
    verses_by_folio: dict[str, list[str]] = defaultdict(list)
    for vref, folio in verse_folio_map:
        verses_by_folio[folio].append(vref)

    tier_results: dict[int, TierCERResult] = {}
    for tier in (1, 2, 3):
        per_verse_cers: dict[str, float] = {
            v: per_verse_cer(chunks_by_verse[v][1], chunks_by_verse[v][2], tier=tier)
            for v, _ in verse_folio_map
        }
        # A2a — human-vs-consensus-gold CER decomposition. When a gold
        # reference is supplied, each annotator's round-0 chunk is scored
        # against the gold chunk with GOLD AS THE CER REFERENCE (first arg →
        # denominator = gold length). This matches the Nakdimon-vs-UXLC tier-2
        # orientation, so cer_vs_gold.{a,b} are directly comparable to the
        # Nakdimon baseline. chunks_by_verse[v] = (folio, a_chunk, b_chunk).
        cer_vs_gold: dict[str, TierCERResult] | None = None
        if gold_chunks_by_verse is not None:
            a_vs_gold_cers = {
                v: per_verse_cer(gold_chunks_by_verse[v], chunks_by_verse[v][1], tier=tier)
                for v, _ in verse_folio_map
            }
            b_vs_gold_cers = {
                v: per_verse_cer(gold_chunks_by_verse[v], chunks_by_verse[v][2], tier=tier)
                for v, _ in verse_folio_map
            }
            cer_vs_gold = {
                "a": _tier_cer_result(
                    a_vs_gold_cers,
                    verse_folio_map,
                    verses_by_folio,
                    bootstrap_b=bootstrap_b,
                    bootstrap_seed=bootstrap_seed,
                ),
                "b": _tier_cer_result(
                    b_vs_gold_cers,
                    verse_folio_map,
                    verses_by_folio,
                    bootstrap_b=bootstrap_b,
                    bootstrap_seed=bootstrap_seed,
                ),
            }
        tier_results[tier] = _tier_cer_result(
            per_verse_cers,
            verse_folio_map,
            verses_by_folio,
            bootstrap_b=bootstrap_b,
            bootstrap_seed=bootstrap_seed,
            cer_vs_gold=cer_vs_gold,
        )

    metadata: dict[str, object] = {
        **metadata_extra,
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
