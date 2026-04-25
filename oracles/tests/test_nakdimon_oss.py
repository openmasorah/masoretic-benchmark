"""Unit + live-oracle tests for oracles.nakdimon_oss (ORA-01)."""

from __future__ import annotations

import pytest

from masoretic_eval.metrics.nakdimon import nakdimon_factoring


def test_module_imports_and_exposes_public_api():
    from oracles.nakdimon_oss import MODEL_HASH, diacritize, disagreement_rate

    assert callable(diacritize)
    assert callable(disagreement_rate)
    assert isinstance(MODEL_HASH, str)
    assert len(MODEL_HASH) == 16
    assert all(c in "0123456789abcdef" for c in MODEL_HASH)


def test_disagreement_rate_math_with_mocked_oracle(monkeypatch):
    # Use two known nikkud strings: prediction with one set of vowels;
    # patched oracle output with the same skeleton but slightly different vowels.
    prediction = "שָׁמַע יִשְׂרָאֵל"
    oracle_canned = "שָׁמָע יִשְׂרָאֵל"  # different qamatz/patach — distinct DEC
    monkeypatch.setattr("oracles.nakdimon_oss.diacritize", lambda c: oracle_canned)

    from oracles.nakdimon_oss import disagreement_rate

    rate, meta = disagreement_rate(prediction)
    # Check math: rate = 1 - DEC(prediction, oracle_canned)
    expected_dec = nakdimon_factoring(prediction, oracle_canned).dec
    assert rate == pytest.approx(1.0 - expected_dec, abs=1e-9)
    assert 0.0 <= rate <= 1.0
    assert meta["dec"] == pytest.approx(expected_dec, abs=1e-9)


def test_audit_meta_shape(monkeypatch):
    # Use a passthrough oracle so we don't need TF loaded.
    monkeypatch.setattr("oracles.nakdimon_oss.diacritize", lambda c: c)

    from oracles.nakdimon_oss import MODEL_HASH, disagreement_rate

    rate, meta = disagreement_rate("שָׁלוֹם")
    assert meta["oracle"] == "nakdimon_oss"
    assert meta["model_hash"] == MODEL_HASH
    assert isinstance(meta["input_cp_count"], int) and meta["input_cp_count"] > 0
    assert isinstance(meta["oracle_cp_count"], int) and meta["oracle_cp_count"] > 0
    assert isinstance(meta["dec"], float)
    assert 0.0 <= rate <= 1.0


def test_cgj_preserved_through_diacritize(monkeypatch):
    """Pitfall 3 contract: diacritize() must preserve U+034F CGJ.

    CGJ is consonantal-side metadata that Nakdimon leaves untouched upstream.
    We verify *our* module's contract (the diacritize wrapper): if the
    underlying nakdimon.diacritize returns a string containing CGJ, our
    diacritize() returns it unchanged.

    Note the scorer's strip_to_consonantal does NOT preserve CGJ (CGJ is
    outside the 0x05D0-0x05EA consonant range), so disagreement_rate's
    skeleton-to-oracle path will not carry CGJ. The oracle-level
    guarantee is specifically about diacritize() itself — this is the
    must-have truth documented in the plan.
    """
    cgj = "͏"
    input_with_cgj = f"א{cgj}ב"
    # Emulate a Nakdimon that faithfully echoes CGJ-bearing input.
    monkeypatch.setattr("nakdimon.diacritize", lambda text: text)

    from oracles.nakdimon_oss import diacritize

    out = diacritize(input_with_cgj)
    assert cgj in out, f"CGJ stripped by diacritize wrapper: {out!r}"
    assert out == input_with_cgj


@pytest.mark.live_oracles
def test_live_diacritize_smoke():
    from oracles.nakdimon_oss import diacritize

    out = diacritize("שמע ישראל")
    assert isinstance(out, str)
    assert len(out) > 0


@pytest.mark.live_oracles
def test_live_disagreement_rate_in_unit_interval():
    from oracles.nakdimon_oss import disagreement_rate

    rate, meta = disagreement_rate("שָׁמַע יִשְׂרָאֵל יְהוָה אֱלֹהֵינוּ יְהוָה אֶחָד")
    assert 0.0 <= rate <= 1.0
    assert meta["oracle"] == "nakdimon_oss"
