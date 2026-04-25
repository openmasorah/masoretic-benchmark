"""Sandbox-then-promote atomic writes (D-14).

Per-folio predictions, replay logs, and run_meta are written to
results/.in_progress/<baseline_id>/ during the run. On full-run
success: atomic POSIX rename per file from .in_progress/<bl>/ to
results/<bl>/. On any abort: leave .in_progress/<bl>/ populated for
inspection; do NOT touch results/<bl>/.

results/<bl>/ only ever contains complete blessed runs.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


class SandboxRun:
    """Context manager wrapping a per-baseline output sandbox.

    Lifecycle:
      __enter__ -> create results/.in_progress/<bl>/
      .write_prediction(folio_id, payload) per folio
      .write_run_meta(payload) once
      .promote() once on success -> os.replace per file into results/<bl>/
      __exit__ on exception -> sandbox preserved for inspection (D-14)
    """

    def __init__(self, results_root: Path | str, baseline_id: str):
        self.results_root = Path(results_root)
        self.baseline_id = baseline_id
        self.sandbox_dir = self.results_root / ".in_progress" / baseline_id
        self.final_dir = self.results_root / baseline_id
        self._promoted = False

    def __enter__(self) -> SandboxRun:
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # On exception: leave sandbox for inspection. Do NOT delete.
        # On clean exit without explicit promote(): also leave sandbox
        # (defensive — a missing promote() call is a bug, not a success).
        # Never suppress.
        return False

    def write_prediction(self, folio_id: str, payload: dict) -> Path:
        path = self.sandbox_dir / f"{folio_id}.json"
        self._atomic_write_json(path, payload)
        return path

    def write_diagnostic(self, folio_id: str, payload: dict) -> Path:
        """BL-03/BL-04 only: GT-fed diagnostic chain (D-01).
        Lands at results/<bl>/diagnostic/<folio_id>.gt_fed.json.
        NOT counted toward expected_total_reports (D-15)."""
        diag_dir = self.sandbox_dir / "diagnostic"
        diag_dir.mkdir(parents=True, exist_ok=True)
        path = diag_dir / f"{folio_id}.gt_fed.json"
        self._atomic_write_json(path, payload)
        return path

    def write_run_meta(self, payload: dict) -> Path:
        path = self.sandbox_dir / "run_meta.json"
        self._atomic_write_json(path, payload)
        return path

    def count(self) -> int:
        """Count of REALISTIC predictions (top-level *.json), not diagnostics
        and not run_meta.json. D-15 bit-equality compares this to
        manifest.expected_reports_for(baseline_id)."""
        if not self.sandbox_dir.exists():
            return 0
        return sum(
            1
            for p in self.sandbox_dir.glob("*.json")
            if p.name != "run_meta.json"
        )

    def promote(self) -> None:
        """Atomic rename: move every file from sandbox to final dir.

        Per POSIX rename(2): within the same filesystem this is atomic
        per file. The whole-directory promote is therefore atomic per
        file but NOT atomic across the directory; however, callers
        guarantee promote() is the very last step (after D-15 bit-equality
        passes), so a partial promote is only possible on hardware fault
        — and the sandbox copy is the source of truth in that case.
        """
        self.final_dir.mkdir(parents=True, exist_ok=True)
        for src in self.sandbox_dir.iterdir():
            dst = self.final_dir / src.name
            if src.is_dir():
                # diagnostic/ subdir: replace whole subdir atomically
                # via rmtree-then-rename. Not atomic at the directory
                # level, but the only existing subdir is `diagnostic/`
                # which is a paper-only artifact; partial replace is
                # tolerable here.
                if dst.exists():
                    shutil.rmtree(dst)
                os.replace(src, dst)
            else:
                os.replace(src, dst)
        # Remove now-empty sandbox dir (best-effort).
        try:
            self.sandbox_dir.rmdir()
        except OSError:
            pass
        self._promoted = True

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict) -> None:
        """Temp-file + os.replace: standard POSIX atomic-write idiom."""
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, sort_keys=True, indent=2)
        os.replace(tmp, path)
