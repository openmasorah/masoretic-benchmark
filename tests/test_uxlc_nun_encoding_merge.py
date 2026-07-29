"""UXLC encodes nun hafukha two ways; both must land on one canonical type.

``<reversednun/>`` (a child of ``<v>``) and ``<x>8</x>`` (inline in a ``<w>``)
are two encodings of the same mark. Before scorer 0.3.0 the loader emitted them
as two distinct types, so a verse carrying both produced
``reversednun ordinal=1`` *and* ``inverted_nun ordinal=1`` — one phenomenon,
counted twice, each starting its own ordinal sequence.

Both now map to ``inverted_nun`` and share the per-verse ordinal counter. No
verse in the v0.1 corpus exercises this (nun hafukha is at Num 10:35-36, and
the frozen scope is Deuteronomy), which is why the fixture below is synthetic.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from masoretic_eval.uxlc_loader import load_uxlc

# Num 10:35 carries both encodings; 10:36 carries only the tag.
_XML = """<?xml version="1.0" encoding="utf-8"?>
<Tanach><tanach><book><names><name>Numbers</name></names>
<c n="10">
  <v n="35"><w>test<x>8</x></w><w>word</w><reversednun/></v>
  <v n="36"><w>word</w><reversednun/></v>
</c></book></tanach></Tanach>
"""


@pytest.fixture(scope="module")
def marks():
    path = pathlib.Path(tempfile.mkdtemp()) / "nun.xml"
    path.write_text(_XML, encoding="utf-8")
    return load_uxlc(path).metamarks


def test_both_encodings_produce_the_canonical_type(marks) -> None:
    assert {m.type for m in marks} == {"inverted_nun"}
    assert "reversednun" not in {m.type for m in marks}


def test_the_two_encodings_share_one_ordinal_sequence(marks) -> None:
    """A verse with both encodings numbers them 1 and 2, not 1 and 1.

    This is the regression: two records that collide on
    ``(type, verse_ref, ordinal)`` would be silently deduplicated by the
    tier-4 matcher, which scores over a *set* of those 3-tuples.
    """
    v35 = sorted(m.ordinal for m in marks if m.verse_ref == "Num.10.35")
    v36 = sorted(m.ordinal for m in marks if m.verse_ref == "Num.10.36")

    assert v35 == [1, 2]
    assert v36 == [1]


def test_ordinals_are_unique_per_verse(marks) -> None:
    keys = [(m.type, m.verse_ref, m.ordinal) for m in marks]

    assert len(set(keys)) == len(keys)


@pytest.mark.xfail(
    reason=(
        "KNOWN CAVEAT, documented not fixed. Verse-child tags are collected "
        "before inline <x> codes, so when one verse carries both encodings the "
        "ordinals run in parse order, not reading order: the verse-final "
        "<reversednun/> takes ordinal 1 and the earlier inline <x>8</x> takes 2. "
        "Pre-existing loader behaviour (pe/samekh have always been collected "
        "first); it only becomes observable now that both encodings share a "
        "type. No verse in the frozen v0.1 scope carries either encoding, so no "
        "published number is affected. Fixing it means merging the two "
        "collection passes into one document-order walk — a behaviour change to "
        "ordinal assignment, which is a pre-registered v0.2 decision, not a "
        "patch-release edit."
    ),
    strict=True,
)
def test_ordinals_would_follow_reading_order(marks) -> None:
    # In reading order the inline <x>8</x> in word 1 precedes the verse-final
    # <reversednun/>, so the first-emitted record should be the inline one.
    first = next(m for m in marks if m.verse_ref == "Num.10.35")
    assert first.ordinal == 2, "inline mark emitted first would mean reading order"
