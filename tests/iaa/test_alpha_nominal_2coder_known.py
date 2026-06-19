"""Hand-coded reference test for Krippendorff α (nominal, 2 coders).

Pins the implementation against analytically-derived values so future edits
to the coincidence-matrix code surface as test failures.
"""

from __future__ import annotations

import math

from masoretic_eval.iaa.alpha import krippendorff_alpha_nominal


def test_perfect_agreement_alpha_is_one():
    """Two-coder perfect agreement on two classes → α = 1.0."""
    units = [("none", "none"), ("circellus", "circellus")]
    assert krippendorff_alpha_nominal(units) == 1.0


def test_known_value_4_units():
    """Hand-derived α = 12/19 on 4 units, 3 classes.

    Coincidence-matrix derivation (each unit contributes a (cA,cB) AND a
    (cB,cA) entry — total mass per unit = 2):

        (none, none) x2  → coinc[(none,none)] = 4
        (circ, circ) x1  → coinc[(circ,circ)] = 2
        (circ, rafe) x1  → coinc[(circ,rafe)] = 1, coinc[(rafe,circ)] = 1

        n_c[none]=4, n_c[circ]=3, n_c[rafe]=1; n_total=8
        D_o = 2 (off-diagonal mass)
        D_e = (4·3 + 4·1 + 3·4 + 3·1 + 1·4 + 1·3) / 7 = 38/7
        α = 1 - 2 / (38/7) = 1 - 14/38 = 24/38 = 12/19 ≈ 0.6315789
    """
    units = [
        ("none", "none"),
        ("none", "none"),
        ("circellus", "circellus"),
        ("circellus", "rafe"),
    ]
    expected = 12.0 / 19.0
    got = krippendorff_alpha_nominal(units)
    assert math.isclose(got, expected, abs_tol=1e-9), (got, expected)


def test_perfect_disagreement_alpha_negative():
    """Chance-corrected α should drop below zero for perfect disagreement.

    Verifies the chance-correction term is doing real work (a naive
    agreement-rate metric would land at 0; α correctly punishes this case
    further because the marginal distribution makes the disagreement
    *unlikely* under chance and therefore "worse than random").
    """
    units = [("a", "b"), ("b", "a"), ("a", "b"), ("b", "a")]
    alpha = krippendorff_alpha_nominal(units)
    assert alpha < 0.0
    # Spot-check the exact value: D_o = 8, D_e = 32/7, α = 1 - 8/(32/7) = -0.75
    assert math.isclose(alpha, -0.75, abs_tol=1e-9)


def test_empty_units_returns_nan():
    """Empty unit list → NaN (degenerate, no data)."""
    result = krippendorff_alpha_nominal([])
    assert math.isnan(result)
