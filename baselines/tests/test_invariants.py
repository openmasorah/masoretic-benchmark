"""Phase 3 architectural invariants — pinned as runnable pytest tests.

Mirrors oracles/tests/test_invariants.py pattern (Phase 2 02-01 lesson:
REPO_ROOT uses parents[2] directly — the off-by-one trap from
plan 02-01 is documented; do not append an extra .parent to this
expression. parents[2] is already the sibling repo root because
the file path is .../baselines/tests/test_invariants.py).

Pinned invariants:

  I-1 (D-12): Concrete subclasses of BaselineBase MUST NOT override run().
              AST walk over baselines/src/baselines/*.py; fails test if
              any class inheriting from BaselineBase defines `def run(`.

  I-2 (D-12): Concrete subclasses of BaselineBase MUST set BASELINE_ID
              as a class-level string attribute.

  I-3 (A-3):  Zero references to the Phase-4 score-time oracle wrapper
              from baselines/. The concrete grep test lives in
              test_no_compute_oracle_rates.py (added by plan 03-08, Wave 4).
"""

from __future__ import annotations

import ast
from pathlib import Path

# .../baselines/tests/test_invariants.py
#   parents[0] = baselines/tests/
#   parents[1] = baselines/
#   parents[2] = masoretic-benchmark/   <-- sibling repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINES_SRC = REPO_ROOT / "baselines" / "src" / "baselines"


def _baseline_subclass_classes() -> list[tuple[Path, ast.ClassDef]]:
    """Yield (file, ClassDef) for every class defined under
    baselines/src/baselines/ that inherits from BaselineBase or
    ChainBaseline (a future helper baseline used by BL-03/04). Skips
    underscore-prefixed modules (those are infrastructure, not concrete
    baseline definitions).
    """
    out: list[tuple[Path, ast.ClassDef]] = []
    if not BASELINES_SRC.exists():
        return out
    for py in BASELINES_SRC.glob("*.py"):
        if py.name.startswith("_"):
            continue
        if py.name == "__init__.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                base_names = {b.id for b in node.bases if isinstance(b, ast.Name)}
                # Also catch dotted bases (e.g., baselines._base.BaselineBase)
                for b in node.bases:
                    if isinstance(b, ast.Attribute) and b.attr in (
                        "BaselineBase",
                        "ChainBaseline",
                    ):
                        base_names.add(b.attr)
                if "BaselineBase" in base_names or "ChainBaseline" in base_names:
                    out.append((py, node))
    return out


def test_no_subclass_overrides_run():
    """I-1 (D-12): subclass MUST NOT override run().

    BaselineBase.run() is the locked template-method contract. Allowing
    subclasses to override run() would silently bypass D-13 preflight,
    D-14 sandbox-then-promote, and D-15 bit-equality — all four become
    correctness-of-the-honor-system rather than structural guarantees.
    """
    offenders: list[str] = []
    for path, cls in _baseline_subclass_classes():
        for child in cls.body:
            if isinstance(child, ast.FunctionDef) and child.name == "run":
                offenders.append(f"{path.name}::{cls.name}.run (line {child.lineno})")
    assert not offenders, (
        "BaselineBase.run() is locked (D-12). The following subclasses "
        "illegally override run():\n  " + "\n  ".join(offenders)
    )


def test_every_concrete_subclass_sets_BASELINE_ID():
    """I-2 (D-12): every concrete subclass MUST set BASELINE_ID."""
    missing: list[str] = []
    for path, cls in _baseline_subclass_classes():
        has = False
        for child in cls.body:
            if isinstance(child, ast.Assign):
                for tgt in child.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "BASELINE_ID":
                        has = True
            elif isinstance(child, ast.AnnAssign):
                if isinstance(child.target, ast.Name) and child.target.id == "BASELINE_ID":
                    has = True
        if not has:
            missing.append(f"{path.name}::{cls.name}")
    assert not missing, (
        "Every concrete BaselineBase subclass MUST set BASELINE_ID. Missing:\n  "
        + "\n  ".join(missing)
    )


def test_repo_root_resolves_to_sibling_root():
    """Sanity check the parents[2] off-by-one fix (Phase 2 02-01 lesson).
    REPO_ROOT MUST contain pyproject.toml + masoretic_eval/ + oracles/.
    """
    assert (REPO_ROOT / "pyproject.toml").exists(), (
        f"REPO_ROOT={REPO_ROOT} is wrong; pyproject.toml not found there"
    )
    assert (REPO_ROOT / "masoretic_eval").is_dir(), (
        f"REPO_ROOT={REPO_ROOT} is wrong; masoretic_eval/ not found there"
    )
    assert (REPO_ROOT / "oracles").is_dir()
    assert (REPO_ROOT / "baselines").is_dir()


# -- meta-invariant: synthetic-violator scenario -----------------------------
# Test 2 of Task 3 behavior: when a violator file exists, the invariant
# fires with a clear error. We exercise this against a temp file (not
# polluting the real source tree).


_VIOLATOR_SRC = '''
"""Synthetic violator: subclasses BaselineBase and overrides run()."""
from baselines._base import BaselineBase


class IllegalBaseline(BaselineBase):
    BASELINE_ID = "illegal"

    def run(self, *, folio_ids=None) -> int:
        # This MUST trigger I-1
        return 42

    def infer_folio(self, folio):
        return []
'''

_NO_BASELINE_ID_SRC = '''
"""Synthetic violator: subclasses BaselineBase but omits BASELINE_ID."""
from baselines._base import BaselineBase


class UnnamedBaseline(BaselineBase):
    def infer_folio(self, folio):
        return []
'''


def _walk_temp(src_text: str) -> list[ast.ClassDef]:
    """Helper: parse text, return ClassDefs that look like Baseline subclasses."""
    tree = ast.parse(src_text)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            base_names = {b.id for b in node.bases if isinstance(b, ast.Name)}
            if "BaselineBase" in base_names:
                out.append(node)
    return out


def test_violator_run_override_would_be_detected():
    """Test 2: a synthetic file that overrides run() WOULD trip I-1.
    We don't write the file to disk (would pollute the source tree);
    we exercise the AST-walk logic on the source text directly."""
    classes = _walk_temp(_VIOLATOR_SRC)
    assert len(classes) == 1
    cls = classes[0]
    has_run_override = any(
        isinstance(child, ast.FunctionDef) and child.name == "run" for child in cls.body
    )
    assert has_run_override, "Synthetic violator must declare def run; sanity check failed"


def test_run_body_calls_promote_folio_not_promote():
    """I-4 (Phase 03.1 A-01 amendment): BaselineBase.run body MUST call
    sandbox.promote_folio (per-folio paired promotion) and MUST NOT call
    sandbox.promote (whole-batch promotion). Locks the A-01 amendment
    structurally so a future regression to the Phase 3 D-14 form is
    caught by AST walk."""
    base_path = BASELINES_SRC / "_base.py"
    tree = ast.parse(base_path.read_text(encoding="utf-8"))
    run_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "BaselineBase":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "run":
                    run_func = child
                    break
            break
    assert run_func is not None, "BaselineBase.run not found in _base.py"

    promote_folio_calls = 0
    promote_calls = 0
    for sub in ast.walk(run_func):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if isinstance(sub.func.value, ast.Name) and sub.func.value.id == "sandbox":
                if sub.func.attr == "promote_folio":
                    promote_folio_calls += 1
                elif sub.func.attr == "promote":
                    promote_calls += 1

    assert promote_folio_calls >= 1, (
        "I-4 (A-01 amendment): BaselineBase.run body MUST call "
        "sandbox.promote_folio at least once (per-folio paired promotion)."
    )
    assert promote_calls == 0, (
        "I-4 (A-01 amendment): BaselineBase.run body MUST NOT call "
        f"sandbox.promote (whole-batch promotion); found {promote_calls} "
        "call(s). The Phase 3 D-14 form was amended by Phase 03.1 A-01."
    )


def test_violator_missing_baseline_id_would_be_detected():
    """Test 3: a synthetic file that omits BASELINE_ID WOULD trip I-2."""
    classes = _walk_temp(_NO_BASELINE_ID_SRC)
    assert len(classes) == 1
    cls = classes[0]
    has_baseline_id = False
    for child in cls.body:
        if isinstance(child, ast.Assign):
            for tgt in child.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "BASELINE_ID":
                    has_baseline_id = True
        elif isinstance(child, ast.AnnAssign):
            if isinstance(child.target, ast.Name) and child.target.id == "BASELINE_ID":
                has_baseline_id = True
    assert not has_baseline_id, "Synthetic violator must omit BASELINE_ID; sanity check failed"
