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
from collections.abc import Callable
from pathlib import Path

from baselines._schema import validate_prediction, validate_run_meta


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
        # D-16/D-17: validate BEFORE the atomic write so off-shape
        # payloads never reach the sandbox (and never reach results/<bl>/).
        validate_prediction(payload)
        path = self.sandbox_dir / f"{folio_id}.json"
        self._atomic_write_json(path, payload)
        return path

    def write_diagnostic(self, folio_id: str, payload: dict) -> Path:
        """BL-03/BL-04 only: GT-fed diagnostic chain (D-01).
        Lands at results/<bl>/diagnostic/<folio_id>.gt_fed.json.
        NOT counted toward expected_total_reports (D-15)."""
        # D-16/D-17: diagnostic uses the same prediction shape; validate
        # BEFORE any disk side-effect (including mkdir of diagnostic/).
        validate_prediction(payload)
        diag_dir = self.sandbox_dir / "diagnostic"
        diag_dir.mkdir(parents=True, exist_ok=True)
        path = diag_dir / f"{folio_id}.gt_fed.json"
        self._atomic_write_json(path, payload)
        return path

    def write_run_meta(self, payload: dict) -> Path:
        # D-16/D-19: validate BEFORE the atomic write.
        validate_run_meta(payload)
        path = self.sandbox_dir / "run_meta.json"
        self._atomic_write_json(path, payload)
        return path

    def write_run_meta_final(self, payload: dict) -> Path:
        """A-01 amendment: write run_meta directly to results/<bl>/ at
        end-of-run, after all folios have already been per-folio promoted.

        Phase 3 D-18: run_meta is a latest-state snapshot, single-file,
        rewritten on each promotion. Per A-01 (per-folio promotion), there
        is no end-of-run promote() call to migrate sandbox/run_meta.json
        into results/<bl>/. We therefore write directly to the final dir
        (the dir already exists because per-folio promote_folio created
        it). Validation runs BEFORE the atomic temp+rename write so an
        off-shape payload never lands.
        """
        validate_run_meta(payload)
        self.final_dir.mkdir(parents=True, exist_ok=True)
        path = self.final_dir / "run_meta.json"
        self._atomic_write_json(path, payload)
        return path

    def count(self) -> int:
        """Count of REALISTIC predictions (top-level *.json), not diagnostics
        and not run_meta.json. D-15 bit-equality compares this to
        manifest.expected_reports_for(baseline_id)."""
        if not self.sandbox_dir.exists():
            return 0
        return sum(1 for p in self.sandbox_dir.glob("*.json") if p.name != "run_meta.json")

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

    def promote_folio(
        self,
        folio_id: str,
        *,
        manifest_path: Path,
        bump_manifest: Callable[[dict], dict],
    ) -> None:
        """A-01 per-folio paired promotion (Phase 03.1 amendment to D-14).

        Operations (paired success-or-paired-rollback):
          1. os.replace(.in_progress/<bl>/<folio>.json, results/<bl>/<folio>.json)
          2. (BL-01 only -- if .in_progress/<bl>/<folio>/ exists)
             os.replace(.in_progress/<bl>/<folio>/, results/<bl>/<folio>/)
          3. Manifest version bump:
             - read manifest_path JSON
             - call bump_manifest(prev) -> new_manifest_dict
             - atomic temp+rename write via _atomic_write_json
          4. fsync parent dirs of (1), (2), (3) for crash-durability (Pitfall 3)

        Rollback:
          - If (1) succeeds but (3) fails -> rename results/<bl>/<folio>.json BACK
            and (BL-01) rename results/<bl>/<folio>/ BACK; re-raise.
          - If (1) fails -> never call (3); re-raise.
          - If (2) fails -> rollback (1); re-raise.

        Args:
            folio_id: the folio_id being promoted.
            manifest_path: absolute path to phase_0_manifest.json.
            bump_manifest: callable taking the prev manifest dict and returning
                the new manifest dict (with incremented expected_reports_per_baseline,
                updated frozen_at, appended manifest_changelog row).

        Raises:
            FileNotFoundError if .in_progress/<bl>/<folio>.json does not exist.
            Any OSError from os.replace or fsync; or any exception from bump_manifest.
        """
        src_pred = self.sandbox_dir / f"{folio_id}.json"
        src_dir = self.sandbox_dir / folio_id  # BL-01 only -- may not exist for BL-02/03/04
        # BL-03/BL-04 GT-fed diagnostic per folio (D-01); written by
        # SandboxRun.write_diagnostic into <sandbox>/diagnostic/<folio>.gt_fed.json.
        # Promoted alongside the realistic prediction file so the per-folio
        # transaction stays paired across the chain.
        src_diag = self.sandbox_dir / "diagnostic" / f"{folio_id}.gt_fed.json"
        if not src_pred.exists():
            raise FileNotFoundError(f"promote_folio: {src_pred} does not exist")

        self.final_dir.mkdir(parents=True, exist_ok=True)
        dst_pred = self.final_dir / f"{folio_id}.json"
        dst_dir = self.final_dir / folio_id
        dst_diag = self.final_dir / "diagnostic" / f"{folio_id}.gt_fed.json"

        moved_pred = False
        moved_dir = False
        moved_diag = False

        try:
            os.replace(src_pred, dst_pred)
            moved_pred = True
            self._fsync_parent(dst_pred)

            if src_dir.is_dir():
                if dst_dir.exists():
                    shutil.rmtree(dst_dir)
                os.replace(src_dir, dst_dir)
                moved_dir = True
                self._fsync_parent(dst_dir)

            if src_diag.exists():
                dst_diag.parent.mkdir(parents=True, exist_ok=True)
                os.replace(src_diag, dst_diag)
                moved_diag = True
                self._fsync_parent(dst_diag)

            prev = json.loads(manifest_path.read_text(encoding="utf-8"))
            new = bump_manifest(prev)
            self._atomic_write_json(manifest_path, new)
            self._fsync_parent(manifest_path)

        except Exception:
            if moved_diag and dst_diag.exists():
                os.replace(dst_diag, src_diag)
            if moved_dir and dst_dir.is_dir():
                os.replace(dst_dir, src_dir)
            if moved_pred and dst_pred.exists():
                os.replace(dst_pred, src_pred)
            raise

    @staticmethod
    def _fsync_parent(path: Path) -> None:
        """Pitfall 3: rename is not crash-durable without parent-dir fsync."""
        fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict) -> None:
        """Temp-file + os.replace: standard POSIX atomic-write idiom."""
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, sort_keys=True, indent=2)
        os.replace(tmp, path)
