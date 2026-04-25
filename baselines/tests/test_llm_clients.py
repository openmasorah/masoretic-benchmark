"""BL-01 Task 1 unit tests: _llm_clients module + llm_vision.config.yaml + LLM_PIN.md.

Coverage (per plan 03-07 Task 1 behavior):
- T1: module-level constants importable + match YAML
- T2: claude_client() raises KeyError when ANTHROPIC_API_KEY unset (B-4 strict)
- T3: gemini_client() raises KeyError when GOOGLE_API_KEY unset (B-4 strict)
- T4: llm_vision.config.yaml parses cleanly; rate table has Claude + Gemini;
      no abbyy_engine / abbyyfr_id keys (active config is two-source only)
- T5: LLM_PIN.md mirrors NAKDIMON_PIN.md table format and pins both models
- T6: _llm_clients source has no .get() fallback for API keys (grep-style)
"""

from __future__ import annotations

import importlib
import os
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
LLM_PIN_MD = REPO_ROOT / "baselines" / "LLM_PIN.md"
CONFIG_YAML = REPO_ROOT / "baselines" / "llm_vision.config.yaml"
CLIENTS_PY = REPO_ROOT / "baselines" / "src" / "baselines" / "_llm_clients.py"


# ----------------------------------------------------------------------
# T1: module-level constants
# ----------------------------------------------------------------------


def test_module_constants_match_yaml():
    """Module constants ANTHROPIC_MODEL_ID / GEMINI_MODEL_ID / INFERENCE_CFG /
    BUDGET_CFG / RATE_TABLE are loaded from llm_vision.config.yaml at import."""
    # Set env vars so import succeeds even though clients are not constructed
    # at import time (lru_cache on factory).
    os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-for-import")
    os.environ.setdefault("GOOGLE_API_KEY", "dummy-for-import")

    from baselines import _llm_clients as m

    assert m.ANTHROPIC_MODEL_ID == "claude-opus-4-7", m.ANTHROPIC_MODEL_ID
    assert m.GEMINI_MODEL_ID == "gemini-2.5-pro", m.GEMINI_MODEL_ID
    assert m.INFERENCE_CFG["temperature"] == 0
    assert m.INFERENCE_CFG["seed"] == 0
    assert m.INFERENCE_CFG["max_output_tokens"] == 2048
    assert m.BUDGET_CFG["cap_per_folio_usd"] > 0
    assert m.BUDGET_CFG["cap_run_usd"] > 0
    assert "claude" in m.RATE_TABLE
    assert "gemini" in m.RATE_TABLE
    # AbbyyFR explicitly NOT a configured source per A-2
    assert "abbyy" not in m.RATE_TABLE
    assert "abbyyfr" not in m.RATE_TABLE


# ----------------------------------------------------------------------
# T2 + T3: B-4 strict env-var policy
# ----------------------------------------------------------------------


def _reload_llm_clients():
    """Force a fresh import + clear lru_cache so the env-var deletion below
    actually exercises the os.environ[KEY] lookup."""
    import baselines._llm_clients as m

    importlib.reload(m)
    m.claude_client.cache_clear()
    m.gemini_client.cache_clear()
    return m


def test_claude_client_raises_KeyError_when_env_var_unset(monkeypatch):
    """B-4 strict: missing ANTHROPIC_API_KEY -> KeyError (NOT None, NOT
    a custom default)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-for-import")
    m = _reload_llm_clients()
    with pytest.raises(KeyError, match="ANTHROPIC_API_KEY"):
        m.claude_client()


def test_gemini_client_raises_KeyError_when_env_var_unset(monkeypatch):
    """B-4 strict: missing GOOGLE_API_KEY -> KeyError."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-for-import")
    m = _reload_llm_clients()
    with pytest.raises(KeyError, match="GOOGLE_API_KEY"):
        m.gemini_client()


# ----------------------------------------------------------------------
# T4: config YAML shape
# ----------------------------------------------------------------------


def test_llm_vision_config_yaml_parses_cleanly():
    import yaml

    with open(CONFIG_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert isinstance(cfg["budget"]["cap_per_folio_usd"], (int, float))
    assert cfg["budget"]["cap_per_folio_usd"] > 0
    assert cfg["budget"]["cap_run_usd"] > 0
    assert {"claude", "gemini"} <= set(cfg["models"].keys())
    # AbbyyFR is NOT a configured source (the dropped-rationale comment is fine
    # but no abbyyfr_id / abbyy_engine / abbyyfr_input_per_mtok keys exist)
    text = CONFIG_YAML.read_text(encoding="utf-8")
    forbidden_keys = re.compile(
        r"\babbyyfr_input_per_mtok\b|\babbyyfr_id\b|\babbyy_engine\b"
    )
    assert not forbidden_keys.search(text), (
        "active YAML config must not reference AbbyyFR as a configured source"
    )


def test_llm_vision_config_yaml_pricing_metadata_recorded():
    """Pricing-page URL + retrieval date as YAML comments — provider price
    changes are a documented re-pin event, not silent drift (D-08 / D-09)."""
    text = CONFIG_YAML.read_text(encoding="utf-8")
    assert "anthropic.com/pricing" in text
    assert "ai.google.dev/pricing" in text
    assert "Retrieved" in text  # retrieval date marker present


# ----------------------------------------------------------------------
# T5: LLM_PIN.md
# ----------------------------------------------------------------------


def test_llm_pin_md_pins_both_models():
    text = LLM_PIN_MD.read_text(encoding="utf-8")
    assert "claude-opus-4-7" in text
    assert "gemini-2.5-pro" in text
    # Mirrors NAKDIMON_PIN.md / KRAKEN_PIN.md — append-only header + table
    assert "Append-only" in text
    # Initial Phase 3 row dated
    assert "2026-04-25" in text


def test_llm_pin_md_mentions_abbyy_drop_rationale():
    """The dropped-AbbyyFR rationale is captured here (paper-evidence trail)."""
    text = LLM_PIN_MD.read_text(encoding="utf-8")
    assert re.search(r"AbbyyFR.*dropped", text, re.IGNORECASE | re.DOTALL)


# ----------------------------------------------------------------------
# T6: B-4 grep — no .get() fallback in clients source
# ----------------------------------------------------------------------


def test_no_dot_get_fallback_for_api_keys():
    """Source-level invariant: ``os.environ.get("ANTHROPIC_API_KEY", ...)``
    or ``os.environ.get("GOOGLE_API_KEY", ...)`` must NOT appear — B-4 strict.

    Allowed: ``os.environ["ANTHROPIC_API_KEY"]`` (raises KeyError on missing).
    """
    text = CLIENTS_PY.read_text(encoding="utf-8")
    bad_pattern = re.compile(
        r'\.get\(\s*"(?:ANTHROPIC_API_KEY|GOOGLE_API_KEY)"', re.MULTILINE
    )
    assert not bad_pattern.search(text), (
        "B-4 strict: API keys must use os.environ[KEY] (no .get() fallback)"
    )
    # Positive: BOTH bracket-form lookups are present
    assert 'os.environ["ANTHROPIC_API_KEY"]' in text
    assert 'os.environ["GOOGLE_API_KEY"]' in text
