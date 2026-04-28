## Summary

<!--
If this PR adds files under `results/llm_vision/` and main currently has none,
the PR title MUST start with `[YOSEF-REVIEW]` (Phase 03.1 A-03). The
check-yosef-review-gate job enforces this. Once one human-blessed BL-01
result exists in main, subsequent folio PRs auto-merge per CI green.
-->

## Test plan
- [ ] CI green (baseline-unit, baseline-replay, baseline-live (nightly), check-yosef-review-gate)
- [ ] (if first-of-kind BL-01) Yosef written approval recorded as PR review
- [ ] (if results/<bl>/<folio>.json added) D-15 bit-equality verified by test_expected_totals.py
