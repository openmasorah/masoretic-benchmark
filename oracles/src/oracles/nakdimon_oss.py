"""Primary oracle: Nakdimon OSS (elazarg/nakdimon, MIT, PyPI 0.1.2).

ORA-01 / D-20 public API:
  diacritize(consonantal) -> str
  disagreement_rate(prediction) -> (rate, audit_meta)
  MODEL_HASH: str   (16-char hex, see oracles._hashing)

Reproducibility (D-08, RESEARCH delta #2):
  MODEL_HASH = sha256(f"nakdimon=={version}:" + sha256(Nakdimon.h5))[:16]
  Same wheel + same H5 bytes => same hash. Re-pin via NAKDIMON_PIN.md (D-09).

Pitfall 3 (rafe stripping):
  nakdimon.predict() strips U+05BF (rafe) and collapses double-spaces.
  This DOES NOT affect DEC because DEC operates on vowel-decision clusters
  only (whitespace and rafe are not vowel codepoints in
  masoretic_eval.metrics.nakdimon.nakdimon_factoring). U+034F (CGJ) passes
  through Nakdimon unchanged — verified in test_nakdimon_oss.py::
  test_cgj_preserved_through_diacritize. Note: the scorer's
  strip_to_consonantal does drop CGJ (CGJ is outside the 0x05D0-0x05EA
  consonant range), so disagreement_rate's skeleton input to the oracle
  will not contain CGJ. The oracle-level preservation guarantee is about
  diacritize() itself: if Nakdimon receives CGJ, Nakdimon returns CGJ.

Pitfall 6 (cold-start cost):
  First diacritize() call pays 3-8s of TensorFlow graph compile + Keras H5
  load. Subsequent calls in the same process are ~100-300ms per line.
  Module import does NOT eagerly call diacritize — callers absorb the
  first-call cost where it makes sense (compute_oracles.py warms before
  iterating folios).

Pitfall 1 (TF x Python compatibility):
  nakdimon==0.1.2 pins tensorflow==2.15.0 which has no macOS-arm64 wheel
  for Python >= 3.12. Use Python 3.11 for the Nakdimon path. A Py-3.12
  venv can still run the scorer + oracles scaffolding but must not try
  to import this module. CI pins the Nakdimon job to Python 3.11.
"""
from __future__ import annotations

from typing import Tuple

import nakdimon  # type: ignore[import-untyped]
from masoretic_eval.metrics.nakdimon import nakdimon_factoring

from oracles._hashing import compute_nakdimon_model_hash
from oracles._strip import strip_to_consonantal

MODEL_HASH = compute_nakdimon_model_hash()  # 16-char hex, see oracles._hashing


def diacritize(consonantal: str) -> str:
    """Return Nakdimon's diacritization of consonantal Hebrew (ORA-01).

    Forwards to nakdimon.diacritize(text) — the PyPI 0.1.2 public API.
    Output is NOT byte-identical to input even when the input is
    already-diacritized (rafe-stripped per Pitfall 3); use disagreement_rate
    for the metric, not raw byte equality.
    """
    return nakdimon.diacritize(consonantal)


def disagreement_rate(prediction: str) -> Tuple[float, dict]:
    """Per-line disagreement rate (D-01): 1 - DEC(prediction, nakdimon(skeleton)).

    Returns:
      (rate, audit_meta) where audit_meta is a small dict suitable for
      inclusion in run-level provenance. The rate is in [0.0, 1.0]; high
      values for pre-modern Tiberian are evidentiary, not bugs (paper §6).
    """
    skeleton = strip_to_consonantal(prediction)
    oracle_text = diacritize(skeleton)
    result = nakdimon_factoring(prediction, oracle_text)
    rate = 1.0 - result.dec
    meta = {
        "oracle": "nakdimon_oss",
        "model_hash": MODEL_HASH,
        "input_cp_count": len(prediction),
        "oracle_cp_count": len(oracle_text),
        "dec": result.dec,
    }
    return rate, meta


__all__ = ["diacritize", "disagreement_rate", "MODEL_HASH"]
