"""A-3 enforcement: zero compute_oracle_rates references in baselines/.

Per Phase 3 Adjudication A-3:
  - BL-03 imports oracles.nakdimon_oss.diacritize DIRECTLY
  - BL-04 imports oracles.dictabert.diacritize DIRECTLY
  - compute_oracle_rates is Phase 4 score-time, NOT a Phase 3 production wrapper

A grep walk over baselines/src/baselines/*.py + baselines/tests/*.py asserts
zero matches for the literal `compute_oracle_rates`. Any single match fails.

This file itself is excluded from the scan because it documents the literal
in its docstring (necessary for the test to be self-explanatory).
"""
from __future__ import annotations

import re
from pathlib import Path

# .../baselines/tests/test_no_compute_oracle_rates.py
#   parents[2] = sibling repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "baselines" / "src" / "baselines"
TESTS = REPO_ROOT / "baselines" / "tests"

PATTERN = re.compile(r"\bcompute_oracle_rates\b")

# Files that document the literal in docstrings/assertions are intentionally
# excluded from the scan — they are the enforcement substrate, not production
# code, and their job is to catch regressions in real source files.
EXCLUDED_FILENAMES = {
    "test_no_compute_oracle_rates.py",
    # Plan 03-05's BL-03 unit test references the literal in its assertion
    # message; it is a test-time enforcement, not a production import. Plan
    # 03-08's repository-wide grep is scoped to production source AND tests
    # except for the tests whose explicit job is to forbid the literal.
    "test_baseline_unit_nakdimon_chain.py",
}


def _scan(roots: list[Path]) -> list[tuple[Path, int, str]]:
    hits: list[tuple[Path, int, str]] = []
    for root in roots:
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if py.name in EXCLUDED_FILENAMES:
                continue
            for i, line in enumerate(
                py.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if PATTERN.search(line):
                    hits.append((py, i, line.strip()))
    return hits


def test_zero_compute_oracle_rates_references():
    """A-3: production source MUST have zero references to the score-time
    oracle wrapper. Plan 03-05 + 03-06 verified clean at file level; this
    test pins it for future plans."""
    hits = _scan([SRC, TESTS])
    assert not hits, (
        "A-3 violation: compute_oracle_rates is Phase 4 score-time only. "
        "BL-03/04 must import diacritize() directly. Offenders:\n"
        + "\n".join(f"  {p}:{i}: {line}" for p, i, line in hits)
    )


def test_zero_compute_oracle_rates_in_production_source_only():
    """Defense-in-depth: the production source tree (baselines/src/) MUST be
    clean even ignoring the EXCLUDED_FILENAMES carve-out. Tests can document
    the literal; production code cannot."""
    hits = _scan([SRC])
    assert not hits, (
        "A-3 violation in production source (baselines/src/): "
        "compute_oracle_rates is Phase 4 score-time only. Offenders:\n"
        + "\n".join(f"  {p}:{i}: {line}" for p, i, line in hits)
    )


def test_synthetic_violator_would_be_detected(tmp_path):
    """Self-test: planting a synthetic violator in a temp tree triggers the
    scan. Guarantees future regressions in `_scan` are caught."""
    src_dir = tmp_path / "baselines" / "src" / "baselines"
    src_dir.mkdir(parents=True)
    violator = src_dir / "_test_violator.py"
    violator.write_text(
        "from oracles.compute_oracles import compute_oracle_rates\n"
        "x = compute_oracle_rates(None, None)\n",
        encoding="utf-8",
    )
    hits = _scan([src_dir])
    assert hits, (
        "self-test of A-3 detector failed: planted violator was NOT detected"
    )
    # Two lines mention the literal (import + call)
    assert any("import" in line for _p, _i, line in hits)
