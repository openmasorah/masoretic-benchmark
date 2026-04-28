"""Manifest version-bump callables for A-01 paired promotion (Phase 03.1).

The build_bump factory returns a callable suitable for SandboxRun.promote_folio's
``bump_manifest`` parameter. The returned callable:
  - increments expected_reports_per_baseline[baseline_id] by 1
  - updates frozen_at to current UTC (seconds precision per Phase 3 D-18)
  - appends a manifest_changelog row with reason "phase 3.1: <bl> <folio> promoted"
  - on first promotion (when manifest lacks them), idempotently seeds D-06 fields:
      cost_caps_usd: {per_folio: 5.00, per_run: 30.00}    (per A-02 numerical lock)
      nakdimon_model_hash: "8fd7722b8002a690"             (Phase 2 verified)
      dictabert_model_revision: "d311fbf7c403e50b040440e4859ac78064d025d0" (Phase 2)
      kraken_model_hash: "8514a0c7cc2b5b45"               (Phase 3 03-04 verified)
    Subsequent calls do NOT overwrite already-seeded values (idempotent).

Pitfall 7 row-count gate: A-01 per-folio bumps grow manifest_changelog ~20
entries per Phase 03.1 sweep (5 folios x 4 baselines). The deferred-items
"Plan B" fallback (per-invocation bumps) kicks in around 50 entries. We warn
at 40 and HARD-FAIL at 50 to force Plan B switchover before silent drift.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable
from datetime import UTC, datetime

# D-06 idempotent-seed constants (Phase 03.1 first-promotion fields).
_COST_CAPS_USD_DEFAULT = {"per_folio": 5.00, "per_run": 30.00}
_NAKDIMON_MODEL_HASH = "8fd7722b8002a690"
_DICTABERT_MODEL_REVISION = "d311fbf7c403e50b040440e4859ac78064d025d0"
_KRAKEN_MODEL_HASH = "8514a0c7cc2b5b45"

# Pitfall 7: manifest_changelog growth gate.
_MANIFEST_CHANGELOG_WARN_AT = 40
_MANIFEST_CHANGELOG_FAIL_AT = 50


class ManifestChangelogOverflow(Exception):
    """Raised when manifest_changelog row count reaches the Pitfall 7
    hard-fail threshold (50). Operator must switch to Plan B (per-invocation
    bumps) per CONTEXT.md <deferred> before further promotions can land."""


def build_bump(baseline_id: str, folio_id: str) -> Callable[[dict], dict]:
    """Return a bump_manifest callable for SandboxRun.promote_folio."""

    def _bump(prev: dict) -> dict:
        new = json.loads(json.dumps(prev))  # deep copy; never mutate prev
        new.setdefault("expected_reports_per_baseline", {})
        new["expected_reports_per_baseline"][baseline_id] = (
            new["expected_reports_per_baseline"].get(baseline_id, 0) + 1
        )
        now = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        prev_frozen = new.get("frozen_at", "")
        new["frozen_at"] = now
        new.setdefault("manifest_changelog", []).append(
            {
                "prev_frozen_at": prev_frozen,
                "new_frozen_at": now,
                "reason": f"phase 3.1: {baseline_id} {folio_id} promoted",
            }
        )
        # D-06: idempotent seeding on first promotion.
        if not new.get("cost_caps_usd"):
            new["cost_caps_usd"] = dict(_COST_CAPS_USD_DEFAULT)
        if not new.get("nakdimon_model_hash"):
            new["nakdimon_model_hash"] = _NAKDIMON_MODEL_HASH
        if not new.get("dictabert_model_revision"):
            new["dictabert_model_revision"] = _DICTABERT_MODEL_REVISION
        if not new.get("kraken_model_hash"):
            new["kraken_model_hash"] = _KRAKEN_MODEL_HASH

        # Pitfall 7: manifest_changelog row-count gate.
        # Evaluated AFTER appending the current row, so row N triggers when
        # this is the Nth entry. warn at 40, raise at 50.
        row_count = len(new["manifest_changelog"])
        if row_count >= _MANIFEST_CHANGELOG_FAIL_AT:
            raise ManifestChangelogOverflow(
                f"manifest_changelog has {row_count} rows "
                f"(threshold {_MANIFEST_CHANGELOG_FAIL_AT}). "
                "Switch to Plan B (per-invocation bumps) per CONTEXT.md "
                "<deferred> before further A-01 per-folio promotions."
            )
        if row_count >= _MANIFEST_CHANGELOG_WARN_AT:
            warnings.warn(
                f"manifest_changelog at {row_count} rows "
                f"(warn threshold {_MANIFEST_CHANGELOG_WARN_AT}, "
                f"hard-fail at {_MANIFEST_CHANGELOG_FAIL_AT}). "
                "Plan B (per-invocation bumps) switchover approaching.",
                stacklevel=2,
            )
        return new

    return _bump
