"""run_meta.json writer + D-15 bit-equality validator.

validate_expected_total_reports() runs AFTER all folios complete and
BEFORE sandbox.promote() — off-by-one prevents promote, leaves sandbox
for inspection.
"""

from __future__ import annotations

from pathlib import Path

from baselines._errors import BaselineError


def validate_expected_total_reports(
    *, manifest, baseline_id: str, written_count: int
) -> None:
    """D-15: written_count MUST equal manifest.expected_reports_for(baseline_id) exactly.

    Off-by-one is a structural error. Raised BEFORE sandbox.promote()
    so a numerically-incomplete run never appears in results/<bl>/.

    Per A-1 precedence rule (Issue 5): v0.2 readers MUST treat the
    per-baseline mapping as authoritative whenever it has any keys;
    the legacy scalar is consulted ONLY when the mapping is empty
    (v0.1 compat). This function delegates to
    manifest.expected_reports_for(baseline_id), which encapsulates
    the precedence — we do NOT silently fall back to the legacy
    scalar when the mapping has keys but is missing this baseline_id
    (that would mask a manifest declaration bug).
    """
    try:
        expected = manifest.expected_reports_for(baseline_id)
    except KeyError as e:
        raise BaselineError(
            f"D-15: manifest does not declare expected reports for baseline {baseline_id!r} "
            f"(neither expected_reports_per_baseline[{baseline_id!r}] nor legacy "
            f"expected_total_reports scalar resolves). Underlying error: {e!r}"
        ) from e

    if expected is None:
        raise BaselineError(
            f"D-15: manifest does not declare expected reports for baseline {baseline_id!r}"
        )

    if written_count != expected:
        raise BaselineError(
            f"D-15: expected_total_reports mismatch for baseline {baseline_id!r}: "
            f"wrote {written_count}, manifest declares {expected}. "
            f"Sandbox left at results/.in_progress/{baseline_id}/ for inspection."
        )


def write_run_meta(path: Path, payload: dict) -> None:
    """Write run_meta.json atomically. Used internally by SandboxRun."""
    from baselines._atomic import SandboxRun

    SandboxRun._atomic_write_json(path, payload)
