"""Phase 03.1 baseline runner CLI.

Invocation: ``python -m baselines.run --baseline <id> [--folio <folio_id>]``

LOCKED CLI SURFACE (Phase 03.1 D-08 + plan 04 BLOCKER-4 fix):
  --baseline    Required. One of: biblia_kraken, llm_vision,
                biblia_nakdimon, biblia_char_menaked.
  --folio       Optional. Run only the specified folio_id; default = all
                unfinished folios per A-01 (manifest set MINUS already-promoted).

Manifest path: PHASE_0_MANIFEST_PATH env var (CI override) or repo-root
               phase_0_manifest.json. Same convention as BaselineBase.run
               (consistent resolution).

Exit codes:
  0  success (folios promoted; sandbox empty)
  1  ScopeViolation / BudgetExceeded / KrakenInferenceFailure / BaselineError
     or any other error from the baseline run
  2  CLI argument error (handled by argparse with its own non-zero exit)
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

# Registry: --baseline value -> (module path, class name).
# Keep in sync with the four concrete subclasses under baselines/src/baselines/.
BASELINE_REGISTRY = {
    "biblia_kraken": ("baselines.biblia_kraken", "BibliaKrakenBaseline"),
    "llm_vision": ("baselines.llm_vision", "LLMVisionBaseline"),
    "biblia_nakdimon": ("baselines.biblia_nakdimon", "BibliaNakdimonBaseline"),
    "biblia_char_menaked": (
        "baselines.biblia_char_menaked",
        "BibliaCharMenakedBaseline",
    ),
}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m baselines.run",
        description=(
            "Phase 03.1 baseline runner — invokes a registered "
            "BaselineBase subclass against the frozen IAA folios."
        ),
    )
    p.add_argument(
        "--baseline",
        required=True,
        choices=sorted(BASELINE_REGISTRY.keys()),
        help="Which baseline to run.",
    )
    p.add_argument(
        "--folio",
        default=None,
        help=(
            "Optional folio_id to run only that folio. Default: all "
            "unfinished folios per A-01 manifest discovery."
        ),
    )
    return p


def _load_subclass(baseline_id: str):
    module_path, class_name = BASELINE_REGISTRY[baseline_id]
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Resolve manifest_path: CI env var first, then repo-root default.
    # Matches BaselineBase.run's resolution exactly.
    sibling_root = Path(__file__).resolve().parents[3]
    manifest_path = Path(
        os.environ.get(
            "PHASE_0_MANIFEST_PATH",
            str(sibling_root / "phase_0_manifest.json"),
        )
    )
    if not manifest_path.exists():
        print(
            f"ERROR: manifest not found at {manifest_path}. "
            "Set PHASE_0_MANIFEST_PATH env var or run from masoretic-benchmark dev layout.",
            file=sys.stderr,
        )
        return 1

    # Default results_root = sibling repo root's results/ dir. The CLI is
    # the only entry point that needs to compute this; subclass tests use
    # tmp_path. Resolves via this file's location:
    #   parents[0] = baselines/src/baselines
    #   parents[1] = baselines/src
    #   parents[2] = baselines
    #   parents[3] = sibling repo root (masoretic-benchmark)
    results_root = sibling_root / "results"

    cls = _load_subclass(args.baseline)
    # BaselineBase.__init__ signature: (manifest_path, results_root, *, replay=False, ...).
    # Subclasses (LLMVisionBaseline, BibliaKrakenBaseline, etc.) accept the same
    # positional pair plus their own kw-only extras.
    bl = cls(manifest_path, results_root)

    folio_ids = [args.folio] if args.folio else None
    try:
        return bl.run(folio_ids=folio_ids)
    except Exception as e:
        # Preserve the exception type in the exit; surface message to stderr.
        print(f"ERROR ({type(e).__name__}): {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
