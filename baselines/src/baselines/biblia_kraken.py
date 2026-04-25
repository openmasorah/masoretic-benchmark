"""BL-02: BiblIA Kraken Generalized baseline.

The cleanest reproducible baseline: no oracle deps, no LLM calls. The
foundation BL-03 (Kraken -> Nakdimon) and BL-04 (Kraken -> DictaBERT)
build on via the shared baselines._kraken wrapper.

Pinned model: Zenodo DOI 10.5281/zenodo.5468286 (the BiblIA_01.mlmodel
artifact). Pin row in baselines/KRAKEN_PIN.md; KRAKEN_MODEL_HASH
constant re-derived on import.

NOTE on DOIs: ``10.5281/zenodo.5468286`` is the MODEL DOI. The Phase 1
dry-run stub at ``gt-infra/gt_infra/dry_run/biblia_kraken_stub.py`` (in
baalshem) uses ``10.5281/zenodo.5167263`` which is the DATASET DOI (the
BiblIA paper's training corpus, NOT the model file). Production code
uses the model DOI; the Phase 1 stub stays unchanged in baalshem.

D-12 contract: this subclass overrides ONLY ``infer_folio``. The
template-method ABC's ``run()`` is locked structurally by
tests/test_invariants.py. D-13a/D-13b ScopeViolation preflight,
D-14 sandbox-then-promote, D-15 expected_total_reports bit-equality,
and D-16/D-17/D-19 schema validation are inherited for free.

D-04: per-line LineRecord.kraken_confidence is populated by the
shared wrapper from rpred.rpred per-character confidences;
KrakenInferenceFailure on full-page failure aborts the folio per the
atomic-run policy (sandbox left for inspection).
"""

from __future__ import annotations

import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from baselines._base import BaselineBase, LineRecord
from baselines._images import fetch_image, image_sha256
from baselines._kraken import KRAKEN_MODEL_HASH, recognize_lines

# Path resolution: this file is at
#   <repo>/baselines/src/baselines/biblia_kraken.py
# parents[0]=baselines, parents[1]=src, parents[2]=baselines, parents[3]=<repo>.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_PATH = REPO_ROOT / "baselines" / ".cache" / "kraken" / "BiblIA_01.mlmodel"
DEFAULT_IMAGE_CACHE = REPO_ROOT / "baselines" / ".cache" / "images"


class BibliaKrakenBaseline(BaselineBase):
    """BL-02 BiblIA Kraken Generalized baseline (D-12 template-method subclass)."""

    BASELINE_ID = "biblia_kraken"

    def __init__(
        self,
        manifest_path,
        results_root,
        *,
        replay: bool = False,
        model_path: Path = DEFAULT_MODEL_PATH,
        image_cache: Path = DEFAULT_IMAGE_CACHE,
    ) -> None:
        super().__init__(manifest_path, results_root, replay=replay)
        self.model_path = Path(model_path)
        self.image_cache = Path(image_cache)
        # Per-folio meta accumulated during run() and emitted by
        # _compose_run_meta into run_meta.folios.<folio_id>.
        self._folio_meta: dict[str, dict] = {}

    # -- D-12 abstract method (only override) --------------------------------
    def infer_folio(self, folio) -> list[LineRecord]:
        """Per-folio inference. THE ONLY method overridden.

        Fetches the folio image (idempotent cache), runs the shared Kraken
        wrapper to produce LineRecords, and stamps per-folio provenance into
        ``self._folio_meta`` for run_meta emission.

        Raises KrakenInferenceFailure on full-page failure (D-04). Caller's
        SandboxRun __exit__ leaves the sandbox for inspection.
        """
        image_path = fetch_image(folio.id, folio.image_url, self.image_cache)
        # image_sha256 is computed for paper provenance; not yet emitted into
        # the schema (per-folio entries are additionalProperties=false in the
        # run_meta schema). We keep the call here so live runs surface drift.
        _ = image_sha256(image_path)
        lines = recognize_lines(image_path, self.model_path, folio_id=folio.id)
        self._folio_meta[folio.id] = {
            "budget_used": None,
            "replay_used": None,
            "line_count": len(lines),
            "scope_check_passed_at_iso": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        }
        return lines

    # -- run_meta extension --------------------------------------------------
    def _compose_run_meta(self) -> dict:
        """Extend the base default with BL-02 specifics (D-19)."""
        base = super()._compose_run_meta()
        base["hostname"] = socket.gethostname()
        base["sibling_git_sha"] = self._read_git_sha()
        base["pins"] = {
            "kraken_model_hash": KRAKEN_MODEL_HASH,
            "nakdimon_model_hash": None,
            "dictabert_model_revision": None,
            "llm_pin_md_hash": None,
        }
        # Budget / combine remain null (BL-02 has no LLM cost cap, no
        # combine logic).
        base["folios"] = self._folio_meta
        return base

    @staticmethod
    def _read_git_sha() -> str | None:
        """Best-effort sibling-repo HEAD sha for run_meta provenance.

        Returns None on any failure (subprocess error, not in a git repo,
        etc.) so a CI environment without git history doesn't break runs.
        """
        try:
            out = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=REPO_ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            return out.strip()[:12]
        except Exception:
            return None
