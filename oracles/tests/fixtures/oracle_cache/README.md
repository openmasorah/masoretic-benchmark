# Cached oracle outputs

`golden_fixture_oracles.json` is committed to git. The ORA-06 contract test
(`oracles/tests/test_oracle_golden_fixture.py`) reads this file and compares
the scorer's bit-identical-everything-else output against it — **never**
hits live DICTA during PR-blocking CI.

## When to regenerate

- **Nakdimon re-pin** (D-09): the H5 weights or PyPI version changed →
  MODEL_HASH changes → cached `nakdimon_disagreement_rate` must be regenerated.
- **DICTA endpoint rotation** (Pitfall 2): the resolved IP shifts dramatically
  or the response payload schema changes → cached `dicta_disagreement_rate`
  may drift; regenerate after a manual smoke test confirms the new endpoint.
- **Scorer version bump**: `v0.1.0-scorer` advances → re-run the scorer
  with the new version to confirm tier1/3/4 + composite + confusion still
  match across both legs of the contract test.

## How to regenerate

Standard (Linux + Python 3.11 + nakdimon installed):

```bash
cd /Users/benlamm/Workspace/masoretic-benchmark
RUN_LIVE_ORACLES=1 python oracles/scripts/regenerate_golden_oracle_cache.py
git add oracles/tests/fixtures/oracle_cache/golden_fixture_oracles.json
git commit -m "chore(oracles): regenerate golden fixture oracle cache (<reason>)"
```

Degraded mode (macOS arm64, Pitfall 1 -- TF 2.15 SIGABRT on Nakdimon import):

```bash
RUN_LIVE_ORACLES=1 NAKDIMON_DEGRADED=1 .venv/bin/python oracles/scripts/regenerate_golden_oracle_cache.py
```

In degraded mode `nakdimon_disagreement_rate` is `null` and the contract
test must be re-run on a Linux host (Phase 2 Plan 06 CI image) to refresh
the Nakdimon column. `nakdimon_model_hash` is carried forward from
NAKDIMON_PIN.md (the pin is deterministic given the wheel + H5 sha,
recorded at 02-02 plan completion).

The regeneration MUST be a deliberate human commit (not an automatic CI
update). Drift between the cached values and live oracles is information,
not an error to be auto-papered-over (D-09 "document at bump").
