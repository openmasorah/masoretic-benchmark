"""Unit + live-oracle tests for oracles.dictabert (ORA-03)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_module_imports_constants_only():
    # Patch HF entry points BEFORE importing oracles.dictabert to prove laziness.
    with patch("transformers.AutoTokenizer") as tok_cls, patch("transformers.AutoModel") as mdl_cls:
        import importlib

        import oracles.dictabert as dm

        importlib.reload(dm)  # ensure fresh module-level execution under our patches
        assert dm.MODEL_ID == "dicta-il/dictabert-large-char-menaked"
        assert dm.MODEL_REVISION == "d311fbf7c403e50b040440e4859ac78064d025d0"
        tok_cls.from_pretrained.assert_not_called()
        mdl_cls.from_pretrained.assert_not_called()


def test_diacritize_calls_predict_with_pinned_args(monkeypatch):
    from oracles import dictabert as dm

    # Clear lru_cache so we can substitute _load
    dm._load.cache_clear()
    captured = {}

    class _MockTok:
        pass

    class _MockModel:
        def predict(self, sentences, tokenizer):
            captured["sentences"] = sentences
            captured["tok_type"] = type(tokenizer).__name__
            return ["שָׁלוֹם"]

    monkeypatch.setattr(dm, "_load", lambda: (_MockTok(), _MockModel()))
    out = dm.diacritize("שלום")
    assert out == "שָׁלוֹם"
    assert captured["sentences"] == ["שלום"]
    assert captured["tok_type"] == "_MockTok"


def test_load_uses_pinned_revision_and_cache_dir(monkeypatch):
    from oracles import dictabert as dm

    dm._load.cache_clear()
    tok_mock = MagicMock(name="from_pretrained_tok")
    mdl_mock = MagicMock(name="from_pretrained_mdl")
    # Make sure mdl.eval() is callable
    loaded_mdl = MagicMock()
    loaded_mdl.eval.return_value = None
    mdl_mock.return_value = loaded_mdl
    monkeypatch.setattr(dm.AutoTokenizer, "from_pretrained", tok_mock)
    monkeypatch.setattr(dm.AutoModel, "from_pretrained", mdl_mock)
    dm._load()
    # Assert revision pinned
    tok_kwargs = tok_mock.call_args.kwargs
    mdl_kwargs = mdl_mock.call_args.kwargs
    assert tok_kwargs.get("revision") == "d311fbf7c403e50b040440e4859ac78064d025d0"
    assert mdl_kwargs.get("revision") == "d311fbf7c403e50b040440e4859ac78064d025d0"
    assert mdl_kwargs.get("trust_remote_code") is True
    # Assert cache_dir lands under oracles/.cache/dictabert
    assert "oracles/.cache/dictabert" in tok_kwargs.get("cache_dir", "")
    assert "oracles/.cache/dictabert" in mdl_kwargs.get("cache_dir", "")


def test_no_disagreement_rate_in_module():
    from oracles import dictabert as dm

    assert not hasattr(dm, "disagreement_rate"), "D-26 violation"


def test_diacritize_handles_empty_predict_output(monkeypatch):
    from oracles import dictabert as dm

    dm._load.cache_clear()

    class _MockModel:
        def predict(self, sentences, tokenizer):
            return []

    monkeypatch.setattr(dm, "_load", lambda: (object(), _MockModel()))
    assert dm.diacritize("anything") == ""


@pytest.mark.live_oracles
def test_live_diacritize_smoke():
    from oracles.dictabert import diacritize

    out = diacritize("שלום עליכם")
    assert isinstance(out, str)
    assert len(out) > 0
