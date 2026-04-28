"""BL-01 LLMVisionBaseline mocked unit tests.

Mirrors the BL-02/03/04 mocked-unit pattern: tests construct the subclass
via cls.__new__ + attribute assignment so we bypass real Manifest.load
(FakeManifest is enough). Anthropic + Google clients are fully mocked at
the call boundary; PIL is stubbed out via patches against
``baselines.llm_vision.fetch_image`` / ``image_sha256`` / the inline
``Image.open`` import (we patch ``PIL.Image.open`` directly).

Coverage (per plan 03-07 Task 3 behavior):
- T1: agreement happy path. Both LLMs return identical Hebrew; Claude wins
      (no tie-break); replay log has TWO records (one Claude, one Gemini);
      image bytes referenced by sha256 in the replay request.
- T2: tier-1 disagreement -> Claude wins alphabetically; tier1=tier2=tier3
      ALL come from Claude (no tier-mixing); llm_tie_breaks=1.
- T3: D-08 budget cap fires; BudgetExceeded raised; results/llm_vision/
      NOT created; results/.in_progress/llm_vision/ preserved.
- T4: D-13a ScopeViolation raised BEFORE any LLM client instantiated.
- T6: B-4 strict — KeyError on missing ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from baselines._base import LineRecord

from tests._fake_manifest import FakeFolio, FakeManifest

# ----------------------------------------------------------------------
# PIL stub injected into sys.modules so the lazy "from PIL import Image"
# inside infer_folio resolves to a MagicMock without requiring Pillow.
# ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_pil(monkeypatch):
    """Inject a fake PIL.Image module so the lazy import inside
    LLMVisionBaseline.infer_folio works in environments without Pillow.
    The fixture replaces the top-level "PIL" and "PIL.Image" entries in
    sys.modules and restores them on teardown.

    The chained ``Image.open(p).convert("RGB").crop(bbox).save(out_path)``
    idiom from infer_folio is wired so ``save(out_path)`` writes a tiny
    stub byte string to disk — that way the subsequent
    ``open(crop_path, "rb")`` inside _call_claude / _call_gemini sees a
    real file (the bytes are irrelevant; image_sha256 is patched away)."""
    fake_pil = MagicMock()
    fake_image_module = MagicMock()
    fake_img_obj = MagicMock()
    fake_img_obj.convert.return_value = fake_img_obj
    fake_img_obj.crop.return_value = fake_img_obj

    def _save(out_path, *args, **kwargs):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"\xff\xd8\xff\xe0")  # minimal JPEG-ish stub

    fake_img_obj.save = _save
    fake_image_module.open = MagicMock(return_value=fake_img_obj)
    fake_pil.Image = fake_image_module

    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image_module)

    # Also stub google.genai.types — _call_gemini's inner _client_fn does
    # `from google.genai import types` for Part.from_bytes(...). The real
    # genai client is patched at baselines.llm_vision.gemini_client, so
    # types only needs to provide a no-op Part / GenerateContentConfig.
    fake_google = MagicMock()
    fake_genai = MagicMock()
    fake_types = MagicMock()
    fake_types.Part.from_bytes = MagicMock(return_value=MagicMock(name="Part"))
    fake_types.GenerateContentConfig = MagicMock(name="GenerateContentConfig")
    fake_genai.types = fake_types
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)

    yield fake_image_module


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _ctor(tmp_path: Path, manifest: FakeManifest, replay: bool = False):
    """Construct LLMVisionBaseline bypassing Manifest.load."""
    from baselines.llm_vision import LLMVisionBaseline

    bl = LLMVisionBaseline.__new__(LLMVisionBaseline)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = replay
    bl.kraken_model_path = tmp_path / "fake.mlmodel"
    bl.image_cache = tmp_path / "image-cache"
    from datetime import datetime

    bl._started_at = datetime.now(UTC).isoformat(timespec="seconds")
    bl._folio_meta = {}
    bl._used_total_usd = 0.0
    bl._tie_breaks_total = 0
    bl._winners = {"claude": 0, "gemini": 0}
    # Phase 03.1 A-02: __init__ would read cost_caps from manifest; mirror
    # that here since we bypass __init__.
    bl._cost_caps = bl._resolve_cost_caps()
    return bl


def _kraken_lines(folio_id: str, n: int = 1) -> list[LineRecord]:
    """Synthetic Kraken segmentation output (we mock recognize_lines)."""
    return [
        LineRecord(
            line_id=f"{folio_id}_L{i + 1:03d}",
            bbox=(10, 10 + i * 50, 500, 60 + i * 50),
            tier1="kraken-text",
            tier2="kraken-text",
            tier3="kraken-text",
            tier4_records=tuple(),
            kraken_confidence=0.9,
        )
        for i in range(n)
    ]


def _claude_response(text: str, in_t: int = 100, out_t: int = 30) -> MagicMock:
    """Anthropic-shaped response."""
    r = MagicMock()
    r.content = [MagicMock(text=text)]
    r.id = "msg_01abcdef"
    r.model = "claude-opus-4-7-20260101"
    r.stop_reason = "end_turn"
    r.usage = MagicMock(input_tokens=in_t, output_tokens=out_t)
    return r


def _gemini_response(text: str, in_t: int = 100, out_t: int = 30) -> MagicMock:
    """Google Gen AI-shaped response."""
    r = MagicMock()
    r.text = text
    r.response_id = "gemini-resp-abc"
    r.model_version = "gemini-2.5-pro-002"
    r.finish_reason = "STOP"
    r.usage_metadata = MagicMock(prompt_token_count=in_t, candidates_token_count=out_t)
    return r


def _patches(claude_text: str, gemini_text: str, kraken_n: int = 1):
    """Common patch set for unit tests: stubs out image I/O, Kraken,
    PIL.Image, and both LLM clients."""
    fake_image_path = Path("/tmp/fake-image.jpg")  # never read since we patch open
    fake_kraken = _kraken_lines("fid", n=kraken_n)

    # PIL.Image.open returns an object whose .convert().crop().save() is a no-op.
    fake_pil_img = MagicMock()
    fake_pil_img.convert.return_value = fake_pil_img
    fake_pil_img.crop.return_value = fake_pil_img
    fake_pil_img.save = MagicMock()

    fake_claude = MagicMock()
    fake_claude.messages.create = MagicMock(return_value=_claude_response(claude_text))
    fake_gemini = MagicMock()
    fake_gemini.models.generate_content = MagicMock(return_value=_gemini_response(gemini_text))

    return {
        "fake_image_path": fake_image_path,
        "fake_kraken": fake_kraken,
        "fake_pil_img": fake_pil_img,
        "fake_claude": fake_claude,
        "fake_gemini": fake_gemini,
    }


# ----------------------------------------------------------------------
# T1: agreement happy path
# ----------------------------------------------------------------------


def test_llm_vision_agreement_writes_prediction_and_replay_log(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-claude-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-gemini-key")

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"llm_vision": 1},
    )
    p = _patches(claude_text="שמע", gemini_text="שמע", kraken_n=2)

    # Use a real tiny image file so PIL.Image.open works without mocking
    # (we want to exercise the lazy import path).
    real_img = tmp_path / "image-cache" / f"{fid}.jpg"
    real_img.parent.mkdir(parents=True, exist_ok=True)
    # Write a 4x4 JPEG via PIL only if PIL is installed; otherwise patch
    # PIL.Image.open. The unit-test environment has no Pillow, so we patch.
    with (
        patch("baselines.llm_vision.fetch_image", return_value=p["fake_image_path"]),
        patch("baselines.llm_vision.image_sha256", return_value="img-sha"),
        patch("baselines.llm_vision.recognize_lines", return_value=p["fake_kraken"]),
        patch("baselines.llm_vision.claude_client", return_value=p["fake_claude"]),
        patch("baselines.llm_vision.gemini_client", return_value=p["fake_gemini"]),
    ):
        bl = _ctor(tmp_path, manifest)
        rc = bl.run()

    assert rc == 0

    # Prediction promoted to results/llm_vision/<folio>.json
    pred_path = tmp_path / "llm_vision" / f"{fid}.json"
    assert pred_path.exists()
    pred = json.loads(pred_path.read_text(encoding="utf-8"))
    assert pred["baseline_id"] == "llm_vision"
    assert pred["folio_id"] == fid
    assert len(pred["lines"]) == 2
    # Tier-1 agreement: Claude chosen, no tie-break
    for line in pred["lines"]:
        assert line["llm_winner"] == "claude"
        assert line["llm_tie_breaks"] == 0
        assert line["tier1"] == line["tier2"] == line["tier3"] == "שמע"

    # Replay log: D-10 — promoted into final dir; one record per LLM per line
    replay_log = tmp_path / "llm_vision" / fid / "llm_calls.jsonl"
    assert replay_log.exists()
    records = [
        json.loads(r) for r in replay_log.read_text(encoding="utf-8").splitlines() if r.strip()
    ]
    assert len(records) == 4, "2 lines × 2 LLMs = 4 records"
    # BOTH providers represented
    models_used = {rec["request"]["model"] for rec in records}
    assert "claude-opus-4-7" in models_used
    assert "gemini-2.5-pro" in models_used
    # D-10: image bytes referenced by sha256, NEVER inlined
    for rec in records:
        assert rec["request"]["image_bytes_ref"].startswith("sha256:")
        assert "image_bytes" not in rec["request"]
        # Provenance present
        assert rec["response_id"]
        assert rec["model_version_returned"]
        assert rec["token_counts"]["input"] > 0

    # run_meta has BL-01 D-19 fields populated
    meta_path = tmp_path / "llm_vision" / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["baseline_id"] == "llm_vision"
    assert meta["pins"]["llm_pin_md_hash"]  # sha256 prefix recorded
    assert meta["pins"]["kraken_model_hash"]  # shared segmentation
    assert meta["budget"]["cap_per_folio"] > 0
    assert meta["budget"]["cap_run"] > 0
    assert meta["budget"]["used_total"] >= 0
    assert meta["combine"]["tie_break_total"] == 0
    assert meta["combine"]["tie_break_winners"] == {"claude": 2, "gemini": 0}


# ----------------------------------------------------------------------
# T2: disagreement -> Claude wins alphabetically, no tier-mixing
# ----------------------------------------------------------------------


def test_llm_vision_disagreement_claude_wins_no_tier_mixing(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_API_KEY", "k")

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"llm_vision": 1},
    )
    claude_text = "שמע ישראל"
    gemini_text = "שמא ישראל"  # tier-1 disagreement on the second consonant
    p = _patches(claude_text=claude_text, gemini_text=gemini_text, kraken_n=1)

    with (
        patch("baselines.llm_vision.fetch_image", return_value=p["fake_image_path"]),
        patch("baselines.llm_vision.image_sha256", return_value="img-sha"),
        patch("baselines.llm_vision.recognize_lines", return_value=p["fake_kraken"]),
        patch("baselines.llm_vision.claude_client", return_value=p["fake_claude"]),
        patch("baselines.llm_vision.gemini_client", return_value=p["fake_gemini"]),
    ):
        bl = _ctor(tmp_path, manifest)
        bl.run()

    pred = json.loads((tmp_path / "llm_vision" / f"{fid}.json").read_text(encoding="utf-8"))
    line = pred["lines"][0]
    assert line["llm_winner"] == "claude"
    assert line["llm_tie_breaks"] == 1
    # ALL tiers come from Claude — Gemini's text appears NOWHERE on the line
    assert line["tier1"] == claude_text
    assert line["tier2"] == claude_text
    assert line["tier3"] == claude_text
    assert gemini_text not in (line["tier1"], line["tier2"], line["tier3"])

    meta = json.loads((tmp_path / "llm_vision" / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["combine"]["tie_break_total"] == 1
    assert meta["combine"]["tie_break_winners"] == {"claude": 1, "gemini": 0}


# ----------------------------------------------------------------------
# T3: D-08 BudgetExceeded leaves sandbox for inspection
# ----------------------------------------------------------------------


def test_llm_vision_budget_cap_fires_and_preserves_sandbox(tmp_path, monkeypatch):
    """Force the per-folio cap by reporting absurd token counts on the
    first line. BudgetExceeded raised; results/llm_vision/ NOT created;
    results/.in_progress/llm_vision/ preserved (atomic-run policy)."""
    from baselines._errors import BudgetExceeded

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_API_KEY", "k")

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"llm_vision": 1},
    )

    # 1B input tokens × $15/Mtok = $15000 — far over the $5/folio cap.
    p = _patches(claude_text="x", gemini_text="x", kraken_n=1)
    p["fake_claude"].messages.create.return_value = _claude_response(
        "x", in_t=1_000_000_000, out_t=1
    )
    p["fake_gemini"].models.generate_content.return_value = _gemini_response("x", in_t=1, out_t=1)

    with (
        patch("baselines.llm_vision.fetch_image", return_value=p["fake_image_path"]),
        patch("baselines.llm_vision.image_sha256", return_value="img-sha"),
        patch("baselines.llm_vision.recognize_lines", return_value=p["fake_kraken"]),
        patch("baselines.llm_vision.claude_client", return_value=p["fake_claude"]),
        patch("baselines.llm_vision.gemini_client", return_value=p["fake_gemini"]),
    ):
        bl = _ctor(tmp_path, manifest)
        with pytest.raises(BudgetExceeded, match="D-08"):
            bl.run()

    # results/llm_vision/ must NOT exist; sandbox preserved (D-14)
    assert not (tmp_path / "llm_vision").exists()
    sandbox = tmp_path / ".in_progress" / "llm_vision"
    assert sandbox.exists()
    # Replay log has at least the two records that DID complete before the cap fired
    replay_log = sandbox / fid / "llm_calls.jsonl"
    assert replay_log.exists()


# ----------------------------------------------------------------------
# T4: D-13a ScopeViolation BEFORE any LLM client instantiated
# ----------------------------------------------------------------------


def test_llm_vision_scope_violation_fires_before_llm_clients(tmp_path, monkeypatch):
    """Out-of-scope folio -> ScopeViolation raised by _preflight; verify
    via mocks that NEITHER claude_client nor gemini_client was invoked."""
    from baselines._errors import ScopeViolation

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_API_KEY", "k")

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"llm_vision": 1},
    )

    with (
        patch("baselines.llm_vision.claude_client") as m_claude,
        patch("baselines.llm_vision.gemini_client") as m_gemini,
        patch("baselines.llm_vision.recognize_lines") as m_rec,
        patch("baselines.llm_vision.fetch_image") as m_fetch,
    ):
        bl = _ctor(tmp_path, manifest)
        with pytest.raises(ScopeViolation, match="BL-08"):
            bl.run(folio_ids=["non_existent_folio"])
        assert m_claude.call_count == 0, "claude_client must NOT be invoked on D-13a"
        assert m_gemini.call_count == 0, "gemini_client must NOT be invoked on D-13a"
        assert m_rec.call_count == 0
        assert m_fetch.call_count == 0

    assert not (tmp_path / "llm_vision").exists()


# ----------------------------------------------------------------------
# T6: B-4 strict KeyError on missing ANTHROPIC_API_KEY
# ----------------------------------------------------------------------


def test_llm_vision_keyerror_on_missing_anthropic_api_key(tmp_path, monkeypatch):
    """B-4 strict: missing env var -> KeyError. We exercise this via the
    _llm_clients module, since llm_vision.py defers to it. Force lru_cache
    clear + reimport so the env-var deletion is visible."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    import importlib

    import baselines._llm_clients as m

    importlib.reload(m)
    m.claude_client.cache_clear()
    with pytest.raises(KeyError, match="ANTHROPIC_API_KEY"):
        m.claude_client()


# ----------------------------------------------------------------------
# AST invariant cross-check (defense-in-depth, mirrors BL-02 pattern)
# ----------------------------------------------------------------------


def test_llm_vision_baseline_id_is_canonical():
    from baselines.llm_vision import LLMVisionBaseline

    assert LLMVisionBaseline.BASELINE_ID == "llm_vision"


def test_llm_vision_does_not_override_run():
    """D-12 structural lock — pinned by AST-walk in test_invariants.py too."""
    from baselines._base import BaselineBase
    from baselines.llm_vision import LLMVisionBaseline

    assert "run" not in LLMVisionBaseline.__dict__, (
        "D-12: LLMVisionBaseline must NOT override run()"
    )
    assert LLMVisionBaseline.run is BaselineBase.run


def test_llm_vision_prompt_text_d05_clean():
    """D-05 contamination boundary: PROMPT_TEXT must contain no UXLC text,
    no verse content, no GT-derived signal. Defense-in-depth grep — the
    real enforcement is Plan 03-08's contamination test against
    llm_calls.jsonl."""
    from baselines.llm_vision import PROMPT_TEXT

    # No verse references, no Hebrew Bible book names embedded in the prompt
    forbidden = [
        "shema",
        "deuteronomy",
        "devarim",
        "uxlc",
        "verse_ref",
        "1:1",
        "6:4",
    ]
    lower = PROMPT_TEXT.lower()
    for needle in forbidden:
        assert needle not in lower, f"PROMPT_TEXT contains forbidden token {needle!r}"
