"""archive.org image fetcher with sha256-by-reference (D-10 image policy).

Public surface (load-bearing — wave 3 plan 03-07 imports these by name):

    fetch_image(folio_id, image_url, cache_dir) -> Path
    image_sha256(path) -> str

Cache layout: ``<cache_dir>/<folio_id>.<ext>`` (default ``.jpg`` for archive.org
URLs). Cache is gitignored (.gitignore covers ``baselines/.cache/``); image
bytes are NEVER inlined into prediction JSON or replay logs — only the
sha256 fingerprint travels with provenance.

Idempotent: second call with the same folio_id hits the cached file; no
network call. The atomic-write idiom (``.tmp`` + replace) keeps a partial
download from masquerading as a complete cache entry.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path


def fetch_image(folio_id: str, image_url: str, cache_dir: Path) -> Path:
    """Download (or skip-if-cached) the folio image; return the local path.

    Args:
        folio_id: Stable folio identifier; used as the cache filename stem.
        image_url: Direct download URL (typically archive.org).
        cache_dir: Local cache directory; created if missing.

    Returns:
        Path to the cached image file. The file extension is preserved from
        the URL (defaults to ``.jpg`` if the URL has no suffix).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(image_url).suffix or ".jpg"
    path = cache_dir / f"{folio_id}{ext}"
    if path.exists():
        return path
    # Atomic download: write to .tmp then rename, so a partial download
    # never poisons the cache (CTRL-C / process death mid-stream).
    tmp = path.with_suffix(path.suffix + ".tmp")
    urllib.request.urlretrieve(image_url, tmp)
    tmp.replace(path)
    return path


def image_sha256(path: Path) -> str:
    """Return the sha256 hex digest of the image bytes at `path`.

    Streamed read (1 MB chunks) so large images don't blow up memory.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
