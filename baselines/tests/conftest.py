"""Phase 3 baselines test configuration.

Mirrors oracles/tests/conftest.py: env-gated marker for any test that hits
real models, real APIs, or real disk beyond tmp_path. Default: skipped.
Set RUN_LIVE_BASELINES=1 to opt in.

Phase 03.1 A-01 safety net: BaselineBase.run reads PHASE_0_MANIFEST_PATH
from the env to know where to write per-folio manifest bumps. If a unit
test calls bl.run() without seeding this env var, the repo-root default
would mutate the real production manifest. This conftest installs an
autouse fixture that points the env at a tmp file BEFORE every test, so a
forgotten ``monkeypatch.setenv(...)`` in a test cannot pollute the real
manifest. Tests that explicitly want a different path use
``monkeypatch.setenv`` to override this default in their own scope.
"""

import json
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
    skip_live = pytest.mark.skip(reason="set RUN_LIVE_BASELINES=1 to run live-baseline tests")
    for item in items:
        if "live_baselines" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def _safe_phase_0_manifest_path(tmp_path, monkeypatch):
    """A-01 safety net: never let bl.run() touch the real in-repo manifest.

    Seeds a minimal valid v0.2 manifest at <tmp_path>/phase_0_manifest.json
    and points PHASE_0_MANIFEST_PATH at it for the test's lifetime. Tests
    that need a custom manifest can call monkeypatch.setenv again to
    override (later setenv wins).
    """
    p = tmp_path / "phase_0_manifest.json"
    if not p.exists():
        p.write_text(
            json.dumps(
                {
                    "version": "v0.2.0",
                    "frozen_at": "2026-04-25T16:30:44Z",
                    "expected_reports_per_baseline": {
                        "biblia_kraken": 0,
                        "biblia_nakdimon": 0,
                        "biblia_char_menaked": 0,
                        "llm_vision": 0,
                    },
                    "manifest_changelog": [],
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
        )
    monkeypatch.setenv("PHASE_0_MANIFEST_PATH", str(p))
