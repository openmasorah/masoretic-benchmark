"""The UXLC loader must emit only canonical tier-4 types.

History — why this test's assertion changed in 0.3.0
----------------------------------------------------
This file used to assert ``schema_enum == loader_vocab``: the baseline
prediction schema's tier-4 enum had to *equal* the vocabulary the UXLC loader
produces. That equality was the wrong invariant, and holding it is part of how
the scorer/data divergence survived.

The UXLC loader sees one axis of tier 4 — the structural and special-letter
marks an *edition* encodes (``<pe/>``, ``<samekh/>``, ``<x>`` codes). It has no
concept of the manuscript diacritics (``circellus``, ``rafe``,
``double_rafe``) that annotators read off the codex and that make up 100% of
the tier-4 ground truth this benchmark ships. Requiring the schema to equal
the loader's vocabulary therefore *forbade* the schema from admitting the
project's own data — and any attempt to fix the enum would have failed here,
looking like a regression.

The correct invariant is containment, asserted below: everything the loader
emits must be canonical, but the canonical vocabulary is free to be wider than
what one edition's markup happens to express. Equality between the two shipped
schema enums and the canonical list is asserted in
``tests/test_tier4_vocabulary_consistency.py``; that the shipped gold survives
the scorer is asserted in ``tests/test_tier4_gt_roundtrip.py``.
"""

from __future__ import annotations

from masoretic_eval.tier4_vocabulary import TIER4_TYPES
from masoretic_eval.uxlc_loader import _TAG_TO_TYPE, META_MARK_TAGS, _xcode_to_type


def _loader_emitted_types() -> set[str]:
    """Every tier-4 type ``load_uxlc`` can actually put in a record.

    Note this maps tag names through ``_TAG_TO_TYPE``: ``<reversednun/>`` is
    the UXLC *tag* for the mark canonically typed ``inverted_nun``. The old
    version of this test compared raw tag names, which is why ``reversednun``
    appeared to be a distinct mark type needing its own enum slot.
    """
    emitted = {_TAG_TO_TYPE.get(tag, tag) for tag in META_MARK_TAGS}
    emitted |= {
        mark_type
        for mark_type in (_xcode_to_type(code) for code in ("4", "5", "6", "7", "8"))
        if mark_type is not None
    }
    return emitted


def test_uxlc_loader_vocabulary_is_within_the_canonical_vocabulary():
    emitted = _loader_emitted_types()

    assert emitted, "loader emits no tier-4 types — this guard is not exercising anything"
    assert emitted <= set(TIER4_TYPES), (
        f"UXLC loader emits types outside the canonical vocabulary: "
        f"{sorted(emitted - set(TIER4_TYPES))}"
    )


def test_loader_does_not_emit_a_retired_spelling():
    """``reversednun`` is a tag name, never a record type, as of 0.3.0."""
    assert "reversednun" not in _loader_emitted_types()
    assert "puncta" not in _loader_emitted_types()
