"""D-08 (RESEARCH delta #2): nakdimon MODEL_HASH.

Form: ``sha256(f"nakdimon=={version}:" + sha256(Nakdimon.h5))[:16]``.

Simplified from CONTEXT.md D-08 because PyPI wheel bundles weights — there is no
separate HuggingFace revision SHA to incorporate. Document deviation in NAKDIMON_PIN.md.
"""

from __future__ import annotations

import hashlib
from importlib.metadata import version
from pathlib import Path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_nakdimon_model_hash() -> str:
    """Return short MODEL_HASH for the installed nakdimon wheel.

    Form: sha256(f"nakdimon=={version}:" + sha256(Nakdimon.h5))[:16]
    Deterministic: same wheel + same H5 bytes => same hash.
    """
    import nakdimon

    nakdimon_dir = Path(nakdimon.__file__).parent
    h5_path = nakdimon_dir / "Nakdimon.h5"
    h5_sha = _sha256_file(h5_path)
    composed = f"nakdimon=={version('nakdimon')}:{h5_sha}".encode()
    return hashlib.sha256(composed).hexdigest()[:16]
