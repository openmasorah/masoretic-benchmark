"""Krippendorff α (nominal, 2 coders, complete data) for tier-4 ordinal codes.

This implements the coincidence-matrix form (Hayes & Krippendorff 2007). For
2 coders with complete data the result is mathematically Scott's π with a
finite-sample correction. The math mirrors the upstream falsification
reference for SPEC 260619-n3u (reproduced, not imported). The unit test
``tests/iaa/test_alpha_nominal_2coder_known.py`` pins this against a
hand-computed reference value.

Codes are nominal (no ordering). The full universe is "every consonant ordinal
in every verse"; the positive universe is the subset where at least one
annotator placed a non-`none` code. Canonicalization folds `double_rafe`
into `rafe` (per the 260617-d63 convention call).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from masoretic_eval.iaa.parse import Tier4Record


def units_per_verse(
    a_records: list[Tier4Record],
    b_records: list[Tier4Record],
    n_consonants: int,
    verse_ref: str,
    *,
    canonicalize: bool,
) -> list[tuple[str, str]]:
    """Build ordinal-aligned (code_A, code_B) units for one verse.

    The result has length ``n_consonants``: one tuple per ordinal in 1..N.

    When two marks collide on the same ordinal (e.g. circellus AND rafe), the
    fold rule from the falsification is applied:

    * `{circellus, rafe}` → ``"both"`` (distinct nominal class).
    * `{circellus, rafe, double_rafe}` after canon → also ``"both"``.
    * Single-mark sets → their canonicalized type.
    * Empty set → ``"none"``.

    The fold is applied per-side independently before the (A, B) pair is built.
    """

    def canon(t: str) -> str:
        if canonicalize and t == "double_rafe":
            return "rafe"
        return t

    a_by_ord: dict[int, set[str]] = defaultdict(set)
    b_by_ord: dict[int, set[str]] = defaultdict(set)
    for r in a_records:
        if r.verse_ref != verse_ref:
            continue
        a_by_ord[r.ordinal].add(canon(r.type))
    for r in b_records:
        if r.verse_ref != verse_ref:
            continue
        b_by_ord[r.ordinal].add(canon(r.type))

    def code_for_set(s: set[str]) -> str:
        if not s:
            return "none"
        if "circellus" in s and "rafe" in s:
            return "both"
        if "circellus" in s:
            return "circellus"
        if "rafe" in s:
            return "rafe"
        # raw mode only: a lone `double_rafe`. In canon mode this branch is
        # unreachable because the input was folded above.
        return next(iter(s))

    out: list[tuple[str, str]] = []
    for o in range(1, n_consonants + 1):
        cA = code_for_set(a_by_ord.get(o, set()))
        cB = code_for_set(b_by_ord.get(o, set()))
        out.append((cA, cB))
    return out


def krippendorff_alpha_nominal(units: Iterable[tuple[str, str]]) -> float:
    """Krippendorff's α (nominal) for 2 coders, complete data.

    Coincidence-matrix form:
        Each (cA, cB) unit contributes 1 to coinc[cA, cB] and 1 to coinc[cB, cA].
        n_c[c] = row sum of c.
        D_o = sum of off-diagonal coincidence weight.
        D_e = sum_{c1 != c2} n_c[c1] * n_c[c2] / (n_total - 1).
        α = 1 - D_o / D_e.

    Edge cases:
    * Empty unit list → NaN (caller is responsible for refusing this).
    * D_e == 0: returns 1.0 if perfect agreement (D_o == 0), else NaN.
    * Single unit: returns NaN (n_total = 2 satisfies n_total > 1; but with a
      single unit the marginal collapses to one class — D_e ≥ 0 by
      construction, so the standard branches handle it without special-casing).
    """
    units_list = list(units)
    if not units_list:
        return float("nan")

    coinc: dict[tuple[str, str], float] = defaultdict(float)
    for cA, cB in units_list:
        coinc[(cA, cB)] += 1.0
        coinc[(cB, cA)] += 1.0

    n_c: dict[str, float] = defaultdict(float)
    for (c1, _c2), w in coinc.items():
        n_c[c1] += w
    n_total = sum(n_c.values())

    if n_total <= 1:
        return float("nan")

    d_o = sum(w for (c1, c2), w in coinc.items() if c1 != c2)
    d_e = sum(n_c[c1] * n_c[c2] for c1 in n_c for c2 in n_c if c1 != c2) / (n_total - 1)

    if d_e == 0:
        return 1.0 if d_o == 0 else float("nan")
    return 1.0 - d_o / d_e


def alpha_from_records(
    a_records: list[Tier4Record],
    b_records: list[Tier4Record],
    *,
    verse_refs_with_n_cons: list[tuple[str, int]],
    canonicalize: bool,
    positive_only: bool,
) -> float:
    """Compose α from the parsed per-side records over a verse list.

    ``verse_refs_with_n_cons`` is ``[(verse_ref, n_consonants), ...]`` ordered
    to match the verse-folio map; both sides are restricted to these verses.
    """
    units: list[tuple[str, str]] = []
    for vref, n_cons in verse_refs_with_n_cons:
        verse_units = units_per_verse(
            a_records,
            b_records,
            n_cons,
            vref,
            canonicalize=canonicalize,
        )
        if positive_only:
            verse_units = [u for u in verse_units if u != ("none", "none")]
        units.extend(verse_units)
    return krippendorff_alpha_nominal(units)
