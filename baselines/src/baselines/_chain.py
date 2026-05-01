"""ChainBaseline — intermediate ABC for BL-03 + BL-04 (Kraken -> diacritizer chains).

Per D-01: emits TWO outputs per folio:

  - Realistic chain (counted toward expected_total_reports per D-15):
        results/<baseline_id>/<folio_id>.json
        Kraken consonants -> diacritize() -> tier-2/3
  - GT-fed diagnostic (NOT counted; paper-only):
        results/<baseline_id>/diagnostic/<folio_id>.gt_fed.json
        GT consonants -> diacritize()  (isolates diacritizer error from OCR error)

Subclasses override ONLY:

  - BASELINE_ID class attribute
        ("biblia_nakdimon" for BL-03, "biblia_char_menaked" for BL-04)
  - diacritize(consonantal: str) -> str  (the abstract method)
  - DIACRITIZER_PIN_FIELD class attribute
        ("nakdimon_model_hash" or "dictabert_model_revision")
  - DIACRITIZER_PIN_VALUE class attribute (the actual pin value)

Per A-3 (Phase 3 adjudication): BL-03/BL-04 import diacritize() DIRECTLY
from `oracles.nakdimon_oss` / `oracles.dictabert`. The score-time
disagreement-rate wrapper in `oracles.compute_oracles` is reserved for
Phase 4 use; ZERO references to that symbol appear in `baselines/`.
The unit-tier file `test_baseline_unit_nakdimon_chain.py` asserts this
defensively; Plan 03-08 enforces it across all of `baselines/`.

D-12 contract preserved: this class does NOT override BaselineBase.run().
The locked template-method (preflight -> sandbox -> per-folio infer_folio
-> D-15 bit-equality -> sandbox.promote) is inherited as-is. The
diagnostic stream rides through `SandboxRun.write_diagnostic` (Wave 1
03-03 wired schema validation in there) by sharing the active sandbox
directory; the realistic-chain prediction file rides through the normal
`SandboxRun.write_prediction` path called by `BaselineBase.run`.

Pitfall 1 carry-forward (Phase 2 02-02): nakdimon==0.1.2 SIGABRTs on
macOS arm64 + Python 3.11/3.12 due to TF 2.15. Live tier (`live_baselines`
marker) runs only on Linux + Py 3.11 in CI (Plan 03-08); local mocked
unit tier never imports the real Nakdimon stack.
"""

from __future__ import annotations

import json
import socket
import subprocess
from abc import abstractmethod
from datetime import UTC, datetime
from pathlib import Path

from baselines._atomic import SandboxRun
from baselines._base import BaselineBase, LineRecord
from baselines._errors import BaselineError
from baselines._gt_adapter import load_tier1_per_line
from baselines._images import fetch_image
from baselines._kraken import KRAKEN_MODEL_HASH, recognize_lines

# Path resolution: this file is at
#   <repo>/baselines/src/baselines/_chain.py
# parents[0]=baselines, parents[1]=src, parents[2]=baselines, parents[3]=<repo>.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KRAKEN_MODEL = REPO_ROOT / "baselines" / ".cache" / "kraken" / "BiblIA_01.mlmodel"
DEFAULT_IMAGE_CACHE = REPO_ROOT / "baselines" / ".cache" / "images"

# Default GT roots for the diagnostic chain. Real Phase 1 has only a
# single-text-blob fixture (`gt-infra/exports/<folio>.json` is not yet
# emitted with the per-line `{lines:[{line_id,bbox,tier1}]}` shape this
# loader needs — see Issue 2 fix in plan 03-05). Mocked unit tests pass
# their own tmp_path GT root so the loader code path is exercised
# regardless. Live tier skips when no candidate exists.
BAALSHEM_GT_DIR_DEFAULT = Path("/Users/benlamm/Workspace/baalshem/gt-infra/exports")
BAALSHEM_FIXTURE_DIR = Path("/Users/benlamm/Workspace/baalshem/tests/fixtures")


class ChainBaseline(BaselineBase):
    """Intermediate ABC for chain baselines (BL-03 + BL-04).

    Subclasses override ONLY:
      - BASELINE_ID
      - diacritize(consonantal) -> str (the abstract method below)
      - DIACRITIZER_PIN_FIELD / DIACRITIZER_PIN_VALUE class attributes
    """

    # Subclass MUST set; checked at run-time via _compose_run_meta.
    DIACRITIZER_PIN_FIELD: str = ""
    DIACRITIZER_PIN_VALUE: str = ""

    def __init__(
        self,
        manifest_path,
        results_root,
        *,
        replay: bool = False,
        kraken_model_path: Path = DEFAULT_KRAKEN_MODEL,
        image_cache: Path = DEFAULT_IMAGE_CACHE,
        gt_root: Path = BAALSHEM_GT_DIR_DEFAULT,
    ) -> None:
        super().__init__(manifest_path, results_root, replay=replay)
        self.kraken_model_path = Path(kraken_model_path)
        self.image_cache = Path(image_cache)
        self.gt_root = Path(gt_root)
        # Per-folio meta accumulated during run() and emitted by
        # _compose_run_meta into run_meta.folios.<folio_id>.
        self._folio_meta: dict[str, dict] = {}

    # -- abstract surface (subclass overrides ONLY this) ---------------------
    @abstractmethod
    def diacritize(self, consonantal: str) -> str:
        """Concrete subclasses provide the diacritizer.

        BL-03: oracles.nakdimon_oss.diacritize
        BL-04: oracles.dictabert.diacritize
        """

    # -- D-12 abstract method (only override of BaselineBase) ---------------
    def infer_folio(self, folio) -> list[LineRecord]:
        """Realistic chain: Kraken consonants -> diacritize() -> tier strings.

        ALSO writes the GT-fed diagnostic file as a side effect via
        ``self._write_gt_diagnostic(folio)`` — diagnostic is a paper-only
        companion, not a return value. Per D-15, only the returned
        realistic-chain LineRecords are counted toward `expected_total_reports`;
        the diagnostic write lands in `<sandbox>/diagnostic/<folio>.gt_fed.json`
        which `SandboxRun.count()` filters out.
        """
        # 1) Realistic chain: Kraken transcribes consonants from image,
        #    then diacritize() produces tier-2/3 from Kraken's noisy text.
        image_path = fetch_image(folio.id, folio.image_url, self.image_cache)
        kraken_lines = recognize_lines(image_path, self.kraken_model_path, folio_id=folio.id)
        out: list[LineRecord] = []
        for ln in kraken_lines:
            # ln.tier1/tier2/tier3 are all set to Kraken's raw line text by
            # _kraken.recognize_lines (the scorer re-derives tier views at
            # score time). For the realistic chain we keep tier1 as Kraken's
            # consonant-tier view and overwrite tier2/tier3 with the
            # diacritizer's output.
            diacritized = self.diacritize(ln.tier1)
            out.append(
                LineRecord(
                    line_id=ln.line_id,
                    bbox=ln.bbox,
                    tier1=ln.tier1,  # Kraken's text (consonant-tier view at score time)
                    tier2=diacritized,  # diacritizer's output
                    tier3=diacritized,  # same — scorer re-derives trop view
                    tier4_records=tuple(),
                    kraken_confidence=ln.kraken_confidence,
                )
            )

        # 2) GT-fed diagnostic chain (D-01): GT consonants -> diacritize().
        #    Written as a side effect into the active sandbox's
        #    diagnostic/ subdir; NOT counted toward expected_total_reports
        #    (SandboxRun.count() ignores diagnostic/).
        self._write_gt_diagnostic(folio)

        # 3) Per-folio run_meta accumulator (consumed by _compose_run_meta).
        self._folio_meta[folio.id] = {
            "budget_used": None,
            "replay_used": None,
            "line_count": len(out),
            "scope_check_passed_at_iso": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        return out

    # -- D-01 GT-fed diagnostic stream --------------------------------------
    def _write_gt_diagnostic(self, folio) -> None:
        """GT-fed diagnostic chain: GT consonants -> diacritize() -> diagnostic
        prediction. NOT counted toward expected_total_reports (D-15).

        We construct an ephemeral `SandboxRun` pointing at the active
        sandbox dir (already created by `BaselineBase.run`'s `with`-block
        on entry) and call its `write_diagnostic` method, which:
          - validates the payload against `baseline_prediction.schema.json`
            (Wave 1 03-03 wired this in),
          - creates `<sandbox>/diagnostic/` lazily,
          - atomically writes `<folio>.gt_fed.json` via temp-file + replace.
        """
        gt_lines = self._load_gt_consonants(folio)
        diag_lines: list[LineRecord] = []
        for line_id, bbox, tier1_gt in gt_lines:
            diacritized = self.diacritize(tier1_gt)
            diag_lines.append(
                LineRecord(
                    line_id=line_id,
                    bbox=bbox,
                    tier1=tier1_gt,
                    tier2=diacritized,
                    tier3=diacritized,
                    tier4_records=tuple(),
                    # No kraken_confidence — diagnostic uses GT, not Kraken.
                )
            )
        payload = self._serialize(folio, diag_lines)

        # Reuse SandboxRun.write_diagnostic for: schema validation +
        # diagnostic/ subdir creation + atomic-write idiom. The active
        # sandbox dir is already created by the parent `with SandboxRun(...)`
        # in BaselineBase.run; constructing a sibling SandboxRun against
        # the same paths is safe (it's a thin wrapper over the path).
        sb = SandboxRun(self.results_root, self.BASELINE_ID)
        sb.write_diagnostic(folio.id, payload)

    def _load_gt_consonants(self, folio) -> list[tuple[str, tuple[int, int, int, int], str]]:
        """Load frozen GT consonants for the diagnostic chain.

        Phase 03.1 D-21 (locked 2026-04-27): primary source is PAGE-XML at
        ``<gt_root>/<folio_id>.page.xml`` consumed via
        ``baselines._gt_adapter.load_tier1_per_line`` — symmetric with the
        realistic-chain branch's tier-1 extraction over BL-02's PAGE-XML
        Kraken cache. PAGE-XML records carry no bbox; bbox is emitted as
        ``(0,0,0,0)`` per line and ``line_id`` is reconstructed as
        ``<folio_id>_L<line_num>``. This is acceptable for the GT-fed
        diagnostic stream — the diagnostic is paper-only (D-01), not
        consumed by per-line CER (which is deferred to v0.2 anyway), and
        the prediction-schema validator accepts ``bbox=[0,0,0,0]``.

        JSON fallback retained for unit tests (and Phase 1's pre-PAGE-XML
        per-line export shape). The JSON shape is:

            {"lines": [
                {"line_id": "...", "bbox": [x0,y0,x1,y1], "tier1": "..."},
                ...
            ]}

        Returns: list of (line_id, bbox-tuple, tier1) tuples.

        Raises: BaselineError if neither PAGE-XML nor JSON is present for
        ``folio.id`` at any candidate path.
        """
        # Primary: PAGE-XML at <gt_root>/<folio_id>.page.xml (D-21).
        page_xml_candidates = [
            self.gt_root / f"{folio.id}.page.xml",
        ]
        for path in page_xml_candidates:
            if path.exists():
                tier1_lines = load_tier1_per_line(folio.id, path)
                return [
                    (
                        f"{folio.id}_L{idx + 1:03d}",
                        (0, 0, 0, 0),
                        tier1,
                    )
                    for idx, tier1 in enumerate(tier1_lines)
                ]

        # Fallback: per-line JSON shape (unit-test compat + Phase 1 dry-run).
        json_candidates = [
            self.gt_root / f"{folio.id}.json",
            BAALSHEM_FIXTURE_DIR / f"{folio.id}.json",
        ]
        for path in json_candidates:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return [
                    (
                        entry["line_id"],
                        tuple(entry["bbox"]),
                        entry["tier1"],
                    )
                    for entry in data["lines"]
                ]
        all_candidates = page_xml_candidates + json_candidates
        raise BaselineError(
            f"D-01 diagnostic chain: no GT for folio {folio.id} found at any "
            f"of {[str(p) for p in all_candidates]!r}"
        )

    # -- run_meta extension --------------------------------------------------
    def _compose_run_meta(self) -> dict:
        """Extend the base default with chain-baseline specifics (D-19).

        Subclass-determined diacritizer pin lands at:
          - pins.nakdimon_model_hash
            (BL-03 sets DIACRITIZER_PIN_FIELD="nakdimon_model_hash")
          - pins.dictabert_model_revision
            (BL-04 sets DIACRITIZER_PIN_FIELD="dictabert_model_revision")
        """
        base = super()._compose_run_meta()
        base["hostname"] = socket.gethostname()
        base["sibling_git_sha"] = self._read_git_sha()

        # Build pins so the subclass-declared diacritizer pin lands in the
        # right slot; the other two diacritizer slots stay null.
        pins = {
            "kraken_model_hash": KRAKEN_MODEL_HASH,
            "nakdimon_model_hash": None,
            "dictabert_model_revision": None,
            "llm_pin_md_hash": None,
        }
        if self.DIACRITIZER_PIN_FIELD:
            if self.DIACRITIZER_PIN_FIELD not in pins:
                raise BaselineError(
                    f"DIACRITIZER_PIN_FIELD={self.DIACRITIZER_PIN_FIELD!r} is "
                    "not a recognized run_meta.pins.* slot"
                )
            pins[self.DIACRITIZER_PIN_FIELD] = self.DIACRITIZER_PIN_VALUE or None
        base["pins"] = pins

        # budget / combine remain null (no LLM cost cap, no combine logic)
        base["folios"] = self._folio_meta
        return base

    @staticmethod
    def _read_git_sha() -> str | None:
        """Best-effort sibling-repo HEAD sha for run_meta provenance.

        Mirrors BibliaKrakenBaseline._read_git_sha; returns None on any
        failure so a CI environment without git history doesn't break runs.
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
