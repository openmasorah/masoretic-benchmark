"""Per-type binary chance-corrected agreement: Cohen's κ, PABAK, Gwet's AC1.

Reinstated after the post-adversarial-review pivot (260619-n3u). The initial
implementation dropped per-type κ because Cohen's prevalence-paradox produced
spurious negative values on Devarim (κ_circellus = -0.13, κ_rafe = -0.07)
under extreme positive-class skew (~5% prevalence). The original conclave
swap to per-type F1 alone was correct in that F1 is the right HEADLINE for
sparse-positive detection, but the JCDL adversarial reviewer rightly called
this "metric shopping": dropping κ also dropped a chance-corrected agreement
signal the field expects to see.

The defensible response is to report all three chance-corrected coefficients
alongside the per-type F1 headlines:

* **Cohen's κ** (Cohen 1960). Naively chance-corrects agreement using each
  rater's marginal prevalence. Susceptible to prevalence and bias paradoxes
  (Feinstein & Cicchetti 1990): under extreme class skew, κ can be near
  zero or negative even when raw agreement is very high. Reported for
  comparability with prior IAA literature; the prevalence-paradox
  interpretation goes in prose.
* **PABAK** (Byrt, Bishop, Carlin 1993). Prevalence-Adjusted Bias-Adjusted
  Kappa. ``PABAK = 2 * P_o - 1`` for binary nominal coding. Equivalent to
  Cohen's κ under uniform marginals and equal bias; immune to the
  prevalence paradox. Useful as an upper bound on chance-corrected
  agreement when prevalence is extreme.
* **Gwet's AC1** (Gwet 2008). Alternative chance-correction that's stable
  under high agreement and skewed prevalence. ``AC1 = (P_o - P_e_g) /
  (1 - P_e_g)`` with ``P_e_g = 2 * π * (1 - π)`` where ``π`` is the
  averaged marginal probability of the positive class. Reduces toward
  P_o as prevalence approaches 0 or 1.

Universe: the full consonant universe per verse (not just ordinals where ≥1
annotator placed a mark). For each type ``t`` ∈ {circellus, rafe}, each
ordinal contributes one binary code per rater: ``t`` if that rater placed
type ``t`` (or ``both``) at that ordinal, else ``not_t``. The "both" code is
treated as positive for both per-type computations (a both-marked ordinal
counts as a circellus instance AND a rafe instance).

The headline tier-4 result still leads with per-type F1 (exact + ±1
tolerance) because F1 reads directly for DH/philology audiences. κ / PABAK /
AC1 are reported alongside as the chance-corrected sensitivity panel, with
methodology prose calling out the prevalence-paradox for κ explicitly.

All three return ``float('nan')`` on degenerate inputs (e.g. P_e = 1 for κ,
zero observations); the caller treats NaN the same as a missing point.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BinaryAgreementUnit:
    """One ordinal coded by both raters as positive / negative for type ``t``.

    ``a_positive`` / ``b_positive`` are booleans: rater A and rater B's binary
    recoded codes for the type currently being measured.
    """

    a_positive: bool
    b_positive: bool


def _confusion(units: list[BinaryAgreementUnit]) -> tuple[int, int, int, int]:
    """Returns (n_pp, n_pn, n_np, n_nn) — the 2x2 confusion counts."""
    n_pp = sum(1 for u in units if u.a_positive and u.b_positive)
    n_pn = sum(1 for u in units if u.a_positive and not u.b_positive)
    n_np = sum(1 for u in units if not u.a_positive and u.b_positive)
    n_nn = sum(1 for u in units if not u.a_positive and not u.b_positive)
    return (n_pp, n_pn, n_np, n_nn)


def cohens_kappa_binary(units: list[BinaryAgreementUnit]) -> float:
    """Cohen's κ for binary nominal data, 2 raters, complete coding.

    Returns NaN when:

    * No observations (cannot compute marginals).
    * Both raters always agree on the same class (P_e == 1 → division by
      zero in the κ formula).
    """
    n = len(units)
    if n == 0:
        return float("nan")
    n_pp, n_pn, n_np, n_nn = _confusion(units)
    p_o = (n_pp + n_nn) / n
    # Marginal probabilities of "positive" for each rater
    p_a = (n_pp + n_pn) / n
    p_b = (n_pp + n_np) / n
    p_e = p_a * p_b + (1.0 - p_a) * (1.0 - p_b)
    if p_e >= 1.0:
        return float("nan")
    return (p_o - p_e) / (1.0 - p_e)


def pabak_binary(units: list[BinaryAgreementUnit]) -> float:
    """PABAK: Prevalence-Adjusted Bias-Adjusted Kappa (binary).

    For binary nominal data: ``PABAK = 2 * P_o - 1``. Equivalent to Cohen's
    κ under uniform marginals; independent of prevalence. Ranges from
    ``-1`` (perfect disagreement) to ``+1`` (perfect agreement); ``0`` is
    chance level under the uniform-marginal assumption.
    """
    n = len(units)
    if n == 0:
        return float("nan")
    n_pp, _n_pn, _n_np, n_nn = _confusion(units)
    p_o = (n_pp + n_nn) / n
    return 2.0 * p_o - 1.0


def gwet_ac1_binary(units: list[BinaryAgreementUnit]) -> float:
    """Gwet's AC1 (binary nominal, 2 raters).

    ``AC1 = (P_o - P_e_g) / (1 - P_e_g)`` with
    ``P_e_g = 2 * π * (1 - π)``, where ``π`` is the averaged-across-raters
    marginal probability of the positive class. Returns NaN when no
    observations or when P_e_g == 1 (only possible at π = 0.5 with all
    disagreement — degenerate).
    """
    n = len(units)
    if n == 0:
        return float("nan")
    n_pp, n_pn, n_np, _n_nn = _confusion(units)
    p_a = (n_pp + n_pn) / n
    p_b = (n_pp + n_np) / n
    pi_avg = (p_a + p_b) / 2.0
    p_e_g = 2.0 * pi_avg * (1.0 - pi_avg)
    p_o = (n_pp + (n - n_pp - n_pn - n_np)) / n  # nn = n - pp - pn - np
    if p_e_g >= 1.0:
        return float("nan")
    return (p_o - p_e_g) / (1.0 - p_e_g)
