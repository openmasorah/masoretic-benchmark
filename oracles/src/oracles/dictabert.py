"""Off-label oracle: dicta-il/dictabert-large-char-menaked (ORA-03).

DISCLAIMER (D-27, verbatim -- must match oracles/README.md character-for-character):

`dictabert-large-char-menaked` is trained on modern Hebrew and is off-label for pre-modern Tiberian text. Used here only as a publishable negative-result baseline (Baseline 4). Do not interpret outputs as oracle-grade diacritization.

API surface (D-26): diacritize() ONLY. No disagreement_rate -- exposing one
would imply oracle-grade trust we publicly disclaim. Phase 3 baseline 4
(BL-04) imports diacritize() and MODEL_REVISION; no other caller imports
this module.

Pitfall 4 (trust_remote_code supply-chain risk):
  AutoModel.from_pretrained(..., trust_remote_code=True) downloads and
  executes BertForDiacritization.py from the pinned HF revision. Revision
  pinning (D-28) caps current risk; on every re-pin a human MUST manually
  diff the new BertForDiacritization.py vs. the previous version and log
  the result in NAKDIMON_PIN.md (analogous DictaBERT log entry).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from transformers import AutoModel, AutoTokenizer  # type: ignore[import-untyped]

MODEL_ID: str = "dicta-il/dictabert-large-char-menaked"
MODEL_REVISION: str = "d311fbf7c403e50b040440e4859ac78064d025d0"  # D-28 + RESEARCH delta #3
_CACHE_DIR: Path = Path(__file__).resolve().parents[2] / ".cache" / "dictabert"


@lru_cache(maxsize=1)
def _load() -> tuple[object, object]:
    """Load tokenizer + model from the pinned HF revision. Cached process-wide."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, cache_dir=str(_CACHE_DIR)
    )
    mdl = AutoModel.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        trust_remote_code=True,
        cache_dir=str(_CACHE_DIR),
    )
    mdl.eval()
    return tok, mdl


def diacritize(consonantal: str) -> str:
    """Return DictaBERT char-menaked diacritization. OFF-LABEL -- see disclaimer.

    Single-string input, single-string output. Loads model on first call
    (~1-2s on warm cache, ~30-60s on cold download).
    """
    tok, mdl = _load()
    preds = mdl.predict([consonantal], tok)
    if not preds:
        return ""
    first = preds[0]
    return first if isinstance(first, str) else str(first)


__all__ = ["diacritize", "MODEL_ID", "MODEL_REVISION"]
