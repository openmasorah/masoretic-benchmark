from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_manifest_and_scorer_schemas_work_from_package_tree_without_repo_schemas(tmp_path):
    package_root = tmp_path / "installed"
    shutil.copytree(REPO_ROOT / "masoretic_eval", package_root / "masoretic_eval")
    shutil.copy2(REPO_ROOT / "phase_0_manifest.json", package_root / "phase_0_manifest.json")

    script = """
from pathlib import Path
from click.testing import CliRunner

from masoretic_eval.cli import main
from masoretic_eval.manifest import Manifest, SCHEMA_PATH

assert "masoretic_eval/schemas/phase_0_manifest.schema.json" in SCHEMA_PATH.as_posix()
manifest = Manifest.load("phase_0_manifest.json")
assert manifest.version == "v0.2.0"

bad = Path("bad.json")
bad.write_text('{"text": "אבג", "metamarks": [{"type": 123}]}', encoding="utf-8")
out = Path("out.json")
result = CliRunner().invoke(
    main,
    ["score", "--gt", str(bad), "--pred", str(bad), "--folio-id", "smoke", "--out", str(out)],
)
assert result.exit_code != 0
assert "schema validation failed" in result.output
assert "scorer_input.schema.json" in str(Path("masoretic_eval/schemas/scorer_input.schema.json"))
assert not out.exists()
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(package_root)
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=package_root,
        env=env,
        text=True,
        check=True,
    )
