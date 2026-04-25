"""Phase 3 baselines test configuration.

Mirrors oracles/tests/conftest.py: env-gated marker for any test that hits
real models, real APIs, or real disk beyond tmp_path. Default: skipped.
Set RUN_LIVE_BASELINES=1 to opt in.
"""

import os

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_baselines: tests that hit live Kraken / Anthropic / Google / "
        "DictaBERT / Nakdimon (skipped unless RUN_LIVE_BASELINES=1)",
    )


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_LIVE_BASELINES") == "1":
        return
    skip_live = pytest.mark.skip(
        reason="set RUN_LIVE_BASELINES=1 to run live-baseline tests"
    )
    for item in items:
        if "live_baselines" in item.keywords:
            item.add_marker(skip_live)
