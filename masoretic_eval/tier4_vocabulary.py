"""The canonical tier-4 meta-mark vocabulary — one list, one place.

Before v0.3.0 this repo carried four divergent tier-4 vocabularies that no
test compared against each other:

1. ``masoretic_eval/schemas/scorer_input.schema.json`` — the CLI input enum,
   derived from the UXLC loader: ``pe, samekh, reversednun, puncta,
   large_letter, small_letter, suspended_letter, inverted_nun``.
2. ``schemas/baseline_prediction.schema.json`` — a second copy of the same
   eight terms.
3. The shipped IAA ground truth (``iaa_data/devarim_4folio/*.json``) —
   ``circellus, rafe, double_rafe``, sharing **no term at all** with (1).
4. ``schemas/manuscript.schema.json`` ``mark_type_enum`` — a catalog-coverage
   list that used ``puncta_extraordinaria`` where (1) said ``puncta``.

The practical consequence: ``masoretic-eval score`` could not validate, let
alone score, a single one of the 516 tier-4 records the benchmark ships as
its own gold. Every record failed the enum check. See
``tests/test_tier4_gt_roundtrip.py``, the regression test that would have
caught this at any point in the preceding eight months.

This module is now the sole definition. Both JSON Schemas are generated from
it in spirit and asserted against it in fact (``tests/test_tier4_vocabulary_
consistency.py``), so the four lists cannot silently diverge again.

Scope note
----------
Tier 4 spans two genuinely different kinds of thing, and keeping them in one
vocabulary is deliberate — they share the ``(type, verse_ref, ordinal)``
record shape and the same matcher:

* **Structural and special-letter marks** come from an edition's own markup
  (UXLC ``<pe/>``, ``<samekh/>``, ``<x>`` codes 4-8). They are editorial
  claims about the text.
* **Manuscript diacritics** (``circellus``, ``rafe``, ``double_rafe``) come
  from reading the codex itself. They are observations about ink on a page.

A scorer input may mix them; nothing here privileges one origin.
"""

from __future__ import annotations

from types import MappingProxyType

# --- Structural section markers (UXLC <pe/>, <samekh/> children of <v>) -----

STRUCTURAL_MARKS: tuple[str, ...] = (
    "pe",  # petuhah — open section break
    "samekh",  # setumah — closed section break
)

# --- Special letters (UXLC <x> codes 5-8 and 4) ----------------------------

SPECIAL_LETTER_MARKS: tuple[str, ...] = (
    "large_letter",  # litterae majusculae   — <x>5</x>
    "small_letter",  # litterae minusculae   — <x>6</x>
    "suspended_letter",  # litterae suspensae    — <x>7</x>
    "inverted_nun",  # nun hafukha, U+05C6   — <x>8</x> and <reversednun/>
    "puncta_extraordinaria",  # dotted letters, U+05C4/05C5 — <x>4</x>
)

# --- Manuscript diacritics (read off the codex; the IAA annotation axis) ---

DIACRITIC_MARKS: tuple[str, ...] = (
    "circellus",  # U+05AF, masorah-parva anchor
    "rafe",  # U+05BF
    "double_rafe",  # the <DR> editor token — see caveat below
)

#: Every valid value of a tier-4 record's ``type`` field, in documentation
#: order. This is the list both JSON Schema enums must equal.
TIER4_TYPES: tuple[str, ...] = STRUCTURAL_MARKS + SPECIAL_LETTER_MARKS + DIACRITIC_MARKS

#: Retired spellings, mapped to their canonical term. Kept as a migration aid
#: for callers holding pre-0.3.0 prediction files; **not** valid schema input.
#:
#: ``reversednun`` was the UXLC XML tag name for the same mark that ``<x>8</x>``
#: encoded as ``inverted_nun``, so the pre-0.3.0 enum listed one phenomenon
#: twice. Neither spelling occurs anywhere in the v0.1 corpus — UXLC
#: Deuteronomy yields ``{samekh: 136, pe: 32, large_letter: 2,
#: puncta_extraordinaria: 2}`` and nun hafukha sits at Num 10:35-36, outside
#: the frozen scope — so collapsing them moved no published number.
DEPRECATED_ALIASES: MappingProxyType[str, str] = MappingProxyType(
    {
        "reversednun": "inverted_nun",
        "puncta": "puncta_extraordinaria",
    }
)

#: Additional mark types a *manuscript catalog entry* may declare coverage of,
#: but which no scorer record type exists for yet. These describe layout and
#: scribal phenomena the benchmark can say a manuscript contains without being
#: able to score them positionally. Catalog-only; never valid in a tier-4
#: record.
CATALOG_ONLY_MARKS: tuple[str, ...] = (
    "line_filler",
    "stichographic_layout",
    "dotted_letter",  # distinct from puncta_extraordinaria: any scribal dot
    "rashe_tevot",  # abbreviation marks
)

#: The full vocabulary a ``corpus/manuscripts.yaml`` entry may draw on.
MANUSCRIPT_MARK_TYPES: tuple[str, ...] = TIER4_TYPES + CATALOG_ONLY_MARKS


def canonicalize(mark_type: str) -> str:
    """Return the canonical spelling of ``mark_type``.

    Accepts current terms unchanged and rewrites the retired spellings in
    :data:`DEPRECATED_ALIASES`. Raises ``ValueError`` on anything else rather
    than passing an unknown type through — a silently-tolerated unknown type
    is how the scorer/data divergence survived undetected.

    >>> canonicalize("reversednun")
    'inverted_nun'
    >>> canonicalize("rafe")
    'rafe'
    """
    if mark_type in TIER4_TYPES:
        return mark_type
    alias = DEPRECATED_ALIASES.get(mark_type)
    if alias is not None:
        return alias
    raise ValueError(
        f"unknown tier-4 mark type {mark_type!r}; valid types are {', '.join(TIER4_TYPES)}"
    )


__all__ = [
    "CATALOG_ONLY_MARKS",
    "DEPRECATED_ALIASES",
    "DIACRITIC_MARKS",
    "MANUSCRIPT_MARK_TYPES",
    "SPECIAL_LETTER_MARKS",
    "STRUCTURAL_MARKS",
    "TIER4_TYPES",
    "canonicalize",
]
