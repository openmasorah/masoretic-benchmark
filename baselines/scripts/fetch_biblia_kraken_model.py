"""Fetch BiblIA_01.mlmodel from Zenodo (DOI 10.5281/zenodo.5468286).

Idempotent: caches under ``baselines/.cache/kraken/BiblIA_01.mlmodel``.
On every run, prints the sha256 of the cached file plus the derived
``kraken_model_hash`` (the 16-char digest stamped into every BL-02 run's
``run_meta.pins.kraken_model_hash``).

Skip-if-cached-and-matches behavior:
    - If the cache is empty, download.
    - If the cache file exists AND its sha256 matches the pin row in
      ``baselines/KRAKEN_PIN.md``, skip the download (true idempotency —
      do NOT re-fetch on re-runs).
    - If the cache file exists but its sha256 does NOT match the pin,
      fail loudly (drift = a problem to investigate, not silently fix).

Pin formula mirrors ``oracles._hashing.compute_nakdimon_model_hash``:

    kraken_model_hash = sha256(f"kraken=={version}:{mlmodel_sha256}").hexdigest()[:16]

NOTE on DOIs: ``10.5281/zenodo.5468286`` is the MODEL DOI. The Phase 1
stub at ``gt-infra/gt_infra/dry_run/biblia_kraken_stub.py`` (in baalshem)
uses ``10.5281/zenodo.5167263`` which is the DATASET DOI (the BiblIA
paper's training corpus, NOT the model file). Production code uses the
model DOI; the stub stays in baalshem as a Phase 1 dry-run artifact.
"""

from __future__ import annotations

import hashlib
import re
import sys
import urllib.request
from pathlib import Path

ZENODO_DOI = "10.5281/zenodo.5468286"
# Direct download URL for the model file. Verified 2026-04-25; if Zenodo
# changes URL structure, update this constant AND add a new row to
# baselines/KRAKEN_PIN.md in the same commit (D-09 carry-forward).
DOWNLOAD_URL = "https://zenodo.org/records/5468286/files/BiblIA_01.mlmodel"
KRAKEN_VERSION = "7.0.1"

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "baselines" / ".cache" / "kraken"
MODEL_PATH = CACHE_DIR / "BiblIA_01.mlmodel"
PIN_MD = REPO_ROOT / "baselines" / "KRAKEN_PIN.md"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_kraken_model_hash(version: str, mlmodel_sha256: str) -> str:
    """Mirror oracles._hashing.compute_nakdimon_model_hash shape."""
    seed = f"kraken=={version}:{mlmodel_sha256}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:16]


def _read_pinned_sha256() -> str | None:
    """Return the pinned sha256 from KRAKEN_PIN.md, or None if the pin file
    doesn't exist or has only placeholder rows.

    Tolerant of a freshly-authored pin (placeholder ``<FILL_IN_…>``) so the
    very first fetch can populate the placeholder; subsequent runs assert
    cache vs. pin.
    """
    if not PIN_MD.exists():
        return None
    text = PIN_MD.read_text(encoding="utf-8")
    rows = [r for r in text.splitlines() if r.startswith("| 2026-")]
    if not rows:
        return None
    cols = [c.strip() for c in rows[0].strip("|").split("|")]
    if len(cols) < 4:
        return None
    sha = cols[3]
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        return None
    return sha


def main() -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pinned_sha = _read_pinned_sha256()

    if MODEL_PATH.exists():
        cached_sha = _sha256_file(MODEL_PATH)
        if pinned_sha is not None and cached_sha != pinned_sha:
            print(
                f"ERROR: cached BiblIA_01.mlmodel sha256 {cached_sha!r} "
                f"does NOT match KRAKEN_PIN.md pinned value {pinned_sha!r}. "
                f"Cache may be corrupt or the upstream Zenodo file was "
                f"replaced. Investigate before proceeding; do NOT silently "
                f"re-download.",
                file=sys.stderr,
            )
            return 2
        print(
            f"BiblIA_01.mlmodel already cached at {MODEL_PATH} "
            f"(skip download).",
            file=sys.stderr,
        )
    else:
        print(f"Downloading {DOWNLOAD_URL} -> {MODEL_PATH} ...", file=sys.stderr)
        # Atomic download: write to .tmp then rename.
        tmp = MODEL_PATH.with_suffix(MODEL_PATH.suffix + ".tmp")
        urllib.request.urlretrieve(DOWNLOAD_URL, tmp)
        tmp.replace(MODEL_PATH)
        cached_sha = _sha256_file(MODEL_PATH)

    derived = compute_kraken_model_hash(KRAKEN_VERSION, cached_sha)
    print(f"BiblIA_01.mlmodel sha256: {cached_sha}")
    print(f"kraken_model_hash: {derived}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
