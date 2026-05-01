"""BL-04 live test against real DictaBERT char-menaked model.

Gated by RUN_LIVE_BASELINES=1 (live_baselines marker via conftest.py).

Phase 2 Pitfall (carry-forward): DictaBERT char-menaked requires
`transformers>=4.44,<6` + `torch`. CPU is fine for one-folio inference
(slow, ~30-60s cold load + per-line predictions). HF cache lives at
`oracles/.cache/dictabert/` per Phase 2 D-28; BL-04 reuses that cache
(no new download).

Issue 2 fix (option b — carry-forward from plan 03-05): The diagnostic
chain depends on a Phase 1 line-level GT export (`{lines:[{line_id,bbox,
tier1}]}` per folio). As of Phase 3 landing, Phase 1 produced ONLY a
single-text-blob golden fixture at `tests/fixtures/golden/gt.json` (no
per-line bboxes). The whole live test therefore SKIPS until that export
is supplied with BAALSHEM_GT_EXPORT_JSON. The realistic-chain mocked test
in `test_baseline_unit_char_menaked_chain.py` exercises the realistic-chain
code path under unit tests; this live test only adds value once a real
per-line GT is available.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

GT_EXPORT_PATH_ENV = "BAALSHEM_GT_EXPORT_JSON"


@pytest.mark.live_baselines
def test_live_char_menaked_chain_realistic_only(tmp_path):
    # TODO(phase-1-gt-export): unblock the diagnostic-chain assertion below
    # when Phase 1 emits a per-line GT export
    # {lines:[{line_id,bbox,tier1}]} for the Shema fixture. As of Phase 3
    # landing, Phase 1 has only a single-text-blob fixture
    # (tests/fixtures/golden/gt.json) lacking per-line bboxes (D-30/D-31).
    gt_path = os.environ.get(GT_EXPORT_PATH_ENV)
    if not gt_path:
        pytest.skip(f"set {GT_EXPORT_PATH_ENV} to run live diagnostic-chain fixture")
    if not Path(gt_path).exists():
        pytest.skip(f"{GT_EXPORT_PATH_ENV} does not exist: {gt_path}")

    # If the GT lands, this test exercises the real DictaBERT model on the
    # cached image. The realistic chain validates against
    # baseline_prediction.schema.json automatically via SandboxRun.
    from baselines.biblia_char_menaked import BibliaCharMenakedBaseline  # noqa: F401

    # Real-run skeleton (filled in by future plan when GT lands):
    #   manifest_path = ...  # phase_0_manifest.json (real)
    #   bl = BibliaCharMenakedBaseline(manifest_path, tmp_path / "results")
    #   rc = bl.run(folio_ids=["leningrad_devarim_F118B_fixture"])
    #   assert rc == 0
    #   pred = json.loads((tmp_path / "results" / "biblia_char_menaked" /
    #                      "leningrad_devarim_F118B_fixture.json").read_text())
    #   assert pred["baseline_id"] == "biblia_char_menaked"
    pytest.skip("GT fixture present — but live-run scaffold deferred to a future plan")
