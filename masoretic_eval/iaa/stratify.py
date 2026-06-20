"""Subset-stratified tier-4 metrics for paper §5.2.

Three external reviewers (DH adversary, external review #1, external review #2)
converged on a request: report per-folio tier-4 F1 / α and a Ha'azinu-vs-prose
split. The Ha'azinu canticle (Deut 32:1-43) is dense in tier-4 marks compared
to the surrounding prose; lumping them together obscures whether the headline
agreement is driven by the dense region or holds across both.

This module exposes one entry point — :func:`stratify_tier4` — that takes the
same per-verse state ``compute_iaa_from_positional`` builds internally and
computes the headline tier-4 metric panel on each subset (each folio, plus
Ha'azinu vs prose). It does NOT bootstrap (the per-subset n is too small for
informative CIs at B=10000; point estimates are the deliverable). The
strata are pure verse subsets: same matcher, same α universe, same
canonicalization as the headline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from masoretic_eval.iaa.alpha import krippendorff_alpha_nominal, units_per_verse
from masoretic_eval.iaa.f1 import (
    Detection,
    detections_covering_type,
    detections_from_records,
    f1_with_tolerance,
)
from masoretic_eval.iaa.parse import Tier4Record


@dataclass(frozen=True)
class Tier4StratumPoint:
    """Point-estimate tier-4 panel for one verse subset.

    No CIs — per-subset n is too small for the bootstrap to be informative
    at B=10000. The paper reports these as stratification context for the
    headline; CIs are quoted only on the overall numbers.
    """

    n_verses: int
    f1_exact: float
    f1_tolerance_1: float
    f1_circellus_exact: float
    f1_circellus_tolerance_1: float
    f1_rafe_exact: float
    f1_rafe_tolerance_1: float
    alpha_full_canon: float
    alpha_positive_canon: float


def _haazinu_subset(verse_refs: Sequence[str]) -> list[str]:
    """The Ha'azinu canticle: Deut 32:1-43 (the song proper).

    Per the v0.2 frozen scope, Deut.32 covers verses 1-52; the canticle
    proper ends at 32:43 (44-52 are the narrative coda). The paper's
    section split honors the textual structure.
    """
    out: list[str] = []
    for vref in verse_refs:
        parts = vref.split(".")
        if len(parts) != 3:
            continue
        book, chapter, verse = parts
        try:
            v = int(verse)
        except ValueError:
            continue
        if book == "Deut" and chapter == "32" and 1 <= v <= 43:
            out.append(vref)
    return out


def _per_verse_payloads(
    verse_subset: Sequence[str],
    a_records_by_verse: dict[str, list[Tier4Record]],
    b_records_by_verse: dict[str, list[Tier4Record]],
) -> list[tuple[list[Detection], list[Detection]]]:
    return [
        (
            detections_from_records(a_records_by_verse[v]),
            detections_from_records(b_records_by_verse[v]),
        )
        for v in verse_subset
    ]


def _f1_over(payloads: list[tuple[list[Detection], list[Detection]]], *, tolerance: int) -> float:
    tp = fp = fn = 0
    for a, b in payloads:
        r = f1_with_tolerance(a, b, tolerance=tolerance)
        tp += r.tp
        fp += r.fp
        fn += r.fn
    if tp + fp == 0:
        precision = 1.0 if tp + fn == 0 else 0.0
    else:
        precision = tp / (tp + fp)
    if tp + fn == 0:
        recall = 1.0 if tp + fp == 0 else 0.0
    else:
        recall = tp / (tp + fn)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _f1_per_type_over(
    payloads: list[tuple[list[Detection], list[Detection]]], *, t: str, tolerance: int
) -> float:
    filt = [(detections_covering_type(a, t), detections_covering_type(b, t)) for a, b in payloads]
    return _f1_over(filt, tolerance=tolerance)


def _alpha_for_subset(
    verse_subset: Sequence[str],
    a_records_by_verse: dict[str, list[Tier4Record]],
    b_records_by_verse: dict[str, list[Tier4Record]],
    n_cons_by_verse: dict[str, int],
    *,
    canonicalize: bool,
    positive_only: bool,
) -> float:
    units: list[tuple[str, str]] = []
    for v in verse_subset:
        verse_units = units_per_verse(
            a_records_by_verse[v],
            b_records_by_verse[v],
            n_cons_by_verse[v],
            v,
            canonicalize=canonicalize,
        )
        if positive_only:
            verse_units = [u for u in verse_units if u != ("none", "none")]
        units.extend(verse_units)
    return krippendorff_alpha_nominal(units)


def stratify_tier4(
    verse_folio_map: Sequence[tuple[str, str]],
    a_records_by_verse: dict[str, list[Tier4Record]],
    b_records_by_verse: dict[str, list[Tier4Record]],
    n_cons_by_verse: dict[str, int],
) -> dict[str, dict[str, Tier4StratumPoint]]:
    """Per-folio and Ha'azinu-vs-prose tier-4 panels.

    Returns ``{"per_folio": {folio: Tier4StratumPoint, ...},
                "by_section": {"haazinu": ..., "prose": ...}}``.

    Strata that end up empty (no verses) are omitted from the output.
    """
    verse_refs = [v for v, _ in verse_folio_map]

    folio_verses: dict[str, list[str]] = {}
    for v, f in verse_folio_map:
        folio_verses.setdefault(f, []).append(v)

    haazinu = _haazinu_subset(verse_refs)
    prose = [v for v in verse_refs if v not in set(haazinu)]

    def point(subset: list[str]) -> Tier4StratumPoint:
        payloads = _per_verse_payloads(subset, a_records_by_verse, b_records_by_verse)
        return Tier4StratumPoint(
            n_verses=len(subset),
            f1_exact=_f1_over(payloads, tolerance=0),
            f1_tolerance_1=_f1_over(payloads, tolerance=1),
            f1_circellus_exact=_f1_per_type_over(payloads, t="circellus", tolerance=0),
            f1_circellus_tolerance_1=_f1_per_type_over(payloads, t="circellus", tolerance=1),
            f1_rafe_exact=_f1_per_type_over(payloads, t="rafe", tolerance=0),
            f1_rafe_tolerance_1=_f1_per_type_over(payloads, t="rafe", tolerance=1),
            alpha_full_canon=_alpha_for_subset(
                subset,
                a_records_by_verse,
                b_records_by_verse,
                n_cons_by_verse,
                canonicalize=True,
                positive_only=False,
            ),
            alpha_positive_canon=_alpha_for_subset(
                subset,
                a_records_by_verse,
                b_records_by_verse,
                n_cons_by_verse,
                canonicalize=True,
                positive_only=True,
            ),
        )

    per_folio = {f: point(vs) for f, vs in sorted(folio_verses.items()) if vs}
    by_section: dict[str, Tier4StratumPoint] = {}
    if haazinu:
        by_section["haazinu"] = point(haazinu)
    if prose:
        by_section["prose"] = point(prose)
    return {"per_folio": per_folio, "by_section": by_section}
