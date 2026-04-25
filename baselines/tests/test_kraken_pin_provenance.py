"""Provenance test: KRAKEN_PIN.md row matches the cached mlmodel + module constant.

Three layers:

1. ``test_pin_row_format_well_formed`` — KRAKEN_PIN.md exists and the latest dated
   row's sha256 column is exactly 64 hex chars (no ``<FILL_IN_…>`` placeholder).
2. ``test_cached_mlmodel_matches_pin`` — if the cached BiblIA_01.mlmodel exists
   locally, its sha256 equals the pin row's sha256. Skipped when the model is
   absent (the 250 MB download is gated to live runs / RUN_LIVE_BASELINES=1).
3. ``test_module_hash_constant_matches_pin`` — ``baselines._kraken.KRAKEN_MODEL_HASH``
   equals ``sha256(f"kraken=={KRAKEN_VERSION}:{pin_sha256}").hexdigest()[:16]``.
   Skipped when the model is absent because importing _kraken triggers the read.

Wave 3 plans (03-05/03-06/03-07) import ``KRAKEN_MODEL_HASH`` by name, so the
derived-hash contract is load-bearing across the phase.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PIN_MD = REPO_ROOT / "baselines" / "KRAKEN_PIN.md"
MODEL_PATH = REPO_ROOT / "baselines" / ".cache" / "kraken" / "BiblIA_01.mlmodel"
KRAKEN_VERSION = "7.0.1"


def _latest_row_sha256() -> str:
    """Parse KRAKEN_PIN.md, return the sha256 column from the latest dated row.

    Append-only, newest-first convention (see oracles/NAKDIMON_PIN.md for the
    template). Row format:

        | <YYYY-MM-DD> | <DOI> | <kraken-version> | <64-hex sha256> | <reason> |
    """
    text = PIN_MD.read_text(encoding="utf-8")
    rows = [r for r in text.splitlines() if r.startswith("| 2026-")]
    assert rows, "no dated row found in KRAKEN_PIN.md"
    latest = rows[0]
    cols = [c.strip() for c in latest.strip("|").split("|")]
    return cols[3]


def test_pin_row_format_well_formed():
    sha = _latest_row_sha256()
    assert re.fullmatch(r"[0-9a-f]{64}", sha), (
        f"sha256 not 64 hex chars: {sha!r} (placeholder not replaced?)"
    )


@pytest.mark.skipif(
    not MODEL_PATH.exists(),
    reason="model not fetched locally; covered by live test",
)
def test_cached_mlmodel_matches_pin():
    h = hashlib.sha256()
    with open(MODEL_PATH, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    actual = h.hexdigest()
    expected = _latest_row_sha256()
    assert actual == expected, f"local model sha256 {actual!r} != pin row {expected!r}"


@pytest.mark.skipif(
    not MODEL_PATH.exists(),
    reason="model not fetched locally; KRAKEN_MODEL_HASH still resolves but "
    "this test asserts the *derivation* matches the pin row, which only "
    "matters once we have the local model to verify against.",
)
def test_module_hash_constant_matches_pin():
    from baselines._kraken import KRAKEN_MODEL_HASH

    sha = _latest_row_sha256()
    seed = f"kraken=={KRAKEN_VERSION}:{sha}".encode()
    expected = hashlib.sha256(seed).hexdigest()[:16]
    assert KRAKEN_MODEL_HASH == expected
