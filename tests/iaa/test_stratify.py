"""Pins for the per-folio and Ha'azinu-vs-prose tier-4 stratification."""

from __future__ import annotations

from masoretic_eval.iaa.parse import Tier4Record
from masoretic_eval.iaa.stratify import _haazinu_subset, stratify_tier4


def test_haazinu_subset_recognises_canonical_range():
    refs = [
        "Deut.31.28",
        "Deut.32.1",
        "Deut.32.43",
        "Deut.32.44",
        "Deut.33.1",
        "Deut.34.12",
    ]
    assert _haazinu_subset(refs) == ["Deut.32.1", "Deut.32.43"]


def test_haazinu_subset_handles_non_deut_chapters():
    """Non-Deut.32 verses must not enter the canticle subset."""
    refs = ["Gen.32.1", "Deut.32.1", "Deut.32.45"]
    assert _haazinu_subset(refs) == ["Deut.32.1"]


def test_stratify_tier4_partitions_verses_and_returns_panels():
    """Stratify two folios + a Ha'azinu + prose split with synthetic data."""
    verse_folio_map = [
        ("Deut.31.28", "F118B"),
        ("Deut.32.1", "F118B"),
        ("Deut.32.2", "F118B"),
        ("Deut.32.43", "F118B"),
        ("Deut.33.1", "F119A"),
    ]
    a_records_by_verse = {v: [Tier4Record("circellus", v, 3)] for v, _ in verse_folio_map}
    b_records_by_verse = {v: [Tier4Record("circellus", v, 3)] for v, _ in verse_folio_map}
    n_cons_by_verse = {v: 10 for v, _ in verse_folio_map}

    result = stratify_tier4(
        verse_folio_map, a_records_by_verse, b_records_by_verse, n_cons_by_verse
    )

    assert set(result["per_folio"].keys()) == {"F118B", "F119A"}
    assert result["per_folio"]["F118B"].n_verses == 4
    assert result["per_folio"]["F119A"].n_verses == 1

    # All-agreement synthetic data → F1 = 1.0 on every subset.
    for stratum in result["per_folio"].values():
        assert stratum.f1_exact == 1.0
        assert stratum.f1_tolerance_1 == 1.0

    assert set(result["by_section"].keys()) == {"haazinu", "prose"}
    assert result["by_section"]["haazinu"].n_verses == 3  # 32.1, 32.2, 32.43
    assert result["by_section"]["prose"].n_verses == 2  # 31.28, 33.1


def test_stratify_tier4_handles_disagreement_correctly():
    """Disagreement on one verse must surface in the relevant strata's F1."""
    verse_folio_map = [
        ("Deut.32.1", "F118B"),  # haazinu — A=ord 3, B=ord 5 (off by 2; no tol match)
        ("Deut.33.1", "F119A"),  # prose — both agree
    ]
    a_records_by_verse = {
        "Deut.32.1": [Tier4Record("circellus", "Deut.32.1", 3)],
        "Deut.33.1": [Tier4Record("rafe", "Deut.33.1", 2)],
    }
    b_records_by_verse = {
        "Deut.32.1": [Tier4Record("circellus", "Deut.32.1", 5)],
        "Deut.33.1": [Tier4Record("rafe", "Deut.33.1", 2)],
    }
    n_cons_by_verse = {v: 10 for v, _ in verse_folio_map}

    result = stratify_tier4(
        verse_folio_map, a_records_by_verse, b_records_by_verse, n_cons_by_verse
    )
    # Ha'azinu has the disagreement → F1 exact 0; prose is clean → F1 exact 1.
    assert result["by_section"]["haazinu"].f1_exact == 0.0
    assert result["by_section"]["prose"].f1_exact == 1.0
