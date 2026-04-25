"""Whole-line winner combine logic with alphabetical tie-break (D-07).

Procedure:
    Step 1: if both sources' tier-1 strippings agree, take Claude
            (arbitrary, deterministic — no tie-break used).
    Step 2: tier-1 disagrees -> alphabetical tie-break: Claude < Gemini, so
            Claude wins. The alphabetical winner takes ALL FOUR tiers of
            that line.
    NO tier-mixing across sources within a line (D-07 — preventing the
    physical-impossibility bug where pointing attaches to consonants from
    a different source).

Returns ``(LineRecord, winner_name, tie_breaks_used)``.

The tier-1 stripping done HERE is intentionally minimal — keep-Hebrew-
letters-only — used ONLY for the combine equality check. The scorer
(D-22 untouched) re-runs its own tier-strip at score time. We avoid
pulling masoretic_eval at module import time so this combine logic is
unit-testable in isolation.
"""

from __future__ import annotations

from baselines._base import LineRecord


def _tier1_strip(text: str) -> str:
    """Cluster-level tier-1 (consonantal) view used ONLY for combine equality.

    Conservative codepoint-keep: keep ``[U+05D0, U+05EA]`` (Hebrew letters),
    drop everything else (whitespace, nikkud, trop, punctuation). The scorer
    re-derives its own tier-1 view at score time per D-22.
    """
    return "".join(c for c in text if 0x05D0 <= ord(c) <= 0x05EA)


def combine_lines(
    *,
    claude_line: dict,
    gemini_line: dict,
    line_id: str,
    bbox: tuple[int, int, int, int],
) -> tuple[LineRecord, str, int]:
    """Apply D-07 whole-line winner combine.

    Args:
        claude_line: ``{"raw": "..."}`` — Claude's transcription for the line.
        gemini_line: ``{"raw": "..."}`` — Gemini's transcription for the line.
        line_id: Stable line identifier (preserves Phase 1 D-30/D-31 line
            semantics).
        bbox: Line geometry from segmentation (Kraken-derived per BL-02
            shared infra).

    Returns:
        ``(LineRecord, winner_name, tie_breaks_used)`` where:
          - winner_name is ``"claude"`` or ``"gemini"`` (currently always
            ``"claude"`` per D-07 alphabetical tie-break);
          - tie_breaks_used is 0 (tier-1 agreement) or 1 (tier-1 disagreement).
    """
    c_raw = claude_line["raw"]
    g_raw = gemini_line["raw"]
    if _tier1_strip(c_raw) == _tier1_strip(g_raw):
        # Tier-1 agreement: deterministic pick of Claude (arbitrary; no
        # tie-break used).
        chosen_raw = c_raw
        winner = "claude"
        tie_breaks = 0
    else:
        # Alphabetical tie-break: "claude" < "gemini" -> Claude wins.
        chosen_raw = c_raw
        winner = "claude"
        tie_breaks = 1
    return (
        LineRecord(
            line_id=line_id,
            bbox=bbox,
            tier1=chosen_raw,    # WHOLE-LINE WINNER: all tiers from same source
            tier2=chosen_raw,
            tier3=chosen_raw,
            tier4_records=tuple(),  # BL-01 LLMs unreliable on metamarks (Phase 1 D-07d)
            llm_winner=winner,
            llm_tie_breaks=tie_breaks,
        ),
        winner,
        tie_breaks,
    )
