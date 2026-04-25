"""Phase 3 baseline base class and shared LineRecord dataclass.

D-12: BaselineBase is a template-method ABC. Subclasses CANNOT override
run() — the template IS the contract. The ONLY abstract method is
infer_folio(folio) -> list[LineRecord]. The locked-run() invariant is
pinned structurally by tests/test_invariants.py.

Lifecycle (locked, executed in this exact order):

    run() ->
        _preflight()                        # D-13a: script-start
        with SandboxRun(...) as sb:
            for folio in iter_folios():
                _scope_check(folio)         # D-13b: per-folio re-check
                lines = infer_folio(folio)  # ONLY abstract method
                sb.write_prediction(folio.id, _serialize(folio, lines))
            validate_expected_total_reports(...)  # D-15 BEFORE promote
            sb.write_run_meta(_compose_run_meta())
            sb.promote()                    # D-14: atomic per file

Phase 1 D-30/D-31 line preservation: LineRecord.line_id is load-bearing.
Run-on text rejected. bbox preserves PAGE-XML coordinates.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from baselines._errors import BaselineError, ScopeViolation


@dataclass(frozen=True)
class LineRecord:
    """One line of a folio's prediction.

    Note on tier4_records: declared as ``tuple[dict, ...]`` for hashability
    under ``frozen=True``. Callers MUST pass a tuple, not a list — passing a
    list will break ``hash(record)`` with TypeError. ``dict`` itself is also
    unhashable; the type is preserved for shape, but if you need to hash a
    LineRecord with non-empty tier4_records, freeze the inner dicts to
    tuples-of-pairs at the call site.
    """

    line_id: str
    bbox: tuple[int, int, int, int]
    tier1: str
    tier2: str
    tier3: str
    tier4_records: tuple[dict, ...]
    kraken_confidence: float | None = None
    llm_winner: str | None = None
    llm_tie_breaks: int | None = None


class BaselineBase(ABC):
    """Template-method ABC for Phase 3 baselines (D-12).

    Subclasses MUST set BASELINE_ID (one of "llm_vision", "biblia_kraken",
    "biblia_nakdimon", "biblia_char_menaked") and override
    infer_folio(folio) -> list[LineRecord]. Subclasses MUST NOT override
    run() — pinned structurally by tests/test_invariants.py.
    """

    # Subclass MUST set; checked in __init__.
    BASELINE_ID: str = ""
    SCHEMA_VERSION: str = "0.1.0"

    def __init__(
        self,
        manifest_path: Path | str,
        results_root: Path | str,
        *,
        replay: bool = False,
    ) -> None:
        # Imported lazily so unit tests can construct subclasses with a
        # FakeManifest without requiring masoretic-eval on the import path.
        from masoretic_eval.manifest import Manifest

        self.manifest = Manifest.load(manifest_path)
        self.results_root = Path(results_root)
        self.replay = replay
        self._started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not self.BASELINE_ID:
            raise BaselineError(
                f"{type(self).__name__}: subclass must set BASELINE_ID"
            )

    # -- LOCKED template-method ------------------------------------------------
    def run(self, *, folio_ids: list[str] | None = None) -> int:
        """LOCKED. Subclasses MUST NOT override.

        Returns 0 on success. Raises ScopeViolation / BudgetExceeded /
        KrakenInferenceFailure / BaselineError on structural failure;
        sandbox is left at results/.in_progress/<baseline_id>/ for
        inspection.
        """
        # D-13a: script-start preflight.
        self._preflight(folio_ids)

        # D-14: sandbox-then-promote. Lazy imports keep the helper modules
        # off the package import path so test fakes can patch them.
        from baselines._atomic import SandboxRun
        from baselines._run_meta import validate_expected_total_reports

        with SandboxRun(self.results_root, self.BASELINE_ID) as sandbox:
            for folio in self._iter_folios(folio_ids):
                # D-13b: per-folio re-check, BEFORE inference call.
                self._scope_check(folio)
                lines = self.infer_folio(folio)
                pred = self._serialize(folio, lines)
                sandbox.write_prediction(folio.id, pred)

            # D-15: bit-equality. Raised BEFORE sandbox.promote() so an
            # off-by-one run never appears in results/<bl>/.
            validate_expected_total_reports(
                manifest=self.manifest,
                baseline_id=self.BASELINE_ID,
                written_count=sandbox.count(),
            )

            sandbox.write_run_meta(self._compose_run_meta())
            sandbox.promote()

        return 0

    # -- abstract surface ------------------------------------------------------
    @abstractmethod
    def infer_folio(self, folio) -> list[LineRecord]:
        """Per-folio inference. THE ONLY abstract method.

        Subclasses override this and only this. Return a list of
        LineRecord — Phase 1 D-30/D-31 line semantics MUST be preserved.
        """
        ...

    # -- D-13 preflight + per-folio re-check ----------------------------------
    def _preflight(self, folio_ids: list[str] | None) -> None:
        """D-13a: script-start preflight. Validates that any user-supplied
        --folio-id is in the frozen-Leningrad set."""
        leningrad_ids = {f.id for f in self.manifest.frozen_leningrad_folios()}
        if folio_ids:
            bad = [fid for fid in folio_ids if fid not in leningrad_ids]
            if bad:
                raise ScopeViolation(
                    f"BL-08: folio(s) outside Leningrad scope: {bad!r}"
                )

    def _scope_check(self, folio) -> None:
        """D-13b: per-folio re-check. Catches manifest mutation between
        iterations; raised BEFORE infer_folio so no inference call leaks
        for an out-of-scope folio."""
        if folio.manuscript != "leningrad":
            raise ScopeViolation(
                f"BL-08: per-folio re-check failed: folio={folio.id} "
                f"manuscript={folio.manuscript!r}"
            )
        if not folio.in_frozen_scope:
            raise ScopeViolation(
                f"BL-08: per-folio re-check failed: folio={folio.id} "
                f"not in frozen scope"
            )

    # -- iteration ------------------------------------------------------------
    def _iter_folios(self, folio_ids: list[str] | None) -> Iterator:
        """Yield folios fresh-resolved per iteration (D-13b substrate).

        The folio set is resolved ONCE at iteration start (frozen list of
        ids), but each yielded folio is re-fetched from the manifest at
        yield time so that mid-run mutations to manifest.folios are
        visible to the per-folio re-check (_scope_check).
        """
        wanted = set(folio_ids) if folio_ids else None
        # Snapshot the id list at the start; iterate fresh-resolved entries
        # against the (possibly mutated) manifest on each pass.
        initial_ids = [
            f.id for f in self.manifest.frozen_leningrad_folios()
            if wanted is None or f.id in wanted
        ]
        for fid in initial_ids:
            yield self._resolve_folio(fid)

    def _resolve_folio(self, folio_id: str):
        """Look up the current state of `folio_id` on every iteration so
        mid-run mutations to the manifest's folio list are observable to
        D-13b. We deliberately read manifest.folios directly (not via
        frozen_leningrad_folios) — a folio whose manuscript flipped to
        non-leningrad is filtered OUT by frozen_leningrad_folios but we
        need to SEE the flipped folio to raise ScopeViolation in
        _scope_check."""
        for f in self.manifest.folios:
            if f.id == folio_id:
                return f
        # If the folio disappeared entirely from manifest.folios mid-run,
        # treat as a scope violation (manifest tampering case).
        raise ScopeViolation(
            f"BL-08: per-folio re-check failed: folio={folio_id} "
            f"vanished from manifest mid-run"
        )

    # -- serialization (subclass MAY override _serialize / _compose_run_meta) -
    def _serialize(self, folio, lines: list[LineRecord]) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "baseline_id": self.BASELINE_ID,
            "folio_id": folio.id,
            "manifest_hash": getattr(self.manifest, "manifest_hash", None),
            "run_meta_ref": "run_meta.json",
            "lines": [
                {
                    "line_id": ln.line_id,
                    "bbox": list(ln.bbox),
                    "tier1": ln.tier1,
                    "tier2": ln.tier2,
                    "tier3": ln.tier3,
                    "tier4_records": [dict(r) for r in ln.tier4_records],
                    **(
                        {"kraken_confidence": ln.kraken_confidence}
                        if ln.kraken_confidence is not None
                        else {}
                    ),
                    **(
                        {"llm_winner": ln.llm_winner}
                        if ln.llm_winner is not None
                        else {}
                    ),
                    **(
                        {"llm_tie_breaks": ln.llm_tie_breaks}
                        if ln.llm_tie_breaks is not None
                        else {}
                    ),
                }
                for ln in lines
            ],
        }

    def _compose_run_meta(self) -> dict:
        """Default run_meta payload. Subclasses extend (e.g., BL-01 adds
        `budget` + `combine` fields).

        D-19 required-field set: schema_version, baseline_id, manifest_hash,
        scorer_version, started_at_iso, completed_at_iso, replay_mode.
        Optional / per-baseline: hostname, sibling_git_sha, pins, budget,
        combine, folios.
        """
        return {
            "schema_version": self.SCHEMA_VERSION,
            "baseline_id": self.BASELINE_ID,
            "manifest_hash": getattr(self.manifest, "manifest_hash", None),
            "scorer_version": getattr(self.manifest, "scorer_version", None),
            "started_at_iso": getattr(self, "_started_at", None),
            "completed_at_iso": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
            "replay_mode": self.replay,
            "pins": {},
            "folios": {},
        }
