"""The consensus goldens are canonical GT. They must say so, and regenerate exactly.

`phase_0_manifest.json` computes each folio's `gt_hash` over these files, so two
properties are load-bearing:

1. **They must not describe themselves as provisional.** Hashing an artifact that
   says "never fused/promoted/pushed" as canonical ground truth freezes a
   self-contradiction into the manifest. (Trap T2.)
2. **Regeneration must be byte-exact.** A `gt_hash` is only meaningful if anyone
   can rebuild the bytes it was taken over. If the builder's output drifts, the
   digest silently stops verifying.

They also carry no `gt_hash` of their own: the manifest is the single source of
truth for that digest, and a file cannot contain the hash of itself.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "iaa_data" / "devarim_4folio" / "goldens"
BUILDER = GOLDEN_DIR / "build_verified_consensus_golden.py"
SOURCE = REPO_ROOT / "iaa_data" / "devarim_4folio" / "consensus_gold_positional.json"

FOLIOS = [
    "leningrad_devarim_F118B_fixture",
    "leningrad_devarim_F119A_fixture",
    "leningrad_devarim_F119B_fixture",
    "leningrad_devarim_F120A_fixture",
]


def _golden_path(folio: str) -> Path:
    return GOLDEN_DIR / f"{folio}.gt_adapter_golden.json"


def _load(folio: str) -> dict:
    return json.loads(_golden_path(folio).read_text(encoding="utf-8"))


def test_all_four_goldens_exist():
    missing = [f for f in FOLIOS if not _golden_path(f).exists()]
    assert not missing, f"missing consensus goldens: {missing}"


def test_goldens_do_not_live_under_results_provisional():
    """Canonical GT must not sit in a tree whose README disclaims it."""
    stale = REPO_ROOT / "results_provisional" / "verified_consensus"
    assert not stale.exists(), (
        "the goldens moved to iaa_data/devarim_4folio/goldens/; a copy under "
        "results_provisional/ would be a second, unhashed source of truth"
    )


@pytest.mark.parametrize("folio", FOLIOS)
def test_golden_does_not_declare_itself_provisional(folio):
    """Trap T2: gt_hash must not be taken over an artifact that denies being GT."""
    golden = _load(folio)
    assert golden["provisional"] is False
    assert golden["single_annotator"] is False
    assert golden["pre_adjudication"] is False

    status = golden["_provenance"]["iaa_status"]
    assert "never fused" not in status
    assert "canonical ground truth" in status


@pytest.mark.parametrize("folio", FOLIOS)
def test_golden_carries_no_self_referential_gt_hash(folio):
    """A file cannot contain the hash of itself; the manifest is the SSOT."""
    golden = _load(folio)
    assert "gt_hash" not in golden
    assert "gt_hash" not in golden["_provenance"]


@pytest.mark.parametrize("folio", FOLIOS)
def test_golden_points_at_its_source(folio):
    prov = _load(folio)["_provenance"]
    assert "consensus_gold_positional.json" in prov["source"]
    assert "Ginsberg" in prov["annotators"] and "Moster" in prov["annotators"]
    assert _load(folio)["license"] == "CC-BY-4.0"


def test_goldens_regenerate_byte_identically():
    """gt_hash is only meaningful if the bytes it covers can be rebuilt exactly."""
    before = {f: _golden_path(f).read_bytes() for f in FOLIOS}

    proc = subprocess.run(
        [sys.executable, str(BUILDER)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    try:
        assert proc.returncode == 0, proc.stderr

        drifted = [f for f in FOLIOS if _golden_path(f).read_bytes() != before[f]]
        assert not drifted, (
            f"builder output drifted for {drifted}; any committed gt_hash over these "
            "bytes would stop verifying"
        )
    finally:
        # Restore regardless, so a drifting builder cannot leave the tree dirty.
        for folio, payload in before.items():
            _golden_path(folio).write_bytes(payload)


def test_source_artifact_is_the_paper_pinned_consensus():
    """The goldens are a projection. The paper pins the source, not the projection."""
    assert SOURCE.exists()
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert "2026-06-19" in json.dumps(src.get("source", ""))
