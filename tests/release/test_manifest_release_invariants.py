"""REL-05: phase_0_manifest.json release invariants.

Producer: Plan 04-08 (v0.1.0 manifest fuse event).
- gt_hash populated for all 3 frozen folios
- scorer_version aligns with masoretic_eval.__version__
- nakdimon_model_hash non-empty
"""

import pytest


@pytest.mark.xfail(strict=True, reason="v0.1.0 manifest fuse not yet shipped (04-08 W3)")
def test_three_frozen_folios_all_have_gt_hash():
    raise NotImplementedError("Wave-3 producer: three gt_hash values")


@pytest.mark.xfail(strict=True, reason="v0.1.0 manifest fuse not yet shipped (04-08 W3)")
def test_scorer_version_matches_masoretic_eval_dunder_version():
    raise NotImplementedError(
        "Wave-3 producer: fuse aligns scorer_version with masoretic_eval.__version__ per Pitfall 7"
    )


@pytest.mark.xfail(strict=True, reason="manifest hash verification pending")
def test_nakdimon_model_hash_nonempty():
    raise NotImplementedError("Wave-3 producer: manifest fuse asserts non-null nakdimon_model_hash")
