"""REL-05: phase_0_manifest.json release invariants.

These three assertions were placeholders (`raise NotImplementedError` under
`@pytest.mark.xfail(strict=True)`) from Plan 04-08 until the v0.1 `gt_hash` fuse
landed. That construction is worth naming, because it reports green in both
directions: a strict xfail passes precisely when its body fails, so a stub that
asserts nothing and a real assertion that is false look identical. The markers
are removed rather than flipped -- an invariant that only holds while
unimplemented is not an invariant.

The original docstring said "all 3 frozen folios". There are four (F118B, F119A,
F119B, F120A), so these iterate over `in_frozen_scope` rather than trust a count.
"""

from __future__ import annotations

import json
from pathlib import Path

import masoretic_eval

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "phase_0_manifest.json"

GT_HASH_LEN = 16
HEX = set("0123456789abcdef")


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _frozen_folios() -> list[dict]:
    return [f for f in _manifest()["folios"] if f.get("in_frozen_scope")]


def test_every_frozen_folio_has_a_gt_hash():
    """A frozen folio with no digest pins no ground truth."""
    frozen = _frozen_folios()
    assert frozen, "no folios are in frozen scope; the manifest pins nothing"

    unfused = [f["id"] for f in frozen if f.get("gt_hash") is None]
    assert not unfused, f"frozen folios carry no gt_hash: {unfused}"

    for folio in frozen:
        gt_hash = folio["gt_hash"]
        # sha256[:16] -- the repo's pin convention, shared with manifest_hash,
        # kraken_model_hash and nakdimon_model_hash. Asserted explicitly: a full
        # 64-char SHA-256 here would reintroduce the "SHA-256 pinned" overclaim
        # the paper had to retract.
        assert len(gt_hash) == GT_HASH_LEN, f"{folio['id']}: gt_hash is not sha256[:16]"
        assert set(gt_hash) <= HEX, f"{folio['id']}: gt_hash is not lowercase hex"

        # A digest with no stated source is not provenance.
        assert folio.get("gt_source"), f"{folio['id']}: gt_hash set but gt_source missing"


def test_scorer_version_matches_masoretic_eval_dunder_version():
    """Pitfall 7: the manifest's scorer_version went stale against the package.

    It is not an inert label. `baselines/src/baselines/_base.py` cascades it into
    every emitted `run_meta.json`, so a stale manifest field writes a false
    scorer version into each promoted artifact.
    """
    assert _manifest()["scorer_version"] == masoretic_eval.__version__


def test_nakdimon_model_hash_nonempty():
    """Nakdimon OSS is the primary oracle. An unpinned oracle is not reproducible."""
    nakdimon_model_hash = _manifest()["nakdimon_model_hash"]
    assert isinstance(nakdimon_model_hash, str)
    assert nakdimon_model_hash.strip(), "nakdimon_model_hash is empty"
