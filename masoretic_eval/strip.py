"""Shared tier-2 strip view.

`strip_for_tier2` is the single source of truth for the tier-2 (nikkud) view of
a string: trop (taamim) and the tier-4 Hebrew punctuation marks (rafe, paseq,
sof pasuq, nun hafukha) are removed so they are not double-counted across tiers,
then runs of 2+ spaces are collapsed.

Both the tier-2 *score* (`tiers.tier2_nikkud`) and the tier-2 *diagnostics*
(`metrics.confusion`, `metrics.nakdimon`) must consume this exact view — a past
audit found the diagnostics applied only `normalize_for_scoring`, leaking trop
and rafe into a surface the tier-2 score deliberately excludes.
"""

from __future__ import annotations

import re

# Tier-4 / non-nikkud Hebrew punctuation removed from the tier-2 view so it is
# not counted twice across tiers. Mirrors uxlc_loader.load_tier_strings(tier=2).
# Members: meteg/ga'ya (U+05BD), rafe (U+05BF), paseq (U+05C0), sof pasuq
# (U+05C3), nun hafukha (U+05C6) — all retained at tier 3, so stripping here
# removes a tier-2/tier-3 double-count, not signal.
# Meteg (U+05BD) stripped per DECISIONS.md 2026-06-15 (metrical mark, not
# phonemic nikkud; exact rafe precedent). MUST stay in sync with the second copy
# at uxlc_loader.py::_TIER2_EXTRA_STRIP or the score-path and loader-path diverge.
# NOTE: qamats qatan (U+05C7) and puncta extraordinaria (U+05C4/05C5) are NOT in
# this set — they are retained by the tier-2 score today; the diagnostics must
# match that (retained marks are labeled, not stripped).
_TIER2_EXTRA_STRIP = frozenset({0x05BD, 0x05BF, 0x05C0, 0x05C3, 0x05C6})

# Collapse runs of 2+ spaces produced when stripped codepoints were adjacent to
# spaces (e.g. paseq U+05C0 in "word ׀ word").  Mirrors uxlc_loader behavior.
_MULTISPACE = re.compile(r"  +")


def strip_for_tier2(text: str) -> str:
    """Strip trop + tier-2-extra Hebrew punctuation, then collapse whitespace."""
    out: list[str] = []
    for c in text:
        cp = ord(c)
        if 0x0591 <= cp <= 0x05AF:  # trop (taamim)
            continue
        if cp in _TIER2_EXTRA_STRIP:
            continue
        out.append(c)
    return _MULTISPACE.sub(" ", "".join(out)).strip()
