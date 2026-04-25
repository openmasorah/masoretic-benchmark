"""BL-04: BiblIA Kraken + DictaBERT char-menaked chain (publishable negative result).

DISCLAIMER (D-27, verbatim — must match oracles/dictabert.py and
oracles/README.md and baselines/README.md character-for-character):

dictabert-large-char-menaked is trained on modern Hebrew and is off-label for pre-modern Tiberian text. Used here only as a publishable negative-result baseline (Baseline 4). Do not interpret outputs as oracle-grade diacritization.

Per Phase 2 D-26 + Phase 3 A-3: this module imports oracles.dictabert.diacritize
ONLY. The forbidden symbols (DictaBERT does not expose any disagreement-rate
function — exposing one would imply oracle-grade trust we publicly disclaim;
the score-time wrapper from oracles/ is reserved for Phase 4 score-time use,
not Phase 3 production) MUST NOT appear in this file. Plan 03-08 ships a
grep-based invariant that enforces zero references to either forbidden
symbol from any file under baselines/.

Two output streams per folio (D-01):

  - Realistic chain (counted toward expected_total_reports):
        results/biblia_char_menaked/<folio_id>.json
        Kraken consonants -> DictaBERT -> tier-2/3
  - GT-fed diagnostic (NOT counted; paper-only):
        results/biblia_char_menaked/diagnostic/<folio_id>.gt_fed.json
        GT consonants -> DictaBERT -> isolates diacritizer error from OCR error

The GT-fed diagnostic sharpens BL-04's negative-result claim: showing
DictaBERT's error rate ON PERFECT CONSONANTS is the paper's strongest
argument that the model itself, not the upstream OCR, is the floor for
pre-modern Tiberian.

D-12 contract: this subclass overrides ONLY BASELINE_ID,
DIACRITIZER_PIN_FIELD, DIACRITIZER_PIN_VALUE, and diacritize(). The
template-method ABC's run() is locked structurally by
tests/test_invariants.py; ChainBaseline (plan 03-05) provides
infer_folio + diagnostic-write + run_meta extension shared with BL-03.
"""

from __future__ import annotations

# IMPORTANT (D-26 + A-3): direct import of diacritize ONLY.
# This file deliberately contains NO references to either of the two
# forbidden symbols enumerated in the module docstring above. A grep-based
# invariant in plan 03-08 enforces zero matches across all of baselines/;
# this file's per-file enforcement is asserted in
# test_baseline_unit_char_menaked_chain.py + the plan acceptance criteria.
from oracles.dictabert import (
    MODEL_REVISION as DICTABERT_REVISION,
)
from oracles.dictabert import (
    diacritize as dictabert_diacritize,
)

from baselines._chain import ChainBaseline


class BibliaCharMenakedBaseline(ChainBaseline):
    """BL-04 BiblIA Kraken + DictaBERT char-menaked chain (D-12 + ChainBaseline).

    The off-label disclaimer above is load-bearing: BL-04's purpose is the
    paper's negative-result framing. The disclaimer is pinned in this
    docstring AND in baselines/README.md by
    test_dictabert_disclaimer_invariant.py — drift in either location
    fails CI.
    """

    BASELINE_ID = "biblia_char_menaked"
    DIACRITIZER_PIN_FIELD = "dictabert_model_revision"
    # Phase 2 02-04 lock — re-asserted by
    # test_baseline_unit_char_menaked_chain.py::test_char_menaked_run_meta_pins
    # so a Phase 2 revision drift is also caught at the consumer layer.
    DIACRITIZER_PIN_VALUE = DICTABERT_REVISION

    # The ONLY method override. Per A-3, this is a direct call to
    # oracles.dictabert.diacritize — by design no other oracle helper is
    # imported (see module docstring + the import block above for the
    # forbidden-symbol policy).
    def diacritize(self, consonantal: str) -> str:
        return dictabert_diacritize(consonantal)
