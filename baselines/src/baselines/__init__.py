"""Phase 3 baselines for the Masoretic CER benchmark."""

from __future__ import annotations

__version__ = "0.1.0"

from baselines._base import LineRecord  # noqa: F401
from baselines._errors import (  # noqa: F401
    BaselineError,
    BudgetExceeded,
    KrakenInferenceFailure,
    ScopeViolation,
)

# BaselineBase is re-exported lazily to avoid importing the masoretic_eval
# manifest module at package-import time; some downstream tests construct
# fake manifests without installing masoretic-eval.
def __getattr__(name: str):
    if name == "BaselineBase":
        from baselines._base import BaselineBase

        return BaselineBase
    raise AttributeError(f"module 'baselines' has no attribute {name!r}")
