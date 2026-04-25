"""BL-03: BiblIA Kraken + Nakdimon OSS chain (realistic + GT-fed diagnostic).

The first oracle-chain baseline; tests the Kraken-shared infrastructure
(Plan 03-04) plus the direct-diacritize-import discipline (A-3) plus the
two-output diagnostic pattern (D-01).

Per A-3 (Phase 3 adjudication, locked):

    BL-03 imports `oracles.nakdimon_oss.diacritize` DIRECTLY. The
    `oracles.compute_oracles` wrapper is Phase 4 score-time work, NOT a
    Phase 3 production import. A grep-based invariant in Plan 03-08
    enforces zero references in `baselines/` to that wrapper symbol.

D-01 two-output pattern (inherited from ChainBaseline):

  - Realistic chain (counted, leaderboard number):
        results/biblia_nakdimon/<folio_id>.json
        Kraken consonants -> Nakdimon -> tier-2/3
  - GT-fed diagnostic (NOT counted, paper-only):
        results/biblia_nakdimon/diagnostic/<folio_id>.gt_fed.json
        GT consonants -> Nakdimon -> diagnostic prediction
        (isolates diacritizer error from OCR error; sharpens BL-04's
         negative-result framing for the paper)

D-12 contract: this subclass overrides ONLY ``diacritize`` (the abstract
method on ChainBaseline) plus the three class attributes. It does NOT
override ``infer_folio`` (inherited from ChainBaseline) and does NOT
override ``run`` (inherited locked from BaselineBase). AST invariants
in tests/test_invariants.py pin both constraints.

Phase 2 Pitfall 1 carry-forward: nakdimon==0.1.2 + tensorflow==2.15
SIGABRTs on macOS arm64 + Python 3.11/3.12. The mocked unit tier
patches the diacritize symbol via sys.modules so the real Nakdimon
stack never loads; the live tier (live_baselines marker) runs only on
Linux + Py 3.11 in CI (Plan 03-08).
"""
from __future__ import annotations

from baselines._chain import ChainBaseline

# IMPORTANT (A-3, locked Phase 3 adjudication):
#   Direct import of diacritize. The oracles.compute_oracles wrapper is
#   Phase 4 score-time work, NOT a production import. Plan 03-08's
#   contamination grep enforces zero references in baselines/.
from oracles.nakdimon_oss import diacritize as nakdimon_diacritize
from oracles.nakdimon_oss import MODEL_HASH as NAKDIMON_MODEL_HASH


class BibliaNakdimonBaseline(ChainBaseline):
    """BL-03 BiblIA Kraken + Nakdimon OSS chain (D-12 + D-01 subclass)."""

    BASELINE_ID = "biblia_nakdimon"
    DIACRITIZER_PIN_FIELD = "nakdimon_model_hash"
    # Pin value sourced canonical-from-the-pin via oracles.nakdimon_oss.MODEL_HASH
    # (= "8fd7722b8002a690" per Phase 2 02-02 NAKDIMON_PIN.md row).
    DIACRITIZER_PIN_VALUE = NAKDIMON_MODEL_HASH

    def diacritize(self, consonantal: str) -> str:
        """ChainBaseline's abstract method: feed consonants to Nakdimon.

        Called twice per folio (realistic chain + GT-fed diagnostic chain).
        Each call returns Nakdimon's diacritization of the input.
        """
        return nakdimon_diacritize(consonantal)
