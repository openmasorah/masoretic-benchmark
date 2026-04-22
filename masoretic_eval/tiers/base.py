"""Common tier interface. Each tier implements `score(gt, pred) -> TierResult`."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TierResult:
    tier: int
    name: str
    # CER-style metrics (tiers 1–3); F1-style metrics (tier 4).
    cer: float | None = None
    edits: int | None = None
    denominator: int | None = None
    f1: float | None = None
    precision: float | None = None
    recall: float | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


class Tier(ABC):
    tier_number: int
    name: str

    @abstractmethod
    def score(self, gt: Any, pred: Any) -> TierResult: ...
