"""Paper-grade inter-annotator agreement (IAA) for the Devarim 4-folio benchmark.

Public surface (per upstream SPEC 260619-n3u):

    from masoretic_eval.iaa import compute_iaa, IaaResult, IaaInputMismatch

`compute_iaa` is the single entry point. It produces all-types F1 (exact +
±1 tolerance), per-type F1 breakouts for circellus and rafe (exact +
±1 tolerance each), Krippendorff α (raw + canon × full + positive universes),
the circellus offset distribution, and per-folio tier 1–3 CER — all with
deterministic verse-bootstrap CIs. Per-type Cohen's κ was deliberately
omitted; see `Tier4Result.__doc__` for the rationale.

Internals are organized by metric family so the math is greppable in one
function per file. The CLI lives at `masoretic_eval/iaa/cli.py` and runs via
`python -m masoretic_eval.iaa`.
"""

from masoretic_eval.iaa.compute import IaaInputMismatch, compute_iaa
from masoretic_eval.iaa.result import (
    IaaResult,
    MetricWithCI,
    OffsetDistribution,
    Tier4Result,
    TierCERResult,
)

__all__ = [
    "compute_iaa",
    "IaaResult",
    "IaaInputMismatch",
    "MetricWithCI",
    "OffsetDistribution",
    "Tier4Result",
    "TierCERResult",
]
