#!/usr/bin/env python3
"""Phase 03.1 D-10: cost-cap manifest seeding gate for live-tier CI.

Fails fast if phase_0_manifest.json lacks ``cost_caps_usd: {per_folio, per_run}``.
Runs as the FIRST step of the baseline-live job (before any API key is
referenced). Prevents silent live-tier runs against an unseeded manifest.

Per A-02: cost_caps_usd is seeded on first Phase 03.1 promotion. Until
then, this script raises and CI fails — surfacing the seeding requirement
rather than silently overspending.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    # Manifest lives in this repo (relocated from baalshem in Phase 03.1 W3.5).
    # Use env var PHASE_0_MANIFEST_PATH if set (CI override), else default to
    # the in-repo location.
    manifest_path = Path(
        os.environ.get(
            "PHASE_0_MANIFEST_PATH",
            "/Users/benlamm/Workspace/masoretic-benchmark/phase_0_manifest.json",
        )
    )
    if not manifest_path.exists():
        print(
            f"BudgetExceeded: manifest not found at {manifest_path}",
            file=sys.stderr,
        )
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    caps = manifest.get("cost_caps_usd")
    if not caps or "per_folio" not in caps or "per_run" not in caps:
        print(
            "BudgetExceeded: manifest cost_caps_usd not seeded — "
            "run preflight to populate. Phase 03.1 first-promotion seeds "
            "via plan 03.1-05.",
            file=sys.stderr,
        )
        return 1
    print(f"per_folio=${caps['per_folio']:.2f} per_run=${caps['per_run']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
