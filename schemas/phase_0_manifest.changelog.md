# Manifest Schema Changelog

Append-only. Every change to `schemas/phase_0_manifest.schema.json` writes a NEW row above the previous one (newest first). Schema-bump discipline: D-09 carry-forward (Phase 2) — document at bump.

| Date       | From | To   | Reason                                                                                                                              |
|------------|------|------|-------------------------------------------------------------------------------------------------------------------------------------|
| 2026-04-25 | v0.1 | v0.2 | Phase 3 BASELINES launch (A-1). Add iaa_subset, baselines_seeded, expected_reports_per_baseline; expand expected_total_reports to per-baseline mapping; nakdimon_model_hash promoted from optional/null to required string. |
