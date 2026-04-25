"""Task 1 tests: package scaffold + exception hierarchy + LineRecord shape.

Plan 03-02 Task 1 behavior tests, verbatim:
  - Test 1: error classes importable from baselines._errors
  - Test 2: subclassing relationships are correct
  - Test 3: LineRecord constructs with defaults; frozen=True hashable when
    tier4_records is an empty tuple
  - Test 4: package importable; __version__ exposed
"""

from __future__ import annotations


def test_exception_classes_importable():
    from baselines._errors import (  # noqa: F401
        BaselineError,
        BudgetExceeded,
        KrakenInferenceFailure,
        ScopeViolation,
    )


def test_exception_hierarchy():
    from baselines._errors import (
        BaselineError,
        BudgetExceeded,
        KrakenInferenceFailure,
        ScopeViolation,
    )

    assert issubclass(ScopeViolation, BaselineError)
    assert issubclass(BudgetExceeded, BaselineError)
    assert issubclass(BudgetExceeded, ScopeViolation)
    assert issubclass(KrakenInferenceFailure, BaselineError)
    # KrakenInferenceFailure is NOT a ScopeViolation
    assert not issubclass(KrakenInferenceFailure, ScopeViolation)


def test_linerecord_defaults_and_hashability():
    from baselines._base import LineRecord

    r = LineRecord(
        line_id="x_L001",
        bbox=(0, 0, 10, 10),
        tier1="א",
        tier2="א",
        tier3="א",
        tier4_records=(),
    )
    assert r.kraken_confidence is None
    assert r.llm_winner is None
    assert r.llm_tie_breaks is None
    # frozen=True + empty tuple => hashable
    assert hash(r) is not None


def test_linerecord_field_round_trip():
    from baselines._base import LineRecord

    r = LineRecord(
        line_id="lf_L042",
        bbox=(1, 2, 3, 4),
        tier1="abc",
        tier2="abcd",
        tier3="abcd~",
        tier4_records=(),
        kraken_confidence=0.987,
        llm_winner="claude",
        llm_tie_breaks=2,
    )
    assert r.line_id == "lf_L042"
    assert r.bbox == (1, 2, 3, 4)
    assert r.kraken_confidence == 0.987
    assert r.llm_winner == "claude"
    assert r.llm_tie_breaks == 2


def test_package_import_exposes_version():
    import baselines

    assert hasattr(baselines, "__version__")
    assert isinstance(baselines.__version__, str)
    assert baselines.__version__ == "0.1.0"


def test_package_re_exports_task1_surface():
    """Task 1 ships LineRecord + exception hierarchy. BaselineBase
    re-export is verified in test_base after Task 2 lands."""
    import baselines

    for name in (
        "LineRecord",
        "BaselineError",
        "ScopeViolation",
        "BudgetExceeded",
        "KrakenInferenceFailure",
    ):
        assert hasattr(baselines, name), f"baselines.__init__ missing re-export: {name}"
