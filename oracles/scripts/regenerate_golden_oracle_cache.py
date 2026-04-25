"""Regenerate tests/fixtures/oracle_cache/golden_fixture_oracles.json.

Run ONCE during Phase 2 plan 02-05 to produce the cached oracle outputs
that the ORA-06 contract test compares against. Re-run on Nakdimon re-pin
(D-09) or DICTA endpoint URL change (Pitfall 2). Hits live DICTA -- must be
invoked with RUN_LIVE_ORACLES=1 set.

Outputs are committed to git; the contract test never hits live DICTA.

Degraded mode (Pitfall 1, NAKDIMON_PIN.md Notes):
  TF 2.15 aborts at preload_check on macOS arm64 + Python 3.11 -- importing
  oracles.nakdimon_oss is process-fatal (SIGABRT, not a catchable Python
  exception). Set NAKDIMON_DEGRADED=1 to run DICTA-only and produce a
  fixture with nakdimon_disagreement_rate=null. The operator re-runs on a
  Linux host (CI image, Phase 2 Plan 06) to refresh the Nakdimon column.
"""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = (
    Path(__file__).resolve().parents[2]
)  # masoretic-benchmark/ (oracles/scripts/x.py -> parents[2])
GOLDEN_PRED = REPO_ROOT / "tests" / "fixtures" / "golden" / "prediction.json"
OUTPUT = (
    REPO_ROOT / "oracles" / "tests" / "fixtures" / "oracle_cache" / "golden_fixture_oracles.json"
)


def _resolve_ip(endpoint_url: str) -> str:
    host = urlparse(endpoint_url).hostname or ""
    try:
        return socket.gethostbyname(host)
    except OSError:
        return "unresolved"


def _compute_dicta_only(text: str) -> tuple[float | None, dict]:
    """DICTA-only path used when NAKDIMON_DEGRADED=1.

    Imports nakdan_hybrid lazily so a clean degraded run does not also
    require TF (it doesn't anyway -- nakdan_hybrid is pure requests).
    """
    from oracles.nakdan_hybrid import disagreement_rate as dicta_rate

    return dicta_rate(text)


def _compute_full(prediction_path: Path) -> dict:
    """Standard path: full Nakdimon + DICTA via compute_oracle_rates."""
    from oracles.compute_oracles import compute_oracle_rates

    return compute_oracle_rates(prediction_path, with_dicta=True)


def main() -> int:
    if os.environ.get("RUN_LIVE_ORACLES") != "1":
        print("ERROR: set RUN_LIVE_ORACLES=1 to invoke live oracles.", flush=True)
        return 2
    if not GOLDEN_PRED.exists():
        print(f"ERROR: golden prediction not found at {GOLDEN_PRED}", flush=True)
        return 3

    degraded = os.environ.get("NAKDIMON_DEGRADED") == "1"

    if degraded:
        # DICTA-only: extract the prediction text manually + call DICTA once.
        pred_obj = json.loads(GOLDEN_PRED.read_text(encoding="utf-8"))
        text = pred_obj.get("text") or ""
        d_rate, _ = _compute_dicta_only(text)
        nakdimon_rate: float | None = None
        nakdimon_lines_scored = 0
        dicta_lines_scored = 0 if d_rate is None else 1
        dicta_failures = 1 if d_rate is None else 0
        # MODEL_HASH is structurally pinned in NAKDIMON_PIN.md (computed at
        # 02-02 against nakdimon==0.1.2 + bundled Nakdimon.h5 sha=5f693887...).
        # Carry forward as paper-citeable provenance even when TF cannot load
        # (Pitfall 1, NAKDIMON_PIN.md "Derived MODEL_HASH" block).
        model_hash: str | None = "8fd7722b8002a690"
        from oracles.nakdan_hybrid import ENDPOINT_URL  # local import (no TF)

        resolved_ip = _resolve_ip(ENDPOINT_URL)
        regeneration_note = (
            "Generated in NAKDIMON_DEGRADED=1 mode (Pitfall 1: TF 2.15 SIGABRT on macOS arm64). "
            "nakdimon_model_hash carried forward from NAKDIMON_PIN.md "
            "(deterministic given pinned wheel). "
            "Re-run on Linux to refresh nakdimon_disagreement_rate."
        )
    else:
        result = _compute_full(GOLDEN_PRED)
        from oracles.nakdan_hybrid import ENDPOINT_URL
        from oracles.nakdimon_oss import MODEL_HASH as _model_hash

        nakdimon_rate = result["nakdimon_disagreement_rate"]
        d_rate = result["dicta_disagreement_rate"]
        nakdimon_lines_scored = result["audit"]["nakdimon_lines_scored"]
        dicta_lines_scored = result["audit"]["dicta_lines_scored"]
        dicta_failures = result["audit"]["dicta_failures"]
        model_hash = _model_hash
        resolved_ip = _resolve_ip(ENDPOINT_URL)
        regeneration_note = "Standard regeneration -- both oracles live."

    fixture = {
        "fixture_id": "golden_deut_6_4_5",
        "generated_at_iso": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "nakdimon_model_hash": model_hash,
        "nakdan_endpoint_resolved_ip": resolved_ip,
        "nakdimon_disagreement_rate": nakdimon_rate,
        "dicta_disagreement_rate": d_rate,
        "provenance": {
            "nakdimon_lines_scored": nakdimon_lines_scored,
            "dicta_lines_scored": dicta_lines_scored,
            "dicta_failures": dicta_failures,
            "scorer_pinned_version": "v0.1.0-scorer",
            "regeneration_command": (
                "RUN_LIVE_ORACLES=1 python oracles/scripts/regenerate_golden_oracle_cache.py"
            ),
            "regeneration_note": regeneration_note,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT}")
    print(f"  nakdimon_disagreement_rate = {fixture['nakdimon_disagreement_rate']}")
    print(f"  dicta_disagreement_rate    = {fixture['dicta_disagreement_rate']}")
    print(f"  resolved_ip                = {fixture['nakdan_endpoint_resolved_ip']}")
    print(f"  mode                       = {'degraded' if degraded else 'full'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
