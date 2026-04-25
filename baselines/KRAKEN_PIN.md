# Kraken Pin Log

Append-only. Every change to the pinned BiblIA Kraken model writes a new row
here with date + reason (D-03 / Phase 2 D-09 carry-forward). Newest first.

| Date | Zenodo DOI | kraken version | BiblIA_01.mlmodel sha256 | Reason |
|---|---|---|---|---|
| 2026-04-25 | 10.5281/zenodo.5468286 | 7.0.1 | bb48c481d8c46b41465920482e253dc990163405c584d24700cfb0d9b4ca9147 | Initial pin (Phase 3 BL-02 launch). |

- 2026-04-25 — Network re-verified: Zenodo download sha256 matches pin. Verified by: housekeeping pass (Tier 1 #3).

## Derived kraken_model_hash

`oracles._hashing`-style derivation for the 2026-04-25 row:

    sha256(f"kraken==7.0.1:bb48c481d8c46b41465920482e253dc990163405c584d24700cfb0d9b4ca9147").hexdigest()[:16]
    = 8514a0c7cc2b5b45

Every leaderboard row and every `run_meta.pins.kraken_model_hash` field for
runs using this pin will carry this exact 16-char digest. A new pin row
below implies a new derived hash.

## Notes

- **Pin formula** mirrors `oracles._hashing.compute_nakdimon_model_hash`:
  `sha256(f"kraken=={version}:{mlmodel_sha256}").hexdigest()[:16]`. Computed
  by `baselines/scripts/fetch_biblia_kraken_model.py::compute_kraken_model_hash`
  and re-derived at module import time in `baselines/_kraken.py` so the
  `KRAKEN_MODEL_HASH` constant stays canonical-from-the-pin.
- **DOI distinction**: `10.5281/zenodo.5468286` is the MODEL DOI (the
  `BiblIA_01.mlmodel` artifact). The Phase 1 dry-run stub at
  `gt-infra/gt_infra/dry_run/biblia_kraken_stub.py` (in baalshem) uses
  `10.5281/zenodo.5167263` which is the DATASET DOI (the BiblIA paper's
  training corpus, NOT the model file). Production code uses the model
  DOI; the Phase 1 stub stays unchanged in baalshem as a dry-run artifact.
- **Direct download URL** (`https://zenodo.org/records/5468286/files/BiblIA_01.mlmodel`)
  is recorded in `baselines/scripts/fetch_biblia_kraken_model.py::DOWNLOAD_URL`.
  If Zenodo changes URL structure, fix the script in the SAME commit that
  appends a new row to this file (D-09 carry-forward — document at bump).
- **Cache location**: `baselines/.cache/kraken/BiblIA_01.mlmodel` (gitignored).
  Model file is ~16 MB; never committed to git. CI strategy: mocked unit
  tests (default tier) require no model; live tests (`@pytest.mark.live_kraken`,
  gated by `RUN_LIVE_BASELINES=1`) fetch via the script. Plan 03-08 will wire
  CI cache keyed on this `kraken_model_hash` for the `baseline-replay` tier.
- **Idempotency contract**: `fetch_biblia_kraken_model.py` skips the download
  when the cache file exists AND its sha256 matches the pin row. Drift
  (cache present but sha256 mismatch) exits non-zero with a stderr
  explanation; never silently re-downloads.
