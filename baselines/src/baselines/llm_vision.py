"""BL-01: LLM-best-of-two vision-only baseline.

Two sources: Claude Opus 4.7 + Gemini 2.5 Pro. Vision-only — line image only,
NEVER UXLC text or any GT-derived signal in the prompt (D-05 contamination
boundary).

Combine: whole-line winner with alphabetical tie-break (Claude < Gemini, so
Claude wins ties). NO tier-mixing across sources within a line (D-07).

Reproducibility: internal — replay log (D-10) at
``results/llm_vision/<folio>/llm_calls.jsonl`` is the contract. Anyone with
the repo can replay byte-equal against the logged responses. Outsider
reproducibility (re-running against fresh API calls) is NOT solved —
Anthropic/Google internal IDs are not portable; documented honestly here
and in the paper methodology delta (Phase 5 PAP-04 / PAP-09).

HISTORY: AbbyyFR was dropped 2026-04-25 per Phase 3 Adjudication A-2:
  - Engine SDK Hebrew Bible mode = training-contamination risk (vendor opaque).
  - Cloud SDK = rotating endpoint, no version header (DICTA-style non-reproducible).
  - 2026 frontier vision LLMs cleanly clear the bar AbbyyFR fails.
See ``paper/methodology_delta_BL-01_AbbyyFR_drop.md`` (in baalshem) for
the full reframing rationale; CONTEXT.md decision-log entry D-20 records
the dependency graph implication.

Line segmentation: shared with BL-02 (Kraken-derived bboxes); LLMs see one
cropped line image at a time. The LLM never sees Kraken's transcription —
only the cropped image bytes. "Vision-only" applies to the transcription
step, not the segmentation step (paper methodology discloses this).

D-12 contract: this subclass overrides ONLY ``infer_folio``. The
template-method ABC's ``run()`` is locked structurally by
``tests/test_invariants.py``. D-13 ScopeViolation preflight, D-14
sandbox-then-promote, D-15 expected_total_reports bit-equality, and
D-16/D-17/D-19 schema validation are inherited for free.
"""

from __future__ import annotations

import base64
import hashlib
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from baselines._base import BaselineBase, LineRecord
from baselines._errors import BudgetExceeded
from baselines._images import fetch_image, image_sha256
from baselines._kraken import KRAKEN_MODEL_HASH, recognize_lines
from baselines._llm_clients import (
    ANTHROPIC_MODEL_ID,
    BUDGET_CFG,
    GEMINI_MODEL_ID,
    INFERENCE_CFG,
    RATE_TABLE,
    claude_client,
    gemini_client,
)
from baselines._llm_combine import combine_lines
from baselines._llm_replay import llm_call_with_replay

# llm_vision.py lives at .../baselines/src/baselines/llm_vision.py
#   parents[3] = sibling repo root (masoretic-benchmark)
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KRAKEN_MODEL = REPO_ROOT / "baselines" / ".cache" / "kraken" / "BiblIA_01.mlmodel"
DEFAULT_IMAGE_CACHE = REPO_ROOT / "baselines" / ".cache" / "images"
LLM_PIN_MD = REPO_ROOT / "baselines" / "LLM_PIN.md"

# D-05 contamination boundary: this prompt contains image + a generic
# transcription instruction ONLY. NO UXLC text, NO verse content, NO
# token-level GT-derived signal. The contamination unit test (Plan 03-08)
# greps llm_calls.jsonl entries for any UXLC fragment in request.prompt;
# a single match fails the build.
PROMPT_TEXT = (
    "Transcribe the Hebrew text visible in this image. "
    "Return ONLY the Hebrew characters with their full diacritics (nikkud) "
    "and cantillation marks (trop) as you see them. "
    "Do not translate, romanize, or comment. "
    "Do not add or remove diacritics that are not visible."
)


class LLMVisionBaseline(BaselineBase):
    """BL-01 LLM-best-of-two vision-only baseline (D-12 template-method subclass)."""

    BASELINE_ID = "llm_vision"

    def __init__(
        self,
        manifest_path,
        results_root,
        *,
        replay: bool = False,
        kraken_model_path: Path = DEFAULT_KRAKEN_MODEL,
        image_cache: Path = DEFAULT_IMAGE_CACHE,
    ) -> None:
        super().__init__(manifest_path, results_root, replay=replay)
        self.kraken_model_path = Path(kraken_model_path)
        self.image_cache = Path(image_cache)
        self._folio_meta: dict[str, dict] = {}
        self._used_total_usd: float = 0.0
        self._tie_breaks_total: int = 0
        self._winners = {"claude": 0, "gemini": 0}

    # -- D-12 abstract method (only override) --------------------------------
    def infer_folio(self, folio) -> list[LineRecord]:
        """Per-folio inference: Kraken segmentation -> per-line crops ->
        Claude + Gemini transcription -> D-07 whole-line combine.

        D-08 budget cap fires per-line (post-pair) and per-run; both raise
        BudgetExceeded so the atomic-run policy (D-14) leaves the sandbox
        for inspection rather than promoting to ``results/llm_vision/``.

        D-10 replay log: every LLM call writes one record to
        ``<sandbox>/llm_vision/<folio_id>/llm_calls.jsonl``. The folder
        is created lazily on first call; the per-line cropped image lands
        next to the log so the replay set is self-contained for inspection.
        """
        # PIL lazy-imported so mocked unit tests don't require Pillow on
        # the import path (matches the _kraken.py / _images.py pattern).
        from PIL import Image  # noqa: WPS433

        image_path = fetch_image(folio.id, folio.image_url, self.image_cache)
        # image_sha256 surfaces drift in live runs; not currently emitted to
        # the schema (run_meta.folios per-entry is additionalProperties=false).
        _ = image_sha256(image_path)
        kraken_lines = recognize_lines(
            image_path, self.kraken_model_path, folio_id=folio.id
        )
        replay_log = (
            self.results_root
            / ".in_progress"
            / "llm_vision"
            / folio.id
            / "llm_calls.jsonl"
        )

        out: list[LineRecord] = []
        folio_used_usd = 0.0
        folio_image = Image.open(image_path).convert("RGB")
        for ln in kraken_lines:
            # Crop the line region; LLMs see ONLY this cropped image.
            crop_path = replay_log.parent / f"{ln.line_id}.jpg"
            crop_path.parent.mkdir(parents=True, exist_ok=True)
            folio_image.crop(ln.bbox).save(crop_path, format="JPEG")
            crop_sha = image_sha256(crop_path)

            claude_meta = self._call_claude(crop_path, crop_sha, replay_log)
            gemini_meta = self._call_gemini(crop_path, crop_sha, replay_log)

            line_used_usd = self._estimate_usd(claude_meta, "claude") + self._estimate_usd(
                gemini_meta, "gemini"
            )
            folio_used_usd += line_used_usd
            self._used_total_usd += line_used_usd
            self._enforce_budget(folio_used_usd, folio_id=folio.id)

            rec, winner, tie = combine_lines(
                claude_line={"raw": claude_meta["response"]},
                gemini_line={"raw": gemini_meta["response"]},
                line_id=ln.line_id,
                bbox=ln.bbox,
            )
            out.append(rec)
            self._tie_breaks_total += tie
            self._winners[winner] += 1

        self._folio_meta[folio.id] = {
            "budget_used":               round(folio_used_usd, 6),
            "replay_used":               self.replay,
            "line_count":                len(out),
            "scope_check_passed_at_iso": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        }
        return out

    # -- D-08 budget enforcement --------------------------------------------
    def _enforce_budget(self, folio_used: float, *, folio_id: str) -> None:
        """Per-folio + per-run cap (D-08). BudgetExceeded is a ScopeViolation
        sibling — sandbox-then-promote (D-14) leaves results/.in_progress/
        for inspection."""
        if folio_used > BUDGET_CFG["cap_per_folio_usd"]:
            raise BudgetExceeded(
                f"D-08: per-folio budget cap exceeded on folio {folio_id}: "
                f"${folio_used:.4f} > ${BUDGET_CFG['cap_per_folio_usd']}"
            )
        if self._used_total_usd > BUDGET_CFG["cap_run_usd"]:
            raise BudgetExceeded(
                f"D-08: per-run budget cap exceeded: "
                f"${self._used_total_usd:.4f} > ${BUDGET_CFG['cap_run_usd']}"
            )

    @staticmethod
    def _estimate_usd(meta: dict, source: str) -> float:
        """Conservative cost estimate from token counts and rate table.

        D-08: pre-call estimation conservative (we use observed token counts
        from the response itself; the cap-firing condition is ``> cap``,
        evaluated AFTER the pair completes, so retry budget naturally
        counts. A purely pre-call estimate would gate on ``max_output_tokens``;
        either is allowed by D-08.).
        """
        tc = meta.get("token_counts") or {}
        in_t = float(tc.get("input", 0))
        out_t = float(tc.get("output", 0))
        rates = RATE_TABLE[source]
        return (
            in_t * rates["input_per_mtok_usd"]
            + out_t * rates["output_per_mtok_usd"]
        ) / 1_000_000

    # -- per-provider call wrappers -----------------------------------------
    def _call_claude(self, crop_path: Path, crop_sha: str, replay_log: Path) -> dict:
        """Wrap Anthropic vision call through the D-10 replay log."""
        with open(crop_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        request = {
            "model":            ANTHROPIC_MODEL_ID,
            "max_tokens":       INFERENCE_CFG["max_output_tokens"],
            "temperature":      INFERENCE_CFG["temperature"],
            "image_bytes_ref":  f"sha256:{crop_sha}",  # D-10: NEVER inline raw bytes
            "prompt":           PROMPT_TEXT,
        }

        def _client_fn(**req):
            return claude_client().messages.create(
                model=req["model"],
                max_tokens=req["max_tokens"],
                temperature=req["temperature"],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": req["prompt"]},
                        ],
                    }
                ],
            )

        def _extract(raw):
            return {
                "response": raw.content[0].text if raw.content else "",
                "response_id": getattr(raw, "id", None),
                "model_version_returned": getattr(
                    raw, "model", ANTHROPIC_MODEL_ID
                ),
                "token_counts": {
                    "input":  raw.usage.input_tokens,
                    "output": raw.usage.output_tokens,
                },
                "finish_reason": getattr(raw, "stop_reason", None),
            }

        return llm_call_with_replay(
            client_fn=_client_fn,
            request=request,
            replay_log=replay_log,
            replay=self.replay,
            extract_response_meta=_extract,
        )

    def _call_gemini(self, crop_path: Path, crop_sha: str, replay_log: Path) -> dict:
        """Wrap Google Gen AI vision call through the D-10 replay log."""
        with open(crop_path, "rb") as f:
            image_bytes = f.read()
        request = {
            "model":             GEMINI_MODEL_ID,
            "max_output_tokens": INFERENCE_CFG["max_output_tokens"],
            "temperature":       INFERENCE_CFG["temperature"],
            "seed":              INFERENCE_CFG["seed"],
            "image_bytes_ref":   f"sha256:{crop_sha}",  # D-10: NEVER inline raw bytes
            "prompt":            PROMPT_TEXT,
        }

        def _client_fn(**req):
            from google.genai import types  # lazy: keeps mocked tests SDK-free

            return gemini_client().models.generate_content(
                model=req["model"],
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    req["prompt"],
                ],
                config=types.GenerateContentConfig(
                    temperature=req["temperature"],
                    seed=req["seed"],
                    max_output_tokens=req["max_output_tokens"],
                ),
            )

        def _extract(raw):
            u = getattr(raw, "usage_metadata", None)
            return {
                "response":      raw.text or "",
                "response_id":   getattr(raw, "response_id", None),
                "model_version_returned": getattr(
                    raw, "model_version", GEMINI_MODEL_ID
                ),
                "token_counts":  {
                    "input":  getattr(u, "prompt_token_count", 0) if u else 0,
                    "output": getattr(u, "candidates_token_count", 0) if u else 0,
                },
                "finish_reason": str(getattr(raw, "finish_reason", None)),
            }

        return llm_call_with_replay(
            client_fn=_client_fn,
            request=request,
            replay_log=replay_log,
            replay=self.replay,
            extract_response_meta=_extract,
        )

    # -- run_meta extension (D-19) -----------------------------------------
    def _compose_run_meta(self) -> dict:
        """Extend the base default with BL-01 specifics (D-19)."""
        base = super()._compose_run_meta()
        base["hostname"] = socket.gethostname()
        base["sibling_git_sha"] = self._read_git_sha()
        base["pins"] = {
            "kraken_model_hash":        KRAKEN_MODEL_HASH,  # shared segmentation
            "nakdimon_model_hash":      None,
            "dictabert_model_revision": None,
            "llm_pin_md_hash": (
                hashlib.sha256(LLM_PIN_MD.read_bytes()).hexdigest()[:16]
                if LLM_PIN_MD.exists()
                else None
            ),
        }
        base["budget"] = {
            "cap_per_folio":       BUDGET_CFG["cap_per_folio_usd"],
            "cap_run":             BUDGET_CFG["cap_run_usd"],
            "used_total":          round(self._used_total_usd, 6),
            "rate_table_snapshot": RATE_TABLE,
        }
        base["combine"] = {
            "tie_break_total":   self._tie_breaks_total,
            "tie_break_winners": dict(self._winners),
        }
        base["folios"] = self._folio_meta
        return base

    @staticmethod
    def _read_git_sha() -> str | None:
        """Best-effort sibling-repo HEAD sha for run_meta provenance.

        Returns None on any failure so a CI environment without git history
        doesn't break runs.
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
