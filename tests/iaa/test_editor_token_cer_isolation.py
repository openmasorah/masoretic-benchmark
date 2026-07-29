"""Regression: editor tokens must never enter a tier-2/tier-3 CER surface.

The bug this guards
-------------------
``<DR>`` (double rafe) is excluded from ``PASSTHRU_TAGS`` on purpose, so that
``extract_positional`` can emit a tier-4 ``double_rafe`` record from it. Nothing
then removed it, so the four literal ASCII characters ``<DR>`` were scored as
text at tiers 2 and 3. The sides carry different token counts (A=25, B=56,
consensus=27 on the shipped Devarim 4-folio set), so every excess token scored
as four spurious edits.

Published impact before the fix, B-vs-consensus: tier 2 0.0172 -> 0.0031
(-82%), tier 3 0.0234 -> 0.0119 (-49%); B-vs-UXLC tier 2 0.0375 -> 0.0117.

The B-vs-UXLC pair was carried here without a reproduction path, so it was
re-derived in v0.1.1 rather than left as an assertion: scoring B's committed
projection against the pinned UXLC 2.5 Deuteronomy, macro-averaged over the 96
verses with UXLC as reference, gives **0.0117** through ``tier_view`` and
**0.0375** through the pre-fix composition (the same strip sequence with
``strip_editor_tokens`` omitted). Both halves reproduce exactly. Regenerating
them needs the gitignored UXLC cache, which is why this is a docstring and not
an assertion in this file.

The invariant below is stronger than "strip ``<DR>``": a chunk's tier CER must
be *invariant to the presence of editor tokens*, since they are markup, not
manuscript content. That catches the next token added to the vocabulary too.
"""

from __future__ import annotations

import pytest

from masoretic_eval.iaa.cer import per_verse_cer, strip_editor_tokens
from masoretic_eval.iaa.parse import PASSTHRU_TAGS, extract_positional

# A real-shaped verse fragment: Hebrew consonants + nikkud, with a double-rafe
# token attached to the consonant it annotates.
_BARE = "בְּרֵאשִׁית"
_WITH_DR = "בְּר<DR>ֵאשִׁית"


@pytest.mark.parametrize("tier", [1, 2, 3])
def test_editor_token_does_not_affect_cer(tier: int) -> None:
    """A side carrying <DR> must score identically to one that does not."""
    assert per_verse_cer(_BARE, _WITH_DR, tier=tier) == 0.0
    assert per_verse_cer(_WITH_DR, _BARE, tier=tier) == 0.0


@pytest.mark.parametrize("tier", [1, 2, 3])
def test_asymmetric_token_counts_do_not_inflate_cer(tier: int) -> None:
    """The actual shipped failure mode: unequal token counts across sides."""
    a = _WITH_DR + "<DR>"
    b = _BARE
    assert per_verse_cer(a, b, tier=tier) == 0.0


@pytest.mark.parametrize("tag", [*PASSTHRU_TAGS, "<DR>"])
def test_every_known_editor_token_is_stripped(tag: str) -> None:
    assert strip_editor_tokens(f"א{tag}ב") == "אב"


def test_tier4_extraction_still_sees_the_token() -> None:
    """The fix must not disarm tier-4: <DR> still yields a double_rafe record.

    This is the half that must NOT change — tier-4 F1 (0.9187) and the
    UXLC-frame reprojection depend on reading the raw chunk.
    """
    records = extract_positional(_WITH_DR, "Deut 1:1")
    assert [r.type for r in records] == ["double_rafe"]
    # <DR> consumes no consonant ordinal: it annotates the preceding consonant.
    assert records[0].ordinal == 2


def test_stripping_is_idempotent_and_content_preserving() -> None:
    assert strip_editor_tokens(strip_editor_tokens(_WITH_DR)) == _BARE
    assert strip_editor_tokens(_BARE) == _BARE
