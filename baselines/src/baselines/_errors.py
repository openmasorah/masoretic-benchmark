"""Phase 3 baseline exception hierarchy.

BaselineError is the root. ALL subclasses exit non-zero with stderr
reason — see baselines/_base.py::BaselineBase.run() for top-level handler.

Sibling exceptions (D-08, D-04, BL-08): ScopeViolation, BudgetExceeded,
KrakenInferenceFailure. All raised before any state mutation that would
pollute results/<bl>/ — sandbox-then-promote (D-14) is the durability guard.
"""

from __future__ import annotations


class BaselineError(Exception):
    """Root of the baselines exception hierarchy."""


class ScopeViolation(BaselineError):
    """BL-08: a folio is outside the Leningrad-only scope, OR
    a budget cap fired (BudgetExceeded subclass)."""


class BudgetExceeded(ScopeViolation):
    """D-08: per-folio or per-run LLM budget cap exceeded.
    Subclass of ScopeViolation — both are structural-error
    category (preregistered in paper methodology)."""


class KrakenInferenceFailure(BaselineError):
    """D-04: full-page Kraken transcription unrecoverable for a folio.
    Aborts the folio per atomic-run policy (D-14); sandbox is left
    for inspection."""
