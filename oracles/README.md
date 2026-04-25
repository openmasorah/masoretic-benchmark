# masoretic-oracles

Hebrew diacritization oracles for the Masoretic benchmark scorer. Three oracle
modules populate the scorer's pass-through tier-2 fields without modifying the
scorer itself:

- `oracles.nakdimon_oss` — primary, MIT, reproducibly pinned (Nakdimon code
  version + bundled Keras H5 weights → short MODEL_HASH).
- `oracles.nakdan_hybrid` — secondary, DICTA 2020 hybrid Nakdan API
  (`genre=rabbinic`), 1 QPS throttle, labeled "not reproducible (rotating
  endpoint, no version header)".
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

## License

Apache-2.0 (matches the sibling scorer repo's blanket license).
