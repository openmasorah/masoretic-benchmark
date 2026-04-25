# Nakdimon Pin Log

Append-only. Every change to the pinned Nakdimon version writes a new row here with date + reason (D-09).

| Date       | pip install | wheel sha256 (file)                                                | Bundled H5 sha256                                                  | Upstream git SHA (provenance only)                                 | Reason                          |
|------------|-------------|---------------------------------------------------------------------|---------------------------------------------------------------------|---------------------------------------------------------------------|---------------------------------|
| 2026-04-24 | nakdimon==0.1.2 | bc5f7220d468307a0d3b88db61f76b92dc4ee283c56ebebb4138613d183aa0e8 | 5f693887187aa45f6155171d4847c3a5e3b31a01528153d82ae50ab64e3b42b1 | e50a6efecdaa7725593f8594913e590de22696c0 | Initial pin (Phase 2 launch).  |

## Derived MODEL_HASH

`oracles.nakdimon_oss.MODEL_HASH` for the 2026-04-24 row:

    8fd7722b8002a690

Computed by `oracles._hashing.compute_nakdimon_model_hash()` as:

    sha256(f"nakdimon==0.1.2:{H5_SHA256}").hexdigest()[:16]
    = sha256("nakdimon==0.1.2:5f693887187aa45f6155171d4847c3a5e3b31a01528153d82ae50ab64e3b42b1").hexdigest()[:16]
    = 8fd7722b8002a690

Every leaderboard row (ORA-05) and every `nakdimon_model_hash` field in the manifest
(D-08) for runs using this pin will carry this exact 16-char digest. A new pin row
below implies a new digest.

## Notes

- **Pin format (RESEARCH delta #2)**: D-08's original `sha256(code_sha + ":" + weights_revision_sha + ":" + sorted(weights_files_sha256))[:16]` was simplified because the PyPI wheel bundles weights — there is no separate HuggingFace revision SHA. Adopted form: `sha256(f"nakdimon==<version>:" + sha256(Nakdimon.h5))[:16]` (implemented in `oracles._hashing.compute_nakdimon_model_hash`).
- **Upstream git SHA `e50a6efecdaa…`** is recorded for paper provenance only; the install line is `nakdimon==0.1.2` (PyPI), not `git+https://...@<sha>` (CONTEXT.md D-06 revised per RESEARCH delta #1).
- **Python version (Pitfall 1)**: `nakdimon==0.1.2` depends on `tensorflow==2.15.0`, which has no wheel for Python ≥ 3.12 on macOS arm64 (verified 2026-04-24 — pip reports `tensorflow==2.15.0` not-available, offers 2.16+ only). The Nakdimon path is pinned to **Python 3.11** for the duration of Phase 2. Other phases of the pipeline (scorer, GT infra) remain on Python 3.12/3.14 as each uses.
