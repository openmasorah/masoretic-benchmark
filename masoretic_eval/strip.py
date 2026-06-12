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
# NOTE: qamats qatan (U+05C7) and puncta extraordinaria (U+05C4/05C5) are NOT in
# this set — they are retained by the tier-2 score today; the diagnostics must
# match that (retained marks are labeled, not stripped).
_TIER2_EXTRA_STRIP = frozenset({0x05BF, 0x05C0, 0x05C3, 0x05C6})

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
