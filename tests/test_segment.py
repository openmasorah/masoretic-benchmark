import pytest

from masoretic_eval.segment import cluster_codepoints, segment_clusters


def test_bet_plus_qamatz_is_one_cluster():
    # ב (U+05D1) + qamatz (U+05B8) — one grapheme cluster of 2 codepoints
    text = "בָ"
    clusters = list(segment_clusters(text))
    assert len(clusters) == 1
    assert clusters[0] == "בָ"


def test_multiple_clusters():
    # בָרֵא: bet-qamatz, resh-tsere, aleph — 3 clusters
    text = "בָרֵא"
    clusters = list(segment_clusters(text))
    assert len(clusters) == 3


def test_cluster_with_dagesh_and_trop():
    # בְּרֵאשִׁית (first word of Genesis): complex nikkud + trop stacks
    text = "בְּרֵאשִׁית"
    clusters = list(segment_clusters(text))
    # Should segment into one cluster per base consonant
    bases = [c[0] for c in clusters]
    assert bases == ["ב", "ר", "א", "ש", "י", "ת"]


def test_empty_string_produces_no_clusters():
    assert list(segment_clusters("")) == []


def test_cluster_codepoints_counts_codepoints_not_bytes():
    cluster = "בָ"
    assert cluster_codepoints(cluster) == 2


def test_segmentation_is_deterministic():
    text = "בָרֵ"
    assert list(segment_clusters(text)) == list(segment_clusters(text))


def test_pyicu_agrees_with_grapheme_on_hebrew_fixture():
    """Zed's cross-validation requirement: validate our UAX #29 segmenter
    against PyICU on a Hebrew fixture. Prevents self-grading."""
    icu = pytest.importorskip("icu")

    text = "בְּרֵאשִׁית"
    ours = list(segment_clusters(text))

    bi = icu.BreakIterator.createCharacterInstance(icu.Locale("he"))
    ustr = icu.UnicodeString(text)
    bi.setText(ustr)
    theirs = []
    start = bi.first()
    for end in bi:
        theirs.append(str(ustr[start:end]))
        start = end

    assert ours == theirs
