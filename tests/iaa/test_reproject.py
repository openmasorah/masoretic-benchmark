"""Pins for the UXLC-backbone reprojection helper (FINDING 3 sensitivity).

The reprojection module aligns each annotator's consonant stream to a
shared UXLC backbone so tier-4 ordinals stop carrying tier-1 disagreement
noise. These tests pin the alignment algorithm's behavior on synthetic
inputs — actual numerical sensitivity on Devarim falls out of the
regeneration script (Phase A5).
"""

from __future__ import annotations

from masoretic_eval.iaa.parse import Tier4Record
from masoretic_eval.iaa.reproject import (
    align_side_to_uxlc,
    consonants_of,
    reproject_records,
)


def test_consonants_of_strips_to_hebrew_letter_block():
    assert consonants_of("בְּרֵאשִׁית") == "בראשית"
    assert consonants_of("אל֯ה ׃") == "אלה"


def test_identical_streams_align_to_identity():
    # "AABBCC" with itself: every ordinal maps to itself.
    a = "אבגדהו"
    alignment = align_side_to_uxlc(a, a)
    assert alignment == [1, 2, 3, 4, 5, 6]


def test_side_has_one_extra_consonant_drops_to_none():
    # side = "אבגדהו" (6 letters), uxlc = "אבגהו" (5 letters; missing ד at pos 4).
    # Expected: side pos 4 has no UXLC counterpart → None.
    side = "אבגדהו"
    uxlc = "אבגהו"
    alignment = align_side_to_uxlc(side, uxlc)
    assert alignment == [1, 2, 3, None, 4, 5]


def test_uxlc_has_one_extra_consonant_shifts_side_ordinals():
    # side = "אבגהו" (5), uxlc = "אבגדהו" (6; extra ד at uxlc pos 4).
    # Expected: side positions 4,5 should map to uxlc positions 5,6 (post-gap).
    side = "אבגהו"
    uxlc = "אבגדהו"
    alignment = align_side_to_uxlc(side, uxlc)
    assert alignment == [1, 2, 3, 5, 6]


def test_substitution_keeps_alignment_but_changes_letter():
    # side has ז where uxlc has ד; alignment still 1:1 (substitution, not insert).
    side = "אבגזהו"
    uxlc = "אבגדהו"
    alignment = align_side_to_uxlc(side, uxlc)
    assert alignment == [1, 2, 3, 4, 5, 6]


def test_reproject_records_kept_vs_dropped():
    # side = "אבגדה" (5), uxlc = "אבגה" (4; side has extra ד at pos 4).
    # Record at ordinal 4 (the side-only ד) drops; ordinals 1,2,3,5 reproject.
    side = "אבגדה"
    uxlc = "אבגה"
    records = [
        Tier4Record("circellus", "v", 1),
        Tier4Record("rafe", "v", 4),
        Tier4Record("circellus", "v", 5),
    ]
    result = reproject_records(records, side, uxlc)
    assert [r.ordinal for r in result.kept] == [1, 4]
    assert [r.type for r in result.kept] == ["circellus", "circellus"]
    assert [r.ordinal for r in result.dropped] == [4]
    assert result.dropped[0].type == "rafe"


def test_reproject_records_out_of_range_ordinals_drop():
    # Defensive: ordinal past the consonant stream length goes to dropped.
    side = "אבג"
    uxlc = "אבג"
    records = [Tier4Record("circellus", "v", 99)]
    result = reproject_records(records, side, uxlc)
    assert result.kept == []
    assert [r.ordinal for r in result.dropped] == [99]


def test_alignment_is_close_to_identity_on_long_prefix_match():
    # 10-consonant prefix shared, then a single insertion on side near the end.
    # The identity-preferring tiebreak should keep prefix ordinals 1:1.
    side = "אבגדהוזחטיכ"  # 11
    uxlc = "אבגדהוזחטי"  # 10 (missing the last כ)
    alignment = align_side_to_uxlc(side, uxlc)
    # Prefix 1..10 maps to UXLC 1..10; side pos 11 has no counterpart.
    assert alignment[:10] == list(range(1, 11))
    assert alignment[10] is None


def test_compute_iaa_uxlc_anchored_from_positional_smoke(tmp_path):
    """End-to-end smoke: UXLC-anchored pipeline runs and tags metadata.

    Hermetic — uses a 2-verse synthetic projection with a known tier-1
    disagreement between sides. Pins the new metadata fields
    (``uxlc_anchored=True``, ``dropped_record_counts``) and that the
    headline F1 differs from the per-annotator path when tier-1
    disagreement is present.
    """
    from masoretic_eval.iaa.compute import compute_iaa
    from masoretic_eval.iaa.projection import (
        compute_iaa_uxlc_anchored_from_positional,
        project_side,
        serialize_projection,
    )

    # Verse 1: A and B agree exactly; mark at ord 3 on both sides.
    # Verse 2: A has 5 letters, B has 6 (extra ב between א and ג).
    #          Both place a circellus on letter "ה". A: ord 4 (its own frame).
    #          B: ord 5 (its own frame, post-insertion).
    a_text = "אבגה֯ו ׃ אבגה֯ו ׃"
    b_text = "אבגה֯ו ׃ אבבגה֯ו ׃"
    verse_folio_map = [("Synth.1.1", "F0"), ("Synth.1.2", "F0")]

    a_proj = project_side(a_text, verse_folio_map, side_label="A")
    b_proj = project_side(b_text, verse_folio_map, side_label="B")
    a_proj_path = tmp_path / "a.json"
    b_proj_path = tmp_path / "b.json"
    a_proj_path.write_text(serialize_projection(a_proj) + "\n", encoding="utf-8")
    b_proj_path.write_text(serialize_projection(b_proj) + "\n", encoding="utf-8")

    uxlc_text_by_verse = {
        "Synth.1.1": "אבגהו",
        "Synth.1.2": "אבגהו",  # 5 letters; B has 6.
    }

    headline = compute_iaa_uxlc_anchored_from_positional(
        a_proj_path,
        b_proj_path,
        uxlc_text_by_verse,
        bootstrap_b=8,
        bootstrap_seed=42,
    )

    assert headline.metadata["uxlc_anchored"] is True
    assert headline.metadata["dropped_record_counts"]["a_side"] == 0
    assert headline.metadata["dropped_record_counts"]["b_side"] == 0

    # Per-annotator baseline on the same data: write to disk and route through
    # compute_iaa (raw .txt path). With the tier-1 insertion on B, the F1
    # exact will be lower on the per-annotator path than on the UXLC-anchored
    # path (the offset was tier-1 noise, not a schema-anchor disagreement).
    a_raw_path = tmp_path / "a.txt"
    b_raw_path = tmp_path / "b.txt"
    a_raw_path.write_text(a_text, encoding="utf-8")
    b_raw_path.write_text(b_text, encoding="utf-8")
    per_anno = compute_iaa(
        a_raw_path, b_raw_path, verse_folio_map, bootstrap_b=8, bootstrap_seed=42
    )

    assert per_anno.metadata["uxlc_anchored"] is False
    assert per_anno.tier4.f1_exact.point < headline.tier4.f1_exact.point


def test_uxlc_anchored_removes_tier1_offset_from_f1():
    """Concrete FINDING-3-removal demo: two annotators differ by one consonant
    insertion. Their per-annotator ordinals for the SAME UXLC consonant
    diverge by 1 → bipartite matcher absorbs as tolerance-1 (not exact)
    on the per-annotator path. UXLC reprojection lands them at the same
    ordinal → exact match restored.
    """
    from masoretic_eval.iaa.f1 import detections_from_records, f1_with_tolerance

    # UXLC = "אבגדהו" (6 letters).
    # A: matches UXLC. Mark on letter 5 (ה).
    # B: has an extra consonant inserted at position 3 (ז between ב and ג).
    #    B = "אבזגדהו" (7). Mark on B's "ה", which is at B-ordinal 6.
    uxlc = "אבגדהו"
    a_side = "אבגדהו"
    b_side = "אבזגדהו"
    a_recs = [Tier4Record("circellus", "v", 5)]
    b_recs = [Tier4Record("circellus", "v", 6)]

    # Per-annotator path: ordinals 5 vs 6 → tolerance match, not exact.
    a_per = detections_from_records(a_recs)
    b_per = detections_from_records(b_recs)
    per_anno_exact = f1_with_tolerance(a_per, b_per, tolerance=0)
    assert per_anno_exact.tp == 0
    per_anno_tol1 = f1_with_tolerance(a_per, b_per, tolerance=1)
    assert per_anno_tol1.tp == 1  # tolerance absorbs the tier-1 offset

    # UXLC-anchored path: both reproject to the same UXLC ordinal (5) → exact match.
    a_uxlc = reproject_records(a_recs, a_side, uxlc).kept
    b_uxlc = reproject_records(b_recs, b_side, uxlc).kept
    assert a_uxlc[0].ordinal == 5
    assert b_uxlc[0].ordinal == 5
    uxlc_exact = f1_with_tolerance(
        detections_from_records(a_uxlc),
        detections_from_records(b_uxlc),
        tolerance=0,
    )
    assert uxlc_exact.tp == 1  # exact match restored under shared frame
