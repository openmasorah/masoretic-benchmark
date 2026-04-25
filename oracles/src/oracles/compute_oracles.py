"""Composite oracle caller (D-21).

Orchestrates Nakdimon (primary) + DICTA Nakdan (secondary) over a folio's
tier-2 prediction lines, returning per-folio mean disagreement rates ready
to feed the scorer CLI flags --nakdimon-disagreement-rate / --dicta-
disagreement-rate (ORA-04).

Aggregation (D-03): arithmetic mean of per-line rates (not codepoint-
weighted). DICTA None-rates (failures per D-13) are excluded from the
denominator. If ALL DICTA calls fail, the folio rate is None.

Accepts both prediction shapes:
  - Scorer-canonical: {"folio_id": str, "text": str, "metamarks": [...]}
    Treats `text` as a single tier-2 line (a folio scored as one unit).
  - Multi-line: {"lines": [{"tier2": str, ...}, ...]} or [{"tier2": str}, ...]
    Iterates each tier-2 line.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from oracles import nakdan_hybrid, nakdimon_oss


def _extract_tier2_lines(prediction: Any) -> list[str]:
    """Extract tier-2 strings from a prediction JSON, in document order.

    Three accepted shapes:
      1. Scorer canonical: {"folio_id":..., "text": "<tier2 text>", "metamarks":[]}
      2. Multi-line dict:  {"lines": [{"tier2": "..."}, ...]}
      3. Single dict:      {"tier2": "..."}
      4. List of dicts:    [{"tier2": "..."}, ...]
    """
    if isinstance(prediction, dict):
        # Scorer-canonical (golden fixture) shape: single `text` field.
        text = prediction.get("text")
        if isinstance(text, str) and text:
            return [text]
        if "lines" in prediction and isinstance(prediction["lines"], list):
            return [
                ln.get("tier2", "")
                for ln in prediction["lines"]
                if isinstance(ln, dict) and ln.get("tier2")
            ]
        if "tier2" in prediction:
            return [prediction["tier2"]] if prediction["tier2"] else []
        return []
    if isinstance(prediction, list):
        return [
            ln.get("tier2", "") for ln in prediction if isinstance(ln, dict) and ln.get("tier2")
        ]
    return []


def compute_oracle_rates(
    prediction_path: Path,
    *,
    with_dicta: bool = True,
) -> dict:
    """Compute per-folio Nakdimon + DICTA disagreement rates.

    Per D-03: arithmetic mean of per-line rates. DICTA None-rates excluded
    from denominator. Returns shape ready for scorer CLI flag injection.
    """
    prediction_path = Path(prediction_path)
    prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
    lines = _extract_tier2_lines(prediction)

    nakdimon_rates: list[float] = []
    dicta_rates: list[float] = []
    dicta_failures = 0
    model_hash = nakdimon_oss.MODEL_HASH

    for line in lines:
        n_rate, _ = nakdimon_oss.disagreement_rate(line)
        nakdimon_rates.append(n_rate)
        if with_dicta:
            d_rate, _ = nakdan_hybrid.disagreement_rate(line)
            if d_rate is None:
                dicta_failures += 1
            else:
                dicta_rates.append(d_rate)

    nakdimon_mean = (sum(nakdimon_rates) / len(nakdimon_rates)) if nakdimon_rates else 0.0
    if with_dicta and dicta_rates:
        dicta_mean: float | None = sum(dicta_rates) / len(dicta_rates)
    else:
        dicta_mean = None

    return {
        "nakdimon_disagreement_rate": nakdimon_mean,
        "dicta_disagreement_rate": dicta_mean,
        "audit": {
            "nakdimon_lines_scored": len(nakdimon_rates),
            "dicta_lines_scored": len(dicta_rates),
            "dicta_failures": dicta_failures,
            "model_hash": model_hash,
            "computed_at_iso": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        },
    }


__all__ = ["compute_oracle_rates"]
