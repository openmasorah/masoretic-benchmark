"""BL-01 Task 2 unit tests: _llm_combine (D-07).

Coverage (per plan 03-07 Task 2 behavior):
- T1: tier-1 agreement -> Claude chosen, tie_breaks=0, all tiers Claude.
- T2: tier-1 disagreement -> Claude wins alphabetically, tie_breaks=1,
      ALL tiers come from Claude (no tier-mixing across sources).
- T3: D-07 invariant — no field on the returned LineRecord ever sources
      from gemini_line when winner is "claude" (defense-in-depth).
- T4: nikkud/trop differences that strip to identical consonants count as
      tier-1 agreement.
- T5: empty tier4_records on every BL-01 line (LLMs unreliable on
      metamarks per Phase 1 D-07d).
"""

from __future__ import annotations

from baselines._llm_combine import combine_lines

# ----------------------------------------------------------------------
# T1: tier-1 agreement
# ----------------------------------------------------------------------


def test_tier1_agreement_no_tie_break(tmp_path=None):
    """When both sources strip to the same consonants, no tie-break used.
    Claude is chosen (arbitrary, deterministic)."""
    rec, winner, tie_breaks = combine_lines(
        claude_line={"raw": "שמע ישראל"},
        gemini_line={"raw": "שמע ישראל"},
        line_id="F1_L001",
        bbox=(10, 20, 500, 60),
    )
    assert winner == "claude"
    assert tie_breaks == 0
    assert rec.tier1 == "שמע ישראל"
    assert rec.tier2 == "שמע ישראל"
    assert rec.tier3 == "שמע ישראל"
    assert rec.tier4_records == tuple()
    assert rec.llm_winner == "claude"
    assert rec.llm_tie_breaks == 0


# ----------------------------------------------------------------------
# T2: tier-1 disagreement -> Claude wins, no tier-mixing
# ----------------------------------------------------------------------


def test_tier1_disagreement_claude_wins_no_tier_mixing():
    """Tier-1 disagrees -> Claude wins alphabetically (claude < gemini)
    AND ALL tiers come from Claude. Gemini's text appears nowhere on the
    record. (D-07 whole-line winner; physical-impossibility-bug guard.)"""
    claude_text = "שמע ישראל"
    # Tier-1 disagreement: substitute a Hebrew letter (non-Hebrew chars
    # are stripped by the tier-1 view, so a real letter swap is required).
    gemini_text = "שמא ישראל"
    rec, winner, tie_breaks = combine_lines(
        claude_line={"raw": claude_text},
        gemini_line={"raw": gemini_text},
        line_id="F1_L002",
        bbox=(0, 0, 100, 50),
    )
    assert winner == "claude"
    assert tie_breaks == 1
    # ALL tiers from Claude — verbatim
    assert rec.tier1 == claude_text
    assert rec.tier2 == claude_text
    assert rec.tier3 == claude_text
    # Gemini's text appears NOWHERE on the record (D-07 invariant)
    for field_name in ("tier1", "tier2", "tier3"):
        assert getattr(rec, field_name) != gemini_text


def test_no_tier_mixing_on_completely_different_strings():
    """Even when the sources disagree dramatically, the winner takes ALL
    tiers — the combine layer never blends."""
    rec, winner, tie_breaks = combine_lines(
        claude_line={"raw": "אבגד"},
        gemini_line={"raw": "זחטי"},
        line_id="F1_L003",
        bbox=(0, 0, 50, 50),
    )
    assert winner == "claude"
    assert tie_breaks == 1
    assert rec.tier1 == "אבגד"
    assert rec.tier2 == "אבגד"
    assert rec.tier3 == "אבגד"


# ----------------------------------------------------------------------
# T3 + T4: tier-1 stripping correctness
# ----------------------------------------------------------------------


def test_nikkud_difference_alone_counts_as_tier1_agreement():
    """If only nikkud (vowel points, U+05B0..U+05BD) differ, the
    consonantal stripping is identical -> tier-1 agreement -> no tie-break."""
    # שֵׁ vs שָׁ: same shin, different vowel. Stripped consonants identical.
    rec, winner, tie_breaks = combine_lines(
        claude_line={"raw": "שֵׁמע"},
        gemini_line={"raw": "שָׁמע"},
        line_id="F1_L004",
        bbox=(0, 0, 50, 50),
    )
    assert winner == "claude"
    assert tie_breaks == 0  # tier-1 agreement
    # Claude's tier1/2/3 retains its own nikkud
    assert rec.tier1 == "שֵׁמע"


def test_punctuation_difference_alone_counts_as_tier1_agreement():
    """Whitespace / punctuation differences are stripped before the
    tier-1 equality check."""
    rec, winner, tie_breaks = combine_lines(
        claude_line={"raw": "שמע ישראל"},
        gemini_line={"raw": "שמעישראל"},  # no space
        line_id="F1_L005",
        bbox=(0, 0, 50, 50),
    )
    assert tie_breaks == 0


# ----------------------------------------------------------------------
# T5: tier4_records always empty (BL-01 LLMs off-label for metamarks)
# ----------------------------------------------------------------------


def test_tier4_records_always_empty_for_bl01_lines():
    """LLMs are unreliable for tier-4 (Phase 1 D-07d carry-forward) — BL-01
    emits empty tier4_records on every line; the paper documents this limit."""
    for case in [
        ("שמע", "שמע"),
        ("שמע", "אחר"),  # disagreement
    ]:
        rec, _, _ = combine_lines(
            claude_line={"raw": case[0]},
            gemini_line={"raw": case[1]},
            line_id="F1_L006",
            bbox=(0, 0, 50, 50),
        )
        assert rec.tier4_records == tuple()
