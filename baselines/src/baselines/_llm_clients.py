"""Anthropic + Google Gen AI client wrappers (BL-01 / D-09 / B-4).

Public surface (load-bearing — `llm_vision.py` imports these names):

    claude_client() -> anthropic.Anthropic   # raises KeyError if ANTHROPIC_API_KEY unset
    gemini_client() -> genai.Client          # raises KeyError if GOOGLE_API_KEY unset
    ANTHROPIC_MODEL_ID, GEMINI_MODEL_ID      # constants from llm_vision.config.yaml
    INFERENCE_CFG, BUDGET_CFG, RATE_TABLE    # parsed config blocks

Phase 1 B-4 carry-forward: API keys read via ``os.environ[KEY]`` with NO
``.get()`` fallback. Missing env var -> KeyError -> non-zero exit.

The provider SDK imports (``anthropic``, ``google.genai``) are lazy — done
inside the ``claude_client`` / ``gemini_client`` factory functions — so the
module imports cleanly in mocked unit tests where the SDKs are not installed.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# _llm_clients.py lives at .../baselines/src/baselines/_llm_clients.py
#   parents[0] = .../baselines/src/baselines
#   parents[1] = .../baselines/src
#   parents[2] = .../baselines
#   parents[3] = sibling repo root (masoretic-benchmark)
REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "baselines" / "llm_vision.config.yaml"


def _load_config() -> dict:
    """Parse ``baselines/llm_vision.config.yaml``.

    PyYAML is imported lazily so the module can be imported (e.g. for
    invariant tests scanning files for symbols) even in environments
    without PyYAML — though the [llm] extra in pyproject.toml installs it.
    """
    import yaml

    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


_CONFIG = _load_config()
ANTHROPIC_MODEL_ID: str = _CONFIG["models"]["claude"]["id"]
GEMINI_MODEL_ID: str = _CONFIG["models"]["gemini"]["id"]
INFERENCE_CFG: dict = _CONFIG["inference"]
BUDGET_CFG: dict = _CONFIG["budget"]
RATE_TABLE: dict = _CONFIG["models"]


@lru_cache(maxsize=1)
def claude_client():
    """Return a cached ``anthropic.Anthropic`` client.

    Reads ``ANTHROPIC_API_KEY`` via ``os.environ[KEY]`` (NO ``.get()`` fallback —
    Phase 1 B-4). KeyError on missing. Env-var check comes BEFORE the SDK
    import so a missing key surfaces as KeyError even in environments where
    ``anthropic`` is not installed (mocked unit tests).
    """
    key = os.environ["ANTHROPIC_API_KEY"]  # B-4: KeyError on missing
    import anthropic  # lazy: keeps mocked unit tests SDK-free

    return anthropic.Anthropic(api_key=key)


@lru_cache(maxsize=1)
def gemini_client():
    """Return a cached ``google.genai.Client``.

    Reads ``GOOGLE_API_KEY`` via ``os.environ[KEY]`` (NO ``.get()`` fallback —
    Phase 1 B-4). KeyError on missing. Env-var check comes BEFORE the SDK
    import (see claude_client docstring).
    """
    key = os.environ["GOOGLE_API_KEY"]  # B-4: KeyError on missing
    from google import genai  # lazy: keeps mocked unit tests SDK-free

    return genai.Client(api_key=key)
