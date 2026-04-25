"""One-shot weight-fetcher / hash-recorder for Nakdimon + DictaBERT.

Used by Plan 02-01 to populate the TBD cells in `oracles/NAKDIMON_PIN.md` and
to pre-warm the DictaBERT cache so CI does not download on every run.

Idempotent: skips work when the cache hit is already present.

Usage:
    python -m oracles.scripts.fetch_weights --nakdimon
    python -m oracles.scripts.fetch_weights --dictabert
    python -m oracles.scripts.fetch_weights --nakdimon --dictabert
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# DictaBERT pin (D-28, RESEARCH.md line ~9): HF revision committed 2025-04-08.
DICTABERT_REPO_ID = "dicta-il/dictabert-large-char-menaked"
DICTABERT_REVISION = "d311fbf7c403e50b040440e4859ac78064d025d0"

# Cache lives at oracles/.cache/<oracle>/.
_PKG_ROOT = Path(__file__).resolve().parent.parent  # oracles/
_CACHE_DIR = _PKG_ROOT / ".cache"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_nakdimon() -> dict[str, str]:
    """Locate the installed nakdimon wheel + bundled H5; emit short SHAs.

    Output is the row data needed for `NAKDIMON_PIN.md`:
        {h5_sha256, wheel_record_sha256, version}

    Idempotency: pure read of the installed wheel; no download.
    """
    try:
        import nakdimon  # type: ignore
    except ImportError as err:
        raise SystemExit(
            "ERROR: nakdimon not installed. Run `pip install -e ./oracles[nakdimon]` first."
        ) from err

    nakdimon_dir = Path(nakdimon.__file__).resolve().parent
    h5_path = nakdimon_dir / "Nakdimon.h5"
    if not h5_path.exists():
        raise SystemExit(f"ERROR: expected Nakdimon.h5 next to nakdimon module at {h5_path}")

    # Find the dist-info next to the package.
    site_packages = nakdimon_dir.parent
    dist_infos = list(site_packages.glob("nakdimon-*.dist-info"))
    record_sha: str
    if dist_infos:
        record_path = dist_infos[0] / "RECORD"
        if record_path.exists():
            record_sha = _sha256_file(record_path)
        else:
            record_sha = "RECORD-not-found"
    else:
        record_sha = "dist-info-not-found"

    from importlib.metadata import version as _version

    out = {
        "version": _version("nakdimon"),
        "h5_sha256": _sha256_file(h5_path),
        "wheel_record_sha256": record_sha,
        "h5_path": str(h5_path),
    }
    return out


def fetch_dictabert() -> dict[str, str]:
    """Snapshot-download the pinned DictaBERT revision into the local cache.

    Idempotency: huggingface_hub.snapshot_download skips already-cached files.
    """
    cache_dir = _CACHE_DIR / "dictabert"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download  # type: ignore
    except ImportError as err:
        raise SystemExit(
            "ERROR: huggingface_hub not installed. Run `pip install -e ./oracles[dictabert]` first."
        ) from err
    local = snapshot_download(
        repo_id=DICTABERT_REPO_ID,
        revision=DICTABERT_REVISION,
        cache_dir=str(cache_dir),
    )
    return {
        "repo_id": DICTABERT_REPO_ID,
        "revision": DICTABERT_REVISION,
        "local_path": local,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nakdimon", action="store_true", help="record Nakdimon SHAs")
    p.add_argument("--dictabert", action="store_true", help="snapshot DictaBERT weights")
    args = p.parse_args(argv)

    if not (args.nakdimon or args.dictabert):
        p.print_help()
        return 2

    out: dict[str, dict[str, str]] = {}
    if args.nakdimon:
        out["nakdimon"] = fetch_nakdimon()
    if args.dictabert:
        out["dictabert"] = fetch_dictabert()
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
