"""Phase 03.1 A-02 cost-cap + retry-billing tests.

Pin numerical values: per_folio=$5.00, per_run=$30.00 (locked 2026-04-25).
Pin retry billing: max_retries=0 on both clients; custom retry loop bills
each attempt against the budget pool BEFORE invoking the SDK (Pitfall 4).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests._fake_manifest import FakeFolio, FakeManifest

# ---------------------------------------------------------------------------
# Per-folio cap raises BudgetExceeded at $5.01
# ---------------------------------------------------------------------------


def test_per_folio_cap_raises_at_5_01(tmp_path):
    """A-02: per-folio cap = $5.00 (locked 2026-04-25). $5.01 simulated
    spend trips BudgetExceeded with the per-folio message + numeric cap."""
    from baselines._errors import BudgetExceeded
    from baselines.llm_vision import LLMVisionBaseline

    manifest = FakeManifest(
        folios=[FakeFolio(id="leningrad_devarim_F118B_fixture")],
        expected_reports_per_baseline={"llm_vision": 1},
    )

    bl = LLMVisionBaseline.__new__(LLMVisionBaseline)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = False
    bl.kraken_model_path = tmp_path / "fake.mlmodel"
    bl.image_cache = tmp_path / "image-cache"
    bl._used_total_usd = 0.0
    bl._cost_caps = bl._resolve_cost_caps()

    # Simulate folio_used = $5.01 just past the cap.
    with pytest.raises(BudgetExceeded, match=r"per-folio.*5\.0"):
        bl._enforce_budget(5.01, folio_id="leningrad_devarim_F118B_fixture")


# ---------------------------------------------------------------------------
# Per-run cap raises BudgetExceeded at $30.01
# ---------------------------------------------------------------------------


def test_per_run_cap_raises_at_30_01(tmp_path):
    """A-02: per-run cap = $30.00 (locked 2026-04-25). $30.01 cumulative
    spend trips BudgetExceeded with the per-run message + numeric cap."""
    from baselines._errors import BudgetExceeded
    from baselines.llm_vision import LLMVisionBaseline

    manifest = FakeManifest(
        folios=[FakeFolio(id="leningrad_devarim_F118B_fixture")],
        expected_reports_per_baseline={"llm_vision": 1},
    )

    bl = LLMVisionBaseline.__new__(LLMVisionBaseline)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = False
    bl.kraken_model_path = tmp_path / "fake.mlmodel"
    bl.image_cache = tmp_path / "image-cache"
    bl._used_total_usd = 30.01
    bl._cost_caps = bl._resolve_cost_caps()

    with pytest.raises(BudgetExceeded, match=r"per-run.*30\.0"):
        bl._enforce_budget(0.01, folio_id="leningrad_devarim_F118B_fixture")


# ---------------------------------------------------------------------------
# max_retries=0 on both clients (AST/source check)
# ---------------------------------------------------------------------------


def test_max_retries_zero_on_clients():
    """Pitfall 4: SDK retries DISABLED on both clients. The clients factory
    source MUST contain ``max_retries=0`` for Anthropic AND ``retry_count: 0``
    in the http_options for google-genai."""
    text = (
        Path(__file__).resolve().parents[1] / "src" / "baselines" / "_llm_clients.py"
    ).read_text(encoding="utf-8")
    assert "max_retries=0" in text, "anthropic.Anthropic(...) must pass max_retries=0 (Pitfall 4)"
    assert "retry_count" in text and "0" in text, (
        "genai.Client(...) must disable SDK retries via http_options (Pitfall 4)"
    )


# ---------------------------------------------------------------------------
# Retry consumption metered (each attempt bills budget BEFORE SDK invoke)
# ---------------------------------------------------------------------------


class _FakeBudget:
    """Minimal budget pool with charge() raising BudgetExceeded on cap."""

    def __init__(self, cap_per_folio: float = 5.00, cap_run: float = 30.00):
        self.cap_per_folio = cap_per_folio
        self.cap_run = cap_run
        self.spent_folio = 0.0
        self.spent_run = 0.0
        self.charges: list[float] = []

    def charge(self, amount: float, *, source: str) -> None:
        from baselines._errors import BudgetExceeded

        self.charges.append(amount)
        self.spent_folio += amount
        self.spent_run += amount
        if self.spent_folio > self.cap_per_folio:
            raise BudgetExceeded(f"per-folio cap exceeded: {self.spent_folio}")
        if self.spent_run > self.cap_run:
            raise BudgetExceeded(f"per-run cap exceeded: {self.spent_run}")


def test_retry_consumption_metered():
    """Pitfall 4: SDK call raises a transient error on first attempt; the
    retry loop rebills BEFORE the second attempt. Both attempts count
    against the budget pool — invisible-spend is impossible."""
    from baselines._llm_clients import call_with_retry_and_billing

    # Build a fake transient-error class. We register it via _retryable_errors
    # surface by simulating "retry would catch it".
    class _Transient(Exception):
        pass

    # Patch _retryable_errors to include our fake transient.
    import baselines._llm_clients as m

    original = m._retryable_errors
    m._retryable_errors = lambda: (_Transient,)
    try:
        budget = _FakeBudget()
        rate_table = {"claude": {"input_per_mtok_usd": 5.00, "output_per_mtok_usd": 25.00}}
        request = {
            "expected_input_tokens": 100_000,  # 0.50 USD per attempt
            "expected_output_tokens": 0,
        }

        attempts = {"n": 0}

        def client_fn(req):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise _Transient("simulated rate-limit")
            return MagicMock(text="ok")

        response, total = call_with_retry_and_billing(
            client_fn=client_fn,
            request=request,
            budget=budget,
            rate_table=rate_table,
            source="claude",
            max_attempts=3,
            backoff_base_s=0.0,  # zero backoff in test
        )

        # Two attempts -> two bills against the budget pool.
        assert attempts["n"] == 2
        assert len(budget.charges) == 2
        # Each charge is ~$0.50 (100_000 input tokens * $5/M).
        assert all(abs(c - 0.50) < 1e-9 for c in budget.charges), budget.charges
        # Cumulative cost returned reflects BOTH attempts.
        assert abs(total - 1.00) < 1e-9, total
    finally:
        m._retryable_errors = original


# ---------------------------------------------------------------------------
# Manifest lacks cost_caps_usd -> BudgetExceeded preflight gate
# ---------------------------------------------------------------------------


def test_manifest_lacks_cost_caps_raises_budgetexceeded(tmp_path):
    """A-02 preflight gate: if the manifest lacks cost_caps_usd, BL-01
    init MUST raise BudgetExceeded with the canonical preflight message."""
    from baselines._errors import BudgetExceeded
    from baselines.llm_vision import LLMVisionBaseline

    # FakeManifest with cost_caps_usd explicitly cleared.
    manifest = FakeManifest(
        folios=[FakeFolio(id="leningrad_devarim_F118B_fixture")],
        expected_reports_per_baseline={"llm_vision": 1},
        cost_caps_usd=None,  # type: ignore[arg-type]
    )

    bl = LLMVisionBaseline.__new__(LLMVisionBaseline)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = False
    bl.kraken_model_path = tmp_path / "fake.mlmodel"
    bl.image_cache = tmp_path / "image-cache"
    bl._used_total_usd = 0.0

    with pytest.raises(BudgetExceeded, match="manifest cost_caps_usd not seeded"):
        bl._cost_caps = bl._resolve_cost_caps()
