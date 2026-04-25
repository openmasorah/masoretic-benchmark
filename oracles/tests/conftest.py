"""Phase 2 oracle test configuration."""

import os

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_oracles: tests that hit live Nakdimon / DICTA / DictaBERT "
        "(skipped unless RUN_LIVE_ORACLES=1)",
    )


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_LIVE_ORACLES") == "1":
        return
    skip_live = pytest.mark.skip(reason="set RUN_LIVE_ORACLES=1 to run live-oracle tests")
    for item in items:
        if "live_oracles" in item.keywords:
            item.add_marker(skip_live)
