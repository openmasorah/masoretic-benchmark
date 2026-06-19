"""Two CLI invocations with the same seed produce byte-identical JSON.

This is the "deterministic" half of SPEC 260619-n3u's reproducibility
contract. The other half — input SHA256 pinning — lives in
`test_input_sha256_pinned.py`.

The fixture is synthetic (not the published Devarim data) so the test runs
hermetically. The point estimate values don't matter; only the byte-stability
of the output across two runs does.
"""

from __future__ import annotations

import json
from pathlib import Path

from masoretic_eval.iaa.bootstrap import bootstrap_metric
from masoretic_eval.iaa.cli import serialize_result
from masoretic_eval.iaa.compute import compute_iaa

_A_SIDE = "אבגד֯ה׃\nוזחט<DR>י׃\nכלמנֿס׃\n"
_B_SIDE = "אבג֯דה׃\nוזחטֿי׃\nכלמנֿס׃\n"
_VERSE_FOLIO_MAP = [
    ("Deut.99.1", "F999A"),
    ("Deut.99.2", "F999A"),
    ("Deut.99.3", "F999B"),
]


def test_bootstrap_same_seed_same_output(tmp_path: Path):
    """Re-running with the same seed produces byte-identical JSON."""
    a_path = tmp_path / "a.txt"
    b_path = tmp_path / "b.txt"
    a_path.write_text(_A_SIDE, encoding="utf-8")
    b_path.write_text(_B_SIDE, encoding="utf-8")

    # Use a small B so the test is fast; the determinism property is invariant
    # over B (the RNG is reseeded deterministically each call).
    r1 = compute_iaa(a_path, b_path, _VERSE_FOLIO_MAP, bootstrap_b=64, bootstrap_seed=42)
    r2 = compute_iaa(a_path, b_path, _VERSE_FOLIO_MAP, bootstrap_b=64, bootstrap_seed=42)
    assert serialize_result(r1) == serialize_result(r2)


def test_bootstrap_different_seed_different_ci(tmp_path: Path):
    """Sanity: a different seed shifts the CI bounds (otherwise the RNG is
    being silently ignored — which would falsify the determinism claim)."""
    a_path = tmp_path / "a.txt"
    b_path = tmp_path / "b.txt"
    a_path.write_text(_A_SIDE, encoding="utf-8")
    b_path.write_text(_B_SIDE, encoding="utf-8")
    r1 = compute_iaa(a_path, b_path, _VERSE_FOLIO_MAP, bootstrap_b=64, bootstrap_seed=1)
    r2 = compute_iaa(a_path, b_path, _VERSE_FOLIO_MAP, bootstrap_b=64, bootstrap_seed=2)
    # At least one CI bound must differ across seeds. (Point estimates are
    # seed-invariant since they're computed on the full data.)
    j1 = json.loads(serialize_result(r1))
    j2 = json.loads(serialize_result(r2))
    assert j1 != j2


def test_bootstrap_metric_helper_determinism():
    """The low-level bootstrap helper is itself deterministic on the same seed."""
    payloads = [0.1, 0.2, 0.3, 0.4, 0.5]

    def mean(xs):
        return sum(xs) / len(xs)

    a = bootstrap_metric(payloads, mean, b=128, seed=7)
    b = bootstrap_metric(payloads, mean, b=128, seed=7)
    assert a == b
