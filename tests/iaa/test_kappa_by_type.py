"""Per-type chance-corrected agreement: Cohen's κ + PABAK + Gwet's AC1.

Reinstated 2026-06-19 after the adversarial post-review pivot. The initial
implementation dropped per-type κ because of Cohen's prevalence paradox
producing spurious negative values on Devarim. The pivot reinstates the
three coefficients alongside per-type F1 with the universe correctly
defined as the FULL consonant universe with binary recode — this resolves
the prevalence paradox numerically (κ comes out positive and high) and
addresses the JCDL "metric shopping" critique.

These tests pin:

1. Perfect-agreement degenerate: all three coefficients return 1.0.
2. Perfect-disagreement: κ = -1, PABAK = -1, AC1 = -1.
3. Prevalence-paradox fixture: when positive class is sparse and
   disagreement is concentrated in negatives, Cohen's κ understates
   while PABAK / AC1 stay near 1.0.
4. Returns NaN on empty input.
"""

from __future__ import annotations

import math

from masoretic_eval.iaa.kappa import (
    BinaryAgreementUnit,
    cohens_kappa_binary,
    gwet_ac1_binary,
    pabak_binary,
)


def _u(a: bool, b: bool) -> BinaryAgreementUnit:
    return BinaryAgreementUnit(a_positive=a, b_positive=b)


def test_perfect_agreement_all_one():
    """All three coefficients should equal 1.0 under perfect agreement."""
    units = [_u(True, True)] * 10 + [_u(False, False)] * 90
    # 10% positive prevalence, all agree.
    assert cohens_kappa_binary(units) == 1.0
    assert pabak_binary(units) == 1.0
    assert gwet_ac1_binary(units) == 1.0


def test_perfect_disagreement_negative():
    """All three coefficients should be negative (≤ 0) under perfect disagreement.

    Cohen's κ at -1, PABAK at -1, AC1 at -1 when raters disagree on every unit.
    """
    units = [_u(True, False), _u(False, True)] * 50
    assert cohens_kappa_binary(units) == -1.0
    assert pabak_binary(units) == -1.0
    assert math.isclose(gwet_ac1_binary(units), -1.0, abs_tol=1e-9)


def test_prevalence_paradox_kappa_understates_pabak_stable():
    """The motivating case: sparse positive class + a few disagreements.

    100 ordinals; 5 truly positive (both raters); 95 truly negative
    (both raters). Add 2 disagreements (B has positive, A doesn't).
    Raw agreement is 98/100 = 98%. Cohen's κ underweights because the
    base rate (~5% positive) makes "agree on negative" cheap by chance.
    PABAK and AC1 stay near 0.96 because they're stable under skew.
    """
    units = (
        [_u(True, True)] * 5  # agree positive
        + [_u(False, False)] * 93  # agree negative
        + [_u(False, True)] * 2  # disagree (A neg, B pos)
    )
    p_o = 98 / 100
    assert math.isclose(pabak_binary(units), 2 * p_o - 1, abs_tol=1e-9)
    # Cohen's κ on this skewed setup should be lower than the raw agreement
    # rate by a non-trivial margin (the paradox).
    k = cohens_kappa_binary(units)
    assert k < p_o - 0.10, f"κ {k} should be more than 0.10 below p_o {p_o} (prevalence paradox)"
    # AC1 is more stable than Cohen's κ here.
    ac1 = gwet_ac1_binary(units)
    assert ac1 > k, f"AC1 ({ac1}) should be greater than Cohen's κ ({k}) under sparse positives"


def test_empty_input_nan():
    """Zero observations → NaN, not a crash."""
    units: list[BinaryAgreementUnit] = []
    assert math.isnan(cohens_kappa_binary(units))
    assert math.isnan(pabak_binary(units))
    assert math.isnan(gwet_ac1_binary(units))


def test_all_one_class_kappa_nan_pabak_one_ac1_one():
    """When both raters always say "negative" — κ undefined (P_e=1) but raw agreement = 1."""
    units = [_u(False, False)] * 50
    assert math.isnan(cohens_kappa_binary(units))  # P_e = 1 → div by zero
    assert pabak_binary(units) == 1.0  # 2*1 - 1 = 1
    # AC1: π = 0, P_e_g = 0, AC1 = P_o / 1 = 1.
    assert gwet_ac1_binary(units) == 1.0
