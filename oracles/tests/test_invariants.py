"""Architectural invariants pinning the scorer-untouched contract.

Forbidden patterns:
  - unicodedata.normalize anywhere in oracles/src/         (D-05)
  - 'from oracles' or 'import oracles' inside masoretic_eval/ (D-19)
  - cache-keyed-on-input-hash inside nakdan_hybrid.py       (D-12)
  - 'def disagreement_rate' inside dictabert.py             (D-26)
  - D-27 disclaimer drift between README and module docstring
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]  # masoretic-benchmark/
ORACLES_SRC = REPO_ROOT / "oracles" / "src" / "oracles"
SCORER_SRC = REPO_ROOT / "masoretic_eval"
DISCLAIMER = (
    "`dictabert-large-char-menaked` is trained on modern Hebrew and is "
    "off-label for pre-modern Tiberian text. Used here only as a "
    "publishable negative-result baseline (Baseline 4). Do not interpret "
    "outputs as oracle-grade diacritization."
)


def _all_py(root: Path):
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_unicodedata_normalize_in_oracles_src():
    """D-05: oracles must never normalize."""
    forbidden = re.compile(r"\bunicodedata\.normalize\b|from\s+unicodedata\s+import\s+normalize")
    offenders = []
    for path in _all_py(ORACLES_SRC):
        text = path.read_text()
        if forbidden.search(text):
            offenders.append(str(path))
    assert not offenders, f"D-05 violation - unicodedata.normalize found in: {offenders}"


def test_scorer_does_not_import_oracles():
    """D-19: masoretic_eval/ must run without oracle deps installed."""
    offenders = []
    for path in _all_py(SCORER_SRC):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "oracles":
                offenders.append(f"{path}:{node.lineno} from oracles import ...")
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("oracles.")
            ):
                offenders.append(f"{path}:{node.lineno} from {node.module} import ...")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "oracles" or alias.name.startswith("oracles."):
                        offenders.append(f"{path}:{node.lineno} import {alias.name}")
    assert not offenders, f"D-19 violation - scorer imports oracles: {offenders}"


def test_nakdan_hybrid_no_response_cache():
    """D-12: DICTA endpoint rotates; caching responses manufactures false reproducibility."""
    path = ORACLES_SRC / "nakdan_hybrid.py"
    if not path.exists():
        pytest.skip("nakdan_hybrid.py not yet created (wave 1)")
    text = path.read_text()
    forbidden_patterns = [
        r"pickle\.load",
        r"pickle\.dump",
        r"shelve\.open",
        r"joblib\.(load|dump).*request",
        r"@(?:functools\.)?lru_cache.*\n.*def\s+(?:_post|diacritize)\b",
        r"cache_response",
        r"requests_cache",
    ]
    offenders = [pat for pat in forbidden_patterns if re.search(pat, text)]
    assert not offenders, f"D-12 violation - DICTA response caching detected: {offenders}"


def test_dictabert_does_not_expose_disagreement_rate():
    """D-26: dictabert is off-label; exposing disagreement_rate would imply oracle-grade trust."""
    path = ORACLES_SRC / "dictabert.py"
    if not path.exists():
        pytest.skip("dictabert.py not yet created (wave 1)")
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "disagreement_rate":
            pytest.fail(f"D-26 violation - dictabert.py:{node.lineno} defines disagreement_rate")


def test_disclaimer_pinned_in_readme_and_module_docstring():
    """D-27: README and dictabert.py module docstring must contain identical disclaimer text."""
    readme = REPO_ROOT / "oracles" / "README.md"
    assert DISCLAIMER in readme.read_text(), (
        "D-27 violation - disclaimer missing/drifted in oracles/README.md"
    )
    path = ORACLES_SRC / "dictabert.py"
    if not path.exists():
        pytest.skip("dictabert.py not yet created (wave 1)")
    tree = ast.parse(path.read_text())
    module_doc = ast.get_docstring(tree) or ""
    assert DISCLAIMER in module_doc, (
        "D-27 violation - disclaimer missing/drifted in dictabert.py module docstring"
    )


def test_no_oracles_subdir_under_scorer():
    """D-22: oracles/ is sibling-of, not child-of, masoretic_eval/."""
    assert not (SCORER_SRC / "oracles").exists(), (
        "D-22 violation - masoretic_eval/oracles/ must not exist"
    )
