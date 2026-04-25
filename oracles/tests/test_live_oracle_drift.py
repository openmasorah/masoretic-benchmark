"""Live-oracle drift detector — runs nightly via the oracle-live CI job.

Compares fresh live oracle outputs against the committed
oracles/tests/fixtures/oracle_cache/golden_fixture_oracles.json. Drift
means a re-pin happened without a corresponding NAKDIMON_PIN.md entry +
fixture regeneration commit (D-09 "document at bump").

NOT run on PR merges — these tests block only the nightly cron job, which
surfaces drift via a status badge / email. Humans regenerate the cache
deliberately; CI never auto-updates the cache.

Path resolution: this file lives at oracles/tests/test_live_oracle_drift.py;
parents[0]=tests, parents[1]=oracles, parents[2]=repo root. (The 02-05 regen
script noted the same off-by-one in the plan's prescribed formula.)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]  # masoretic-benchmark/
GOLDEN_PRED = REPO_ROOT / "tests" / "fixtures" / "golden" / "prediction.json"
ORACLE_CACHE = Path(__file__).parent / "fixtures" / "oracle_cache" / "golden_fixture_oracles.json"

REGEN_HINT = (
    "RUN_LIVE_ORACLES=1 python oracles/scripts/regenerate_golden_oracle_cache.py "
    "&& git commit oracles/tests/fixtures/oracle_cache/golden_fixture_oracles.json "
    "-m 'chore(oracles): regenerate golden fixture oracle cache (<reason>)'"
)


@pytest.fixture(scope="module")
def cached() -> dict:
    return json.loads(ORACLE_CACHE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def live() -> dict:
    from oracles.compute_oracles import compute_oracle_rates

    return compute_oracle_rates(GOLDEN_PRED, with_dicta=True)


@pytest.mark.live_oracles
def test_nakdimon_model_hash_matches_cache(cached):
    from oracles.nakdimon_oss import MODEL_HASH

    cached_hash = cached["nakdimon_model_hash"]
    if MODEL_HASH != cached_hash:
        pytest.fail(
            f"Nakdimon MODEL_HASH drift: live={MODEL_HASH!r} cached={cached_hash!r}. "
            f"Re-pin must update NAKDIMON_PIN.md AND regenerate the fixture cache. "
            f"Regenerate: {REGEN_HINT}"
        )


@pytest.mark.live_oracles
def test_nakdimon_drift_against_cache(cached, live):
    cached_rate = cached["nakdimon_disagreement_rate"]
    live_rate = live["nakdimon_disagreement_rate"]

    # Degraded-mode tolerance (Pitfall 1 — 02-05 regenerated cache on macOS arm64
    # without TF, so the cached nakdimon_disagreement_rate is null. The first
    # nightly oracle-live run on Linux+Py3.11 will observe a real float; rather
    # than failing, surface this as actionable info so the human re-pins the
    # cache deliberately per D-09.
    if cached_rate is None and live_rate is not None:
        pytest.fail(
            f"Nakdimon column recovered: cached=None live={live_rate}. The cache "
            f"was regenerated in NAKDIMON_DEGRADED=1 mode (Pitfall 1). Now that "
            f"the live run produced a real value, regenerate the cache to commit "
            f"the recovered baseline. Regenerate: {REGEN_HINT}"
        )
    if cached_rate is None and live_rate is None:
        pytest.skip(
            "Nakdimon unavailable in both cache and live — no drift signal "
            "(Pitfall 1: TF 2.15 incompat persists)"
        )
    if cached_rate is not None and live_rate is None:
        pytest.skip(
            "Nakdimon unavailable in this run but cache has a value — drift "
            "cannot be evaluated this cycle"
        )

    delta = abs(live_rate - cached_rate)
    if delta >= 1e-9:
        pytest.fail(
            f"Nakdimon disagreement_rate drift: live={live_rate} cached={cached_rate} "
            f"|delta|={delta} (Nakdimon is deterministic; ANY drift means a re-pin). "
            f"Regenerate: {REGEN_HINT}"
        )


@pytest.mark.live_oracles
def test_dicta_drift_against_cache_or_unavailable(cached, live):
    cached_rate = cached["dicta_disagreement_rate"]
    live_rate = live["dicta_disagreement_rate"]
    # Both None: endpoint stayed down, no drift information
    if cached_rate is None and live_rate is None:
        pytest.skip("DICTA endpoint unavailable in both cache and live — no drift signal")
    # Cached None, live present: endpoint recovered (informational)
    if cached_rate is None and live_rate is not None:
        pytest.fail(
            f"DICTA endpoint recovered: cached=None live={live_rate}. Consider regenerating "
            f"the cache to capture the recovered baseline. Regenerate: {REGEN_HINT}"
        )
    # Cached present, live None: endpoint flapped (transient)
    if cached_rate is not None and live_rate is None:
        pytest.skip("DICTA endpoint unreachable in this run — drift cannot be evaluated")
    # Both present: tolerant comparison
    delta = abs(live_rate - cached_rate)
    if delta > 0.05:
        pytest.fail(
            f"DICTA disagreement_rate drift exceeds 0.05 tolerance: live={live_rate} "
            f"cached={cached_rate} |delta|={delta}. May be endpoint rotation (Pitfall 2) "
            f"or genuine model change. Investigate, then regenerate: {REGEN_HINT}"
        )
