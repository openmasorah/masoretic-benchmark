"""D-27 disclaimer invariant: verbatim text MUST appear in module docstring AND README.

This test pins the off-label DictaBERT disclaimer at TWO places:
  - baselines/src/baselines/biblia_char_menaked.py (module docstring)
  - baselines/README.md

Drift in either location fails the build. Defense in depth: Phase 2 already pins
the same disclaimer at the oracle layer (oracles/dictabert.py + oracles/README.md);
Phase 3 pins the consumer-layer copies.

Per D-27 (Phase 2 carry-forward) and Phase 3 plan 03-06: the disclaimer is the
load-bearing contract that DictaBERT char-menaked is off-label for pre-modern
Tiberian text. The whole purpose of BL-04 is the negative-result framing, and
the disclaimer is the substrate of that framing.
"""

from __future__ import annotations

from pathlib import Path

# Path resolution: this file is at
#   <repo>/baselines/tests/test_dictabert_disclaimer_invariant.py
# parents[0]=tests, parents[1]=baselines, parents[2]=<repo>.
REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "baselines" / "src" / "baselines" / "biblia_char_menaked.py"
README = REPO_ROOT / "baselines" / "README.md"

DISCLAIMER = (
    "dictabert-large-char-menaked is trained on modern Hebrew and is off-label "
    "for pre-modern Tiberian text. Used here only as a publishable negative-result "
    "baseline (Baseline 4). Do not interpret outputs as oracle-grade diacritization."
)


def _normalize(text: str) -> str:
    """Collapse whitespace + line wraps so the markdown blockquote and the
    docstring (which may wrap differently) match the same canonical form."""
    return " ".join(text.split())


def test_disclaimer_in_module_docstring():
    text = MODULE.read_text(encoding="utf-8")
    assert _normalize(DISCLAIMER) in _normalize(text), (
        "D-27 disclaimer missing or altered in baselines/biblia_char_menaked.py "
        "(must match the verbatim Phase 2 02-04 lock)"
    )


def test_disclaimer_in_readme():
    text = README.read_text(encoding="utf-8")
    assert _normalize(DISCLAIMER) in _normalize(text), (
        "D-27 disclaimer missing or altered in baselines/README.md "
        "(must match the verbatim Phase 2 02-04 lock)"
    )
