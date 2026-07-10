# Manifest Schema Changelog

Append-only. Every change to `schemas/phase_0_manifest.schema.json` writes a NEW row above the previous one (newest first). Schema-bump discipline: D-09 carry-forward (Phase 2) — document at bump.

| Date       | From | To   | Reason                                                                                                                              |
|------------|------|------|-------------------------------------------------------------------------------------------------------------------------------------|
| 2026-07-10 | v0.2 | v0.2 | Additive, non-breaking (B4). Declare optional per-folio `gt_source` — the provenance pointer for `gt_hash`. Folio items were already `additionalProperties: true`, so the field validated silently and untyped; this documents and types it. NOT top-level: the root object is `additionalProperties: false`, so a top-level `gt_source` hard-fails `Manifest.load` and breaks the scorer CLI. `$id` intentionally unchanged (no consumer contract is broken). |
| 2026-04-25 | v0.1 | v0.2 | Phase 3 BASELINES launch (A-1). Add iaa_subset, baselines_seeded, expected_reports_per_baseline; expand expected_total_reports to per-baseline mapping; nakdimon_model_hash promoted from optional/null to required string. |
