"""Phase 3 baseline base class and shared LineRecord dataclass.

Task 1 of plan 03-02 ships LineRecord only; Task 2 appends BaselineBase.
See _base.py::BaselineBase for the locked template-method run() (D-12).
Subclasses override only infer_folio() — pinned by the AST invariant test.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineRecord:
    """One line of a folio's prediction.

    Phase 1 D-30/D-31: line_id is load-bearing. Run-on text rejected.
    bbox preserves Phase 1 PAGE-XML coordinates.
    Provenance fields (kraken_confidence, llm_winner, llm_tie_breaks)
    are baseline-specific and optional.

    Note on tier4_records: declared as ``tuple[dict, ...]`` for hashability
    under ``frozen=True``. Callers MUST pass a tuple, not a list — passing a
    list will break ``hash(record)`` with TypeError. ``dict`` itself is also
    unhashable; the type is preserved for shape, but if you need to hash a
    LineRecord with non-empty tier4_records, freeze the inner dicts to
    tuples-of-pairs at the call site.
    """

    line_id: str
    bbox: tuple[int, int, int, int]
    tier1: str
    tier2: str
    tier3: str
    tier4_records: tuple[dict, ...]
    kraken_confidence: float | None = None
    llm_winner: str | None = None
    llm_tie_breaks: int | None = None
