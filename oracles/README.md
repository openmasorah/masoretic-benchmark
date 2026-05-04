# masoretic-oracles

Hebrew diacritization oracles for the Masoretic benchmark scorer. Three oracle
modules populate the scorer's pass-through tier-2 fields without modifying the
scorer itself:

- `oracles.nakdimon_oss` — primary, MIT, reproducibly pinned (Nakdimon code
  version + bundled Keras H5 weights → short MODEL_HASH).
- `oracles.nakdan_hybrid` — secondary, DICTA 2020 hybrid Nakdan API
  (`genre=rabbinic`), 1 QPS throttle. Marked as a non-reproducible source
  in the pin log because, at the time of evaluation, the public endpoint
  did not expose a version header sufficient to pin a specific model
  release; a daily-rotated audit log preserves the exact responses we used.
- `oracles.dictabert` — off-label `dictabert-large-char-menaked` for the
  publishable negative-result baseline (Baseline 4) only.

## Off-label disclaimer

`dictabert-large-char-menaked` is trained on modern Hebrew and is off-label for pre-modern Tiberian text. Used here only as a publishable negative-result baseline (Baseline 4). Do not interpret outputs as oracle-grade diacritization.

## Install

From the sibling repo root:

```bash
pip install -e ./oracles[all]
```

Optional extras instead of `[all]`:

- `[nakdimon]` — adds `nakdimon==0.1.2` (Keras + TensorFlow). Required for the
  primary oracle.
- `[dictabert]` — adds `transformers`, `torch`, `safetensors` for the off-label
  baseline.
- `[dicta]` — no extra deps (core install already covers `requests` +
  `tenacity`); listed for symmetry.
- `[dev]` — `pytest`, `pytest-mock`.

`masoretic-eval >= 0.1.0,<0.2` is a hard dependency. The scorer must be
installed (editable or wheel) before installing this package.

## Modules

| Module                | Purpose                                                          |
|-----------------------|------------------------------------------------------------------|
| `oracles.nakdimon_oss`| Primary reproducible oracle (MIT, pinned by MODEL_HASH).         |
| `oracles.nakdan_hybrid`| DICTA hybrid Nakdan client; 1-QPS throttle + JSONL audit log.   |
| `oracles.dictabert`   | Off-label char-menaked inference for Baseline 4 (Phase 3) only.  |
| `oracles.compute_oracles` | Composite orchestrator: returns both rates ready for scorer CLI. |

## Audit log

DICTA calls are recorded to a daily-rotated JSONL audit log at
`oracles/audit/dicta_<YYYY-MM-DD>.jsonl`. The directory is gitignored — audit
data is provenance only and is referenced from leaderboard rows by back-pointer
(`audit/dicta_<date>.jsonl#L<N>`), never redistributed publicly. See D-15
through D-18 in `.planning/phases/02-oracles/02-CONTEXT.md`.

## CI

Two GitHub Actions jobs cover the oracles package (defined in
`.github/workflows/ci.yml`):

| Job           | Trigger                                                 | Blocks merge?               | What it does                                                                                                                                                                                          |
| ------------- | ------------------------------------------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `oracle-unit` | every PR + push to `main` (after `test` job)            | YES                         | Runs `pytest oracles/tests/ -m "not live_oracles"` on Python 3.11 + 3.12. Includes the ORA-06 bit-identical contract test (`test_oracle_golden_fixture.py`). All live oracle calls are mocked.        |
| `oracle-live` | nightly cron `0 6 * * *` UTC + manual `workflow_dispatch` | NO (`continue-on-error: true`) | Runs `RUN_LIVE_ORACLES=1 pytest oracles/tests/ -m "live_oracles"` on Python 3.11. Surfaces fresh drift via `test_live_oracle_drift.py` against the committed golden cache.                            |

### Drift handling (D-09 "document at bump")

When `oracle-live` fails, a human investigates. Drift means one of:

1. **Nakdimon was re-pinned without updating `NAKDIMON_PIN.md`** + regenerating the
   golden fixture cache. Fix: re-pin properly per D-09 (update `NAKDIMON_PIN.md`,
   then regenerate the cache).
2. **DICTA endpoint rotated** (Pitfall 2) and the response payload shifted. Fix:
   re-verify endpoint URL, regenerate cache, update
   `tactical_dicta_nakdan_access.md`.

CI **never** auto-updates the cache. Cache regeneration is always a deliberate
human commit.

Regenerate command:

```bash
RUN_LIVE_ORACLES=1 python oracles/scripts/regenerate_golden_oracle_cache.py
git commit oracles/tests/fixtures/oracle_cache/golden_fixture_oracles.json \
    -m "chore(oracles): regenerate golden fixture oracle cache (<reason>)"
```

### Pitfall 1 hedge (TF 2.15 + Python 3.12)

`pip install -e "./oracles[nakdimon]"` is best-effort on Python 3.12 (TensorFlow
2.15 has no Python 3.12 wheel). The `oracle-unit` job warns and continues;
mocked unit tests cover Nakdimon paths regardless. The `oracle-live` job runs
only on Python 3.11 where Nakdimon installs cleanly.

The 02-05 cached fixture currently has `nakdimon_disagreement_rate=null`
because regeneration ran in `NAKDIMON_DEGRADED=1` mode on macOS arm64 (TF 2.15
SIGABRT). The first nightly `oracle-live` run on Linux+Py3.11 will surface the
real value via `test_nakdimon_drift_against_cache` (which fails with an
"endpoint recovered" message), at which point a human regenerates the cache to
commit the recovered baseline.

### Pitfall 8 carry-forward

Phase 1's GT-12 IAA gate is NOT run by sibling CI — the sibling repo must be
independently verifiable by anyone (no openmesorah dependency). IAA gates live in
openmesorah only.

## License

Apache-2.0 (matches the sibling scorer repo's blanket license).
