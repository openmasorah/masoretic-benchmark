"""Phase 2 oracle test configuration."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest

_FAKE_NAKDIMON_TMP: tempfile.TemporaryDirectory[str] | None = None


def _install_fake_nakdimon_for_mocked_tests() -> None:
    """Provide nakdimon import surface for mocked tests on Python 3.12.

    nakdimon==0.1.2 depends on TensorFlow 2.15, which is unavailable on
    Python 3.12. Non-live tests monkeypatch the oracle calls, but importing
    oracles.nakdimon_oss still computes MODEL_HASH from package metadata and
    Nakdimon.h5, so the fake package supplies those import-time contracts.
    """
    if os.environ.get("RUN_LIVE_ORACLES") == "1":
        return
    if importlib.util.find_spec("nakdimon") is not None:
        return

    global _FAKE_NAKDIMON_TMP
    _FAKE_NAKDIMON_TMP = tempfile.TemporaryDirectory()
    root = Path(_FAKE_NAKDIMON_TMP.name)

    package_dir = root / "nakdimon"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text(
        "def diacritize(text):\n    return text\n",
        encoding="utf-8",
    )
    (package_dir / "Nakdimon.h5").write_bytes(b"fake nakdimon weights for mocked tests\n")

    dist_info_dir = root / "nakdimon-0.1.2.dist-info"
    dist_info_dir.mkdir()
    (dist_info_dir / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: nakdimon\nVersion: 0.1.2\n",
        encoding="utf-8",
    )

    sys.path.insert(0, str(root))


_install_fake_nakdimon_for_mocked_tests()


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
