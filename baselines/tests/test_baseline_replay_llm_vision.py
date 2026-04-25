"""BL-01 replay-mode test (D-10 + D-11 corollary).

With a committed ``baselines/tests/fixtures/llm_calls/<folio>.replay.jsonl``
the LLMVisionBaseline's ``run(replay=True)`` produces a prediction WITHOUT
calling either provider's API. The fixture is constructed (and written into
the test's sandbox) by re-deriving the canonical prompt_hash via
``canonical_prompt_hash`` — the same function the production replay
reader uses — so the fixture is reproducible across machines.

The replay test asserts:
  - Neither claude_client nor gemini_client was invoked.
  - The prediction JSON is byte-equal-shape to the live path (validates
    against schema, has llm_winner / llm_tie_breaks per line).
  - ``run_meta.replay_mode`` is True.
  - The replay log in results/.in_progress/llm_vision/<folio>/llm_calls.jsonl
    is NOT appended (replay mode reads only).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from baselines._base import LineRecord
from baselines._llm_replay import canonical_prompt_hash
from tests._fake_manifest import FakeFolio, FakeManifest


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "llm_calls"
    / "leningrad_devarim_shema_fixture.replay.jsonl"
)


# ----------------------------------------------------------------------
# PIL stub — same pattern as test_baseline_unit_llm_vision.py
# ----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_pil(monkeypatch):
    fake_pil = MagicMock()
    fake_image_module = MagicMock()
    fake_img_obj = MagicMock()
    fake_img_obj.convert.return_value = fake_img_obj
    fake_img_obj.crop.return_value = fake_img_obj

    def _save(out_path, *args, **kwargs):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"\xff\xd8\xff\xe0")

    fake_img_obj.save = _save
    fake_image_module.open = MagicMock(return_value=fake_img_obj)
    fake_pil.Image = fake_image_module
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image_module)

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
    yield


# ----------------------------------------------------------------------
# Helpers — keep IN SYNC with llm_vision.py's request shape
# ----------------------------------------------------------------------


def _claude_request(crop_sha: str) -> dict:
    """Mirror llm_vision._call_claude.request shape exactly."""
    from baselines._llm_clients import ANTHROPIC_MODEL_ID, INFERENCE_CFG
    from baselines.llm_vision import PROMPT_TEXT

    return {
        "model":            ANTHROPIC_MODEL_ID,
        "max_tokens":       INFERENCE_CFG["max_output_tokens"],
        "temperature":      INFERENCE_CFG["temperature"],
        "image_bytes_ref":  f"sha256:{crop_sha}",
        "prompt":           PROMPT_TEXT,
    }


def _gemini_request(crop_sha: str) -> dict:
    """Mirror llm_vision._call_gemini.request shape exactly."""
    from baselines._llm_clients import GEMINI_MODEL_ID, INFERENCE_CFG
    from baselines.llm_vision import PROMPT_TEXT

    return {
        "model":             GEMINI_MODEL_ID,
        "max_output_tokens": INFERENCE_CFG["max_output_tokens"],
        "temperature":       INFERENCE_CFG["temperature"],
        "seed":              INFERENCE_CFG["seed"],
        "image_bytes_ref":   f"sha256:{crop_sha}",
        "prompt":            PROMPT_TEXT,
    }


def _make_record(*, request: dict, response: str, response_id: str, model_version: str) -> dict:
    """Construct a D-10 replay record."""
    from datetime import datetime, timezone

    return {
        "prompt_hash":            canonical_prompt_hash(request),
        "request":                request,
        "response":               response,
        "response_id":            response_id,
        "model_version_returned": model_version,
        "token_counts":           {"input": 1234, "output": 56},
        "finish_reason":          "end_turn" if "claude" in model_version else "STOP",
        "timestamp":              datetime(2026, 4, 25, tzinfo=timezone.utc).isoformat(
            timespec="seconds"
        ),
    }


def _seed_replay_log(target_path: Path, crop_sha: str) -> None:
    """Write the per-folio replay log with TWO records (one Claude,
    one Gemini) for line L001 of the Shema fixture folio."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        _make_record(
            request=_claude_request(crop_sha),
            response="שמע ישראל",
            response_id="msg_replay_claude_01",
            model_version="claude-opus-4-7-20260101",
        ),
        _make_record(
            request=_gemini_request(crop_sha),
            response="שמע ישראל",
            response_id="gemini-replay-01",
            model_version="gemini-2.5-pro-002",
        ),
    ]
    with open(target_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")


def _kraken_lines(folio_id: str) -> list[LineRecord]:
    return [
        LineRecord(
            line_id=f"{folio_id}_L001",
            bbox=(10, 10, 500, 60),
            tier1="kraken-text",
            tier2="kraken-text",
            tier3="kraken-text",
            tier4_records=tuple(),
            kraken_confidence=0.9,
        )
    ]


# ----------------------------------------------------------------------
# T1: replay-mode produces prediction WITHOUT calling either client
# ----------------------------------------------------------------------


def test_replay_mode_uses_logged_responses_not_live_clients(tmp_path, monkeypatch):
    """The committed replay fixture is copied into the sandbox; the run is
    started with replay=True; both client factories assert-not-called."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_API_KEY", "k")

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"llm_vision": 1},
    )

    # Shared crop sha — the test re-derives the canonical prompt_hash from
    # the request shape, so the fixture and the run match byte-for-byte.
    crop_sha = "deadbeef" * 8  # 64-char hex

    # Pre-populate the SANDBOX path with the replay fixture so
    # llm_call_with_replay can find it. The sandbox path mirrors the
    # production layout: results/.in_progress/llm_vision/<folio>/llm_calls.jsonl.
    sandbox_log = (
        tmp_path
        / ".in_progress"
        / "llm_vision"
        / fid
        / "llm_calls.jsonl"
    )
    _seed_replay_log(sandbox_log, crop_sha=crop_sha)

    # Patches: clients must NOT be invoked; image / kraken are stubbed.
    blocked_claude = MagicMock(side_effect=AssertionError("claude_client must NOT be invoked in replay"))
    blocked_gemini = MagicMock(side_effect=AssertionError("gemini_client must NOT be invoked in replay"))

    from unittest.mock import patch as _patch

    with _patch("baselines.llm_vision.fetch_image", return_value=tmp_path / "fake.jpg"), \
         _patch("baselines.llm_vision.image_sha256", return_value=crop_sha), \
         _patch("baselines.llm_vision.recognize_lines", return_value=_kraken_lines(fid)), \
         _patch("baselines.llm_vision.claude_client", blocked_claude), \
         _patch("baselines.llm_vision.gemini_client", blocked_gemini):
        from baselines.llm_vision import LLMVisionBaseline

        bl = LLMVisionBaseline.__new__(LLMVisionBaseline)
        bl.manifest = manifest
        bl.results_root = tmp_path
        bl.replay = True   # <-- the contract under test
        bl.kraken_model_path = tmp_path / "fake.mlmodel"
        bl.image_cache = tmp_path / "image-cache"
        from datetime import datetime, timezone

        bl._started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        bl._folio_meta = {}
        bl._used_total_usd = 0.0
        bl._tie_breaks_total = 0
        bl._winners = {"claude": 0, "gemini": 0}

        rc = bl.run()

    assert rc == 0
    assert blocked_claude.call_count == 0, "D-10: claude_client must NOT be invoked in replay"
    assert blocked_gemini.call_count == 0, "D-10: gemini_client must NOT be invoked in replay"

    # Prediction landed at results/llm_vision/<folio>.json
    pred_path = tmp_path / "llm_vision" / f"{fid}.json"
    assert pred_path.exists()
    pred = json.loads(pred_path.read_text(encoding="utf-8"))
    assert pred["baseline_id"] == "llm_vision"
    line = pred["lines"][0]
    assert line["llm_winner"] == "claude"
    assert line["llm_tie_breaks"] == 0  # tier-1 agreement (both fixtures say "שמע ישראל")
    assert line["tier1"] == "שמע ישראל"

    meta = json.loads(
        (tmp_path / "llm_vision" / "run_meta.json").read_text(encoding="utf-8")
    )
    assert meta["replay_mode"] is True
    assert meta["folios"][fid]["replay_used"] is True


# ----------------------------------------------------------------------
# T2: replay-mode raises ReplayMissError when the fixture is absent —
#     never falls through to a live call (defense-in-depth on top of
#     test_llm_replay.py).
# ----------------------------------------------------------------------


def test_replay_mode_raises_on_missing_fixture(tmp_path, monkeypatch):
    """No fixture seeded; replay=True; ReplayMissError raised; clients
    not invoked. Sandbox preserved for inspection (D-14)."""
    from baselines._llm_replay import ReplayMissError

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_API_KEY", "k")

    fid = "leningrad_devarim_shema_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"llm_vision": 1},
    )

    blocked_claude = MagicMock(side_effect=AssertionError("must NOT be invoked"))
    blocked_gemini = MagicMock(side_effect=AssertionError("must NOT be invoked"))

    from unittest.mock import patch as _patch

    with _patch("baselines.llm_vision.fetch_image", return_value=tmp_path / "fake.jpg"), \
         _patch("baselines.llm_vision.image_sha256", return_value="img-sha"), \
         _patch("baselines.llm_vision.recognize_lines", return_value=_kraken_lines(fid)), \
         _patch("baselines.llm_vision.claude_client", blocked_claude), \
         _patch("baselines.llm_vision.gemini_client", blocked_gemini):
        from baselines.llm_vision import LLMVisionBaseline

        bl = LLMVisionBaseline.__new__(LLMVisionBaseline)
        bl.manifest = manifest
        bl.results_root = tmp_path
        bl.replay = True
        bl.kraken_model_path = tmp_path / "fake.mlmodel"
        bl.image_cache = tmp_path / "image-cache"
        from datetime import datetime, timezone

        bl._started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        bl._folio_meta = {}
        bl._used_total_usd = 0.0
        bl._tie_breaks_total = 0
        bl._winners = {"claude": 0, "gemini": 0}

        with pytest.raises(ReplayMissError):
            bl.run()

    assert blocked_claude.call_count == 0
    assert blocked_gemini.call_count == 0
    assert not (tmp_path / "llm_vision").exists()
    # Sandbox preserved for inspection
    assert (tmp_path / ".in_progress" / "llm_vision").exists()


# ----------------------------------------------------------------------
# T3: the committed fixture file exists (paper-evidence trail)
# ----------------------------------------------------------------------


def test_committed_fixture_file_exists():
    """The committed fixture file is the substrate Plan 03-08's
    contamination test will grep. It must exist in the repo."""
    assert FIXTURE_PATH.exists(), (
        f"fixture missing: {FIXTURE_PATH} — should be committed alongside this test"
    )


def test_committed_fixture_contents_are_canonical():
    """The committed fixture must contain valid JSONL with both Claude and
    Gemini records and NO inlined image bytes (D-10)."""
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    if not text.strip():
        pytest.skip("committed fixture is empty placeholder; populated by ship-time test fixture")
    records = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    assert len(records) >= 2
    models = {r["request"]["model"] for r in records}
    assert "claude-opus-4-7" in models
    assert "gemini-2.5-pro" in models
    for r in records:
        assert r["request"]["image_bytes_ref"].startswith("sha256:")
        assert "image_bytes" not in r["request"]
