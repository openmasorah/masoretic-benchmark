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
# Phase 03.1 A-02: cost_caps_usd block replaces the v0.1 budget block.
# At runtime, the manifest's cost_caps_usd is authoritative (read by
# llm_vision.py); this YAML value seeds the manifest at first promotion.
COST_CAPS_USD: dict = _CONFIG["cost_caps_usd"]
# Back-compat alias for any code path still expecting the old name; new
# code uses COST_CAPS_USD.
BUDGET_CFG: dict = COST_CAPS_USD
RATE_TABLE: dict = _CONFIG["models"]


@lru_cache(maxsize=1)
def claude_client():
    """Return a cached ``anthropic.Anthropic`` client.

    Reads ``ANTHROPIC_API_KEY`` via ``os.environ[KEY]`` (NO ``.get()`` fallback —
    Phase 1 B-4). KeyError on missing. Env-var check comes BEFORE the SDK
    import so a missing key surfaces as KeyError even in environments where
    ``anthropic`` is not installed (mocked unit tests).

    Phase 03.1 A-02 (Pitfall 4): SDK retries DISABLED (max_retries=0).
    Custom retry loop in call_with_retry_and_billing bills each attempt
    against the budget pool BEFORE invoking the SDK. SDK-internal retries
    would be invisible to the budget.
    """
    key = os.environ["ANTHROPIC_API_KEY"]  # B-4: KeyError on missing
    import anthropic  # lazy: keeps mocked unit tests SDK-free

    return anthropic.Anthropic(api_key=key, max_retries=0)


@lru_cache(maxsize=1)
def gemini_client():
    """Return a cached ``google.genai.Client``.

    Reads ``GOOGLE_API_KEY`` via ``os.environ[KEY]`` (NO ``.get()`` fallback —
    Phase 1 B-4). KeyError on missing. Env-var check comes BEFORE the SDK
    import (see claude_client docstring).

    Phase 03.1 A-02 (Pitfall 4): SDK-side retries disabled. The google-genai
    1.x http_options retry knob (``retry_count``) is set to 0 so any
    backoff/retry happens explicitly inside ``call_with_retry_and_billing``.
    """
    key = os.environ["GOOGLE_API_KEY"]  # B-4: KeyError on missing
    from google import genai  # lazy: keeps mocked unit tests SDK-free

    return genai.Client(api_key=key, http_options={"retry_count": 0})


def call_with_retry_and_billing(
    client_fn,
    request: dict,
    budget,
    *,
    rate_table: dict,
    source: str,  # "claude" or "gemini"
    max_attempts: int = 3,
    backoff_base_s: float = 2.0,
):
    """A-02 retry billing — bills each attempt before invoking SDK.

    Returns (response, actual_spend_usd) on success; raises after max_attempts.

    Each attempt's estimated spend is added to the budget pool BEFORE the
    SDK call, so SDK-internal retries (which we've disabled via max_retries=0)
    cannot create invisible spend. On RateLimitError / ServerError, we sleep
    and retry; each retry rebills.

    Args:
        client_fn: callable(**request) -> raw provider response.
        request: canonical request dict; MUST carry expected_input_tokens
            and expected_output_tokens for pre-call estimation.
        budget: budget pool with a ``charge(amount, source=...)`` method
            that raises BudgetExceeded on per-folio or per-run cap breach.
        rate_table: per-model rate table (e.g. RATE_TABLE).
        source: "claude" or "gemini" — selects rate_table[source].
        max_attempts: total attempts including the first call.
        backoff_base_s: exponential backoff base in seconds.
    """
    import time

    last_exc = None
    cumulative_spend = 0.0
    for attempt in range(max_attempts):
        # Estimate this attempt's spend BEFORE invoking SDK.
        est = _estimate_usd_from_request(request, rate_table[source])
        budget.charge(est, source=source)  # raises BudgetExceeded if cap hit
        cumulative_spend += est
        try:
            response = client_fn(request)
            return response, cumulative_spend
        except _retryable_errors() as e:
            last_exc = e
            if attempt < max_attempts - 1:
                time.sleep(backoff_base_s * (2**attempt))  # exponential backoff
            continue
    # Out of attempts — raise the last exception.
    raise last_exc


def _retryable_errors():
    """Lazy-imported retryable error tuple for both providers.

    Returns the union of retryable error classes across anthropic + google-genai
    that are installed in the current environment. Mocked unit tests with
    neither SDK installed get an empty tuple (no retry path exercised).
    """
    errs: list[type[BaseException]] = []
    try:
        import anthropic

        # APIError is the base class; RateLimitError + OverloadedError are
        # subclasses. Including the base catches all transient API errors.
        for name in ("RateLimitError", "APIError", "OverloadedError"):
            cls = getattr(anthropic, name, None)
            if cls is not None:
                errs.append(cls)
    except ImportError:
        pass
    try:
        from google.genai import errors as genai_errors

        for name in ("ServerError",):
            cls = getattr(genai_errors, name, None)
            if cls is not None:
                errs.append(cls)
    except ImportError:
        pass
    return tuple(errs)


def _estimate_usd_from_request(request: dict, rates: dict) -> float:
    """Pre-call spend estimate from request token-count expectations.

    Uses the same rate-table math as ``llm_vision._estimate_usd``, but reads
    from ``request['expected_input_tokens']`` + ``request['expected_output_tokens']``
    which the BL-01 caller populates BEFORE invoking. Conservative (uses
    the request's max budget, not actual usage).
    """
    in_t = float(request.get("expected_input_tokens", 0))
    out_t = float(request.get("expected_output_tokens", 0))
    return (in_t * rates["input_per_mtok_usd"] + out_t * rates["output_per_mtok_usd"]) / 1_000_000
