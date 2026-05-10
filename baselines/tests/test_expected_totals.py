"""D-15 declarations test: manifest declares expected_reports_per_baseline.

Asserts that for EVERY known Phase 3 baseline_id, the live openmasorah manifest
has the key present in `expected_reports_per_baseline`.

Per Plan 03-01 Task 3, the v0.2 manifest emission populates
`expected_reports_per_baseline` with all four baseline keys mapped to `1`
(one entry per frozen Leningrad folio). This test PASSES against that
manifest. There is NO early-return / legacy-compat branch — that branch
would make the test a no-op under Plan 03-01's manifest and contradict
must_have line 49 of plan 03-08.

Per A-1 precedence rule, the per-baseline mapping is canonical for v0.2;
the legacy scalar `expected_total_reports` is preserved for v0.1 readers
but is NOT consulted by this assertion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

OPENMESORAH_MANIFEST = Path(__file__).resolve().parents[2] / "phase_0_manifest.json"
KNOWN_BASELINE_IDS = (
    "llm_vision",
    "biblia_kraken",
    "biblia_nakdimon",
    "biblia_char_menaked",
)


@pytest.mark.skipif(
    not OPENMESORAH_MANIFEST.exists(),
    reason="openmasorah manifest not present in this CI sandbox",
)
def test_manifest_declares_expected_reports_per_baseline_for_every_baseline_id():
    m = json.loads(OPENMESORAH_MANIFEST.read_text(encoding="utf-8"))
    per_baseline = m.get("expected_reports_per_baseline")
    assert per_baseline is not None, (
        "D-15: manifest is missing the `expected_reports_per_baseline` field entirely. "
        "Plan 03-01 Task 3 must emit it as a populated mapping (not absent, not empty)."
    )
    assert isinstance(per_baseline, dict), (
        f"D-15: `expected_reports_per_baseline` must be an object, got "
        f"{type(per_baseline).__name__}"
    )
    missing = [bid for bid in KNOWN_BASELINE_IDS if bid not in per_baseline]
    assert not missing, (
        f"D-15 declarations gap: manifest's `expected_reports_per_baseline` is missing keys "
        f"for baseline(s): {missing!r}. Plan 03-01 Task 3 MUST populate ALL four baseline_ids "
        f"({list(KNOWN_BASELINE_IDS)!r}) at v0.2 emission. Each value is a non-negative integer "
        f"(zero is allowed before that baseline has run; key presence is the gate)."
    )
    # Each value must be a non-negative integer (schema enforces, but assert
    # here too for a clearer failure than a downstream JSON-schema validation
    # error).
    bad_values = {
        bid: per_baseline[bid]
        for bid in KNOWN_BASELINE_IDS
        if not isinstance(per_baseline[bid], int) or per_baseline[bid] < 0
    }
    assert not bad_values, (
        f"D-15: `expected_reports_per_baseline` values must be non-negative integers; "
        f"offending entries: {bad_values!r}"
    )


def test_results_dir_count_equals_manifest_expected_reports():
    """A-01 D-14 amendment: len(results/<bl>/) must equal
    manifest.expected_reports_per_baseline[<bl>] after every promotion.
    Checked on EVERY CI invocation (not just at end-of-run).

    Path resolution per BLOCKER-2 (post-revision):
      Path(__file__) = .../baselines/tests/test_expected_totals.py
      parents[0]     = baselines/tests/
      parents[1]     = baselines/
      parents[2]     = masoretic-benchmark/   <-- sibling repo root
    Matches the convention pinned in test_invariants.py:33.
    """
    SIBLING_RESULTS = Path(__file__).resolve().parents[2] / "results"
    if not SIBLING_RESULTS.exists():
        pytest.skip("results/ tree not yet seeded (Phase 03.1 W4/W5 in progress)")

    if not OPENMESORAH_MANIFEST.exists():
        pytest.skip("openmasorah manifest not present (running outside expected layout)")

    m = json.loads(OPENMESORAH_MANIFEST.read_text(encoding="utf-8"))
    per_baseline = m["expected_reports_per_baseline"]
    for bid, expected in per_baseline.items():
        bl_dir = SIBLING_RESULTS / bid
        if not bl_dir.exists():
            assert expected == 0, f"{bid}: manifest expects {expected} but results/{bid}/ missing"
            continue
        actual = sum(1 for p in bl_dir.glob("*.json") if p.name != "run_meta.json")
        assert actual == expected, (
            f"D-15 (A-01-amended) bit-equality: results/{bid}/ has {actual} "
            f"files, manifest expects {expected}"
        )


@pytest.mark.skipif(
    not OPENMESORAH_MANIFEST.exists(),
    reason="openmasorah manifest not present in this CI sandbox",
)
def test_manifest_version_is_v02():
    """Companion check: the manifest's schema version is v0.2.0 — only the
    v0.2 schema declares `expected_reports_per_baseline` as the canonical
    counter. A v0.1 manifest would still be load-coerced by Manifest.load()
    but would lack the per-baseline mapping in canonical form."""
    m = json.loads(OPENMESORAH_MANIFEST.read_text(encoding="utf-8"))
    version = m.get("version", "")
    assert version.startswith("v0.2"), (
        f"D-15 expects v0.2 manifest with per-baseline mapping; manifest version is {version!r}"
    )
