"""Per-type Cohen's κ for the tier-4 paper headline.

For each type ``t ∈ {circellus, rafe}``, we collapse each ordinal slot into
a binary signal ``did_annotator_place_t``. ``both`` counts as t-present for
both types (the consonant carried both marks). κ is then computed on the
2×2 contingency table over the restricted universe.

Universe interpretation (per SPEC 260619-n3u):

    Restrict the universe to ordinals where at least one annotator placed
    `t` OR `none`. Binary κ on `{t, not-t}` per ordinal.

This module reads that filter as: include ordinals where at least one side
placed `t` (the "positive-class restriction" the SPEC author uses in the
sister α calculation). The `OR none` clause is read as ensuring negative
matches (none, none) inside the restricted universe contribute to agreement.
A pure-`none`-on-both ordinal carries no t signal and is excluded — same
treatment as the α_positive universe.

If the SPEC's intent was instead "include everything", widen the universe
in `_filter_universe`. The interpretation is documented here so a future
reviewer can change the call without spelunking.
"""

from __future__ import annotations

from masoretic_eval.iaa.alpha import units_per_verse
from masoretic_eval.iaa.parse import Tier4Record


def _binarize(code: str, t: str) -> int:
    """Map a 4-class code into binary t-present (1) / t-absent (0).

    ``both`` is t-present for either ``t='circellus'`` or ``t='rafe'``
    because the consonant carried both marks. Any other non-`t` code maps
    to 0 (t-absent).
    """
    if code == t:
        return 1
    if code == "both":
        return 1
    return 0


def _filter_universe(units: list[tuple[str, str]], t: str) -> list[tuple[int, int]]:
    """Restrict ordinals to "≥1 side placed t" and binarize.

    See module docstring for the universe interpretation.
    """
    out: list[tuple[int, int]] = []
    for c_a, c_b in units:
        a_bin = _binarize(c_a, t)
        b_bin = _binarize(c_b, t)
        if a_bin == 0 and b_bin == 0:
            continue
        out.append((a_bin, b_bin))
    return out


def cohen_kappa_binary(pairs: list[tuple[int, int]]) -> float:
    """Cohen's κ on a 2×2 contingency table built from ``pairs``.

    Returns NaN when the table is degenerate (zero units, or one class is
    fully unobserved on both sides so expected agreement = 1).
    """
    n = len(pairs)
    if n == 0:
        return float("nan")
    n_tt = sum(1 for a, b in pairs if a == 1 and b == 1)
    n_tf = sum(1 for a, b in pairs if a == 1 and b == 0)
    n_ft = sum(1 for a, b in pairs if a == 0 and b == 1)
    n_ff = sum(1 for a, b in pairs if a == 0 and b == 0)

    p_o = (n_tt + n_ff) / n
    p_at = (n_tt + n_tf) / n
    p_bt = (n_tt + n_ft) / n
    p_af = 1.0 - p_at
    p_bf = 1.0 - p_bt
    p_e = p_at * p_bt + p_af * p_bf

    if p_e == 1.0:
        # All units fell in one binary class on both sides; κ is undefined
        # by the standard formula. Caller should report as NaN, not 1.0.
        return float("nan")
    return (p_o - p_e) / (1.0 - p_e)


def kappa_for_type(
    a_records: list[Tier4Record],
    b_records: list[Tier4Record],
    *,
    verse_refs_with_n_cons: list[tuple[str, int]],
    t: str,
) -> float:
    """Compute binary Cohen's κ for one type, in canon mode.

    Canon mode here means the input records have already been folded by
    `units_per_verse(canonicalize=True)`. We always canonicalize for κ —
    the SPEC's κ headline numbers are reported on canon codes.
    """
    units: list[tuple[str, str]] = []
    for vref, n_cons in verse_refs_with_n_cons:
        verse_units = units_per_verse(
            a_records,
            b_records,
            n_cons,
            vref,
            canonicalize=True,
        )
        units.extend(verse_units)
    binary_pairs = _filter_universe(units, t)
    return cohen_kappa_binary(binary_pairs)
