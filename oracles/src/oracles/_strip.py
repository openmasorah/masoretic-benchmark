"""D-04 / D-22: re-export scorer's private strip helpers.

Phase 1 precedent: gt-infra plans aliased these the same way.
If a future scorer plan promotes them to public API, swap imports here only.
"""

from masoretic_eval.tiers.tier1_consonantal import _strip_to_consonants as strip_to_consonantal
from masoretic_eval.tiers.tier2_nikkud import _strip_for_tier2 as strip_to_with_nikkud

__all__ = ["strip_to_consonantal", "strip_to_with_nikkud"]
