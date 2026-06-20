"""UXLC-backbone reprojection of per-annotator tier-4 ordinals.

The headline tier-4 metrics use per-annotator ordinal anchoring: every mark's
ordinal is computed against *its own annotator's* consonant stream (see
``masoretic_eval.iaa.parse`` and ``masoretic_eval/iaa/ALIGNMENT.md``). Where
the two annotators disagree at tier 1 (a one-letter insertion, deletion, or
different irregular-letter convention), every mark placed *after* the
disagreement sits at a different ordinal on each side. The bipartite matcher's
±1 tolerance phase absorbs that shift as "anchor ambiguity," but part of the
shift is tier-1 alignment noise — not the schema-representation question the
§6.1 anchor-ambiguity statistic in the paper is meant to surface.

This module provides a *sensitivity* path: align each annotator's consonant
stream to a shared UXLC consonant backbone and reproject each tier-4 record
to UXLC-frame ordinals before scoring. Under UXLC anchoring, a tier-1
disagreement no longer shifts tier-4 ordinals — the disagreement surfaces
only in the tier-1 alignment step, where it belongs.

The reprojection lives alongside the per-annotator path (not as a
replacement) because the published positional projection JSONs carry
per-annotator ordinals — switching the headline frame without extending
the public schema would break the cross-path byte-equivalence contract.
The numerical sensitivity reported here lets the paper bound FINDING 3
contamination empirically against the per-annotator headline.

Scope of this module
--------------------
Pure functions. No I/O, no UXLC loader call. The caller supplies the UXLC
consonant string per verse (typically via ``masoretic_eval.uxlc_loader``)
and the per-annotator records to reproject. Determinism: same inputs →
same output, no RNG involved.

Algorithm
---------
For each verse:

1. Extract the consonant-only stream from each annotator's raw chunk
   (Hebrew letters U+05D0..U+05EA, in chunk order; identical convention
   to ``parse.extract_positional``'s ordinal counter).
2. Strip the UXLC verse string to the same consonant universe (the
   loader's tier-1 string already does this, but we re-apply defensively
   in case the caller passed a richer string).
3. Compute a Hebrew-letter Levenshtein alignment from each side's
   consonant stream to UXLC via standard O(n*m) DP. The traceback picks,
   on ties: match > substitution > deletion (side ahead of UXLC) >
   insertion (UXLC ahead of side). This ordering keeps the reprojected
   ordinals "as close to identity as possible" — when side and UXLC
   sequences agree on a prefix, every prefix consonant gets its own
   identity ordinal.
4. The alignment yields, for each side ordinal o ∈ [1, |side_cons|],
   either a UXLC ordinal ô ∈ [1, |uxlc_cons|] (a match or substitution)
   or ``None`` (a side-only insertion).
5. ``Tier4Record(type, verse_ref, ord)`` records reproject to
   ``Tier4Record(type, verse_ref, ô)`` when an alignment exists; records
   that map to ``None`` (the mark anchors on a side-inserted consonant
   that has no UXLC counterpart) are dropped from the reprojected set.

Dropped records are reported separately so the caller can decide whether
to treat them as misses, FN-only, or out-of-scope for the sensitivity
column.
"""

from __future__ import annotations

from dataclasses import dataclass

from masoretic_eval.iaa.parse import Tier4Record

_CONSONANT_LO = 0x05D0
_CONSONANT_HI = 0x05EA


def _is_consonant(ch: str) -> bool:
    return _CONSONANT_LO <= ord(ch) <= _CONSONANT_HI


def consonants_of(text: str) -> str:
    """Return the Hebrew-consonant-only subsequence of ``text``.

    Used to derive the alignment stream from a raw chunk (or to defensively
    re-strip a UXLC tier-1 string in case the caller passed a richer one).
    """
    return "".join(c for c in text if _is_consonant(c))


# Traceback move codes. Order encodes tiebreak preference (lowest wins):
# match (no edit), substitution (both consume), deletion (side consumes
# alone — side has an extra letter UXLC lacks), insertion (UXLC consumes
# alone — UXLC has a letter side lacks).
_MOVE_MATCH = 0
_MOVE_SUB = 1
_MOVE_DEL = 2
_MOVE_INS = 3


def _align_levenshtein(side_cons: str, uxlc_cons: str) -> list[int | None]:
    """Align ``side_cons[i]`` → 1-based UXLC ordinal (or ``None``).

    Returns a list of length ``len(side_cons)``. Entry ``i`` is the 1-based
    index into ``uxlc_cons`` that side consonant ``i`` aligns to (an
    identity match or a substitution), or ``None`` if side consonant ``i``
    is a side-only insertion (no UXLC counterpart).

    Standard Levenshtein O(n*m) DP with traceback. Tiebreak ordering keeps
    the alignment close to identity when the prefix agrees.
    """
    n = len(side_cons)
    m = len(uxlc_cons)
    # dp[i][j] = min edits aligning side_cons[:i] to uxlc_cons[:j].
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i
    for j in range(1, m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub_cost = 0 if side_cons[i - 1] == uxlc_cons[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j - 1] + sub_cost,
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
            )

    # Traceback from (n, m). Tiebreak prefers MATCH > SUB > DEL > INS.
    alignment: list[int | None] = [None] * n
    i, j = n, m
    while i > 0 and j > 0:
        sub_cost = 0 if side_cons[i - 1] == uxlc_cons[j - 1] else 1
        diag = dp[i - 1][j - 1] + sub_cost
        up = dp[i - 1][j] + 1
        left = dp[i][j - 1] + 1
        best_move = _MOVE_INS
        best_score = left
        if up < best_score or (up == best_score and _MOVE_DEL < best_move):
            best_score = up
            best_move = _MOVE_DEL
        if diag < best_score or (
            diag == best_score and (_MOVE_MATCH if sub_cost == 0 else _MOVE_SUB) < best_move
        ):
            best_score = diag
            best_move = _MOVE_MATCH if sub_cost == 0 else _MOVE_SUB
        if best_move in (_MOVE_MATCH, _MOVE_SUB):
            alignment[i - 1] = j  # 1-based UXLC ordinal
            i -= 1
            j -= 1
        elif best_move == _MOVE_DEL:
            # side consonant has no UXLC counterpart (side-only insertion).
            alignment[i - 1] = None
            i -= 1
        else:  # _MOVE_INS
            # UXLC has a consonant side lacks; advance UXLC, keep side.
            j -= 1
    # Drain remaining side prefix as side-only insertions (None).
    while i > 0:
        alignment[i - 1] = None
        i -= 1
    # Remaining UXLC prefix (j > 0) is unconsumed; no effect on side alignment.

    return alignment


def align_side_to_uxlc(side_chunk: str, uxlc_verse_text: str) -> list[int | None]:
    """Convenience wrapper: extract consonants on both sides and align.

    ``side_chunk`` is the raw annotator chunk (post-``split_chunks``);
    ``uxlc_verse_text`` is the UXLC verse string (typically a tier-1 string
    from :func:`masoretic_eval.uxlc_loader.load_tier_strings`).
    """
    return _align_levenshtein(consonants_of(side_chunk), consonants_of(uxlc_verse_text))


@dataclass(frozen=True)
class ReprojectionResult:
    """Outcome of reprojecting one side's records to UXLC ordinals.

    ``kept``: records whose per-side ordinal aligned to a UXLC consonant.
    Each record's ``ordinal`` field is the UXLC-frame ordinal; ``type`` and
    ``verse_ref`` are preserved verbatim.

    ``dropped``: records anchored on a side-only insertion (no UXLC
    counterpart). Reported so the caller can decide whether to count them
    as FN, FP, or ignore.
    """

    kept: list[Tier4Record]
    dropped: list[Tier4Record]


def reproject_records(
    records: list[Tier4Record],
    side_chunk: str,
    uxlc_verse_text: str,
) -> ReprojectionResult:
    """Reproject one side's tier-4 records onto a UXLC consonant frame.

    Records are folded back through the alignment computed for the given
    ``side_chunk`` ↔ ``uxlc_verse_text`` pair. Records pointing at a
    side-only insertion (no UXLC counterpart) are surfaced via the
    ``dropped`` field rather than silently absorbed.
    """
    alignment = align_side_to_uxlc(side_chunk, uxlc_verse_text)
    kept: list[Tier4Record] = []
    dropped: list[Tier4Record] = []
    for r in records:
        # Records' ordinals are 1-based; alignment is 0-indexed by side ordinal.
        # Out-of-range ordinals (a mark anchored past the end of the side
        # consonant stream) should never happen — parse.extract_positional
        # only emits ordinals after seeing the consonant — but defensive
        # bound-check keeps the contract explicit.
        if r.ordinal < 1 or r.ordinal > len(alignment):
            dropped.append(r)
            continue
        uxlc_ord = alignment[r.ordinal - 1]
        if uxlc_ord is None:
            dropped.append(r)
        else:
            kept.append(Tier4Record(type=r.type, verse_ref=r.verse_ref, ordinal=uxlc_ord))
    return ReprojectionResult(kept=kept, dropped=dropped)
