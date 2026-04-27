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
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

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
        self._started_at = datetime.now(UTC).isoformat(timespec="seconds")
        if not self.BASELINE_ID:
            raise BaselineError(f"{type(self).__name__}: subclass must set BASELINE_ID")

    # -- LOCKED template-method ------------------------------------------------
    def run(self, *, folio_ids: list[str] | None = None) -> int:
        """LOCKED. Subclasses MUST NOT override.

        Returns 0 on success. Raises ScopeViolation / BudgetExceeded /
        KrakenInferenceFailure / BaselineError on structural failure;
        sandbox is left at results/.in_progress/<baseline_id>/ for
        inspection.

        Phase 03.1 amendment (A-01): per-folio promotion replaces
        whole-batch sandbox.promote(). Each successful folio is paired-
        promoted with its manifest version bump; the next iteration
        cannot start without a clean atomic transaction completing for
        the previous folio.
        """
        # D-13a: script-start preflight.
        self._preflight(folio_ids)

        # D-14 (A-01 amended): sandbox-then-per-folio-promote. Lazy imports
        # keep the helper modules off the package import path so test fakes
        # can patch them.
        import os as _os
        from pathlib import Path as _Path

        from baselines._atomic import SandboxRun
        from baselines._manifest_bump import build_bump
        from baselines._run_meta import validate_expected_total_reports

        # Manifest path resolves from PHASE_0_MANIFEST_PATH env var (CI),
        # else defaults to the dev convention. Both plan 03.1-04 Task 3 CI
        # job and plan 05/06 invocations export PHASE_0_MANIFEST_PATH.
        manifest_path = _Path(
            _os.environ.get(
                "PHASE_0_MANIFEST_PATH",
                "/Users/benlamm/Workspace/baalshem/phase_0_manifest.json",
            )
        )

        with SandboxRun(self.results_root, self.BASELINE_ID) as sandbox:
            for folio in self._iter_folios(folio_ids):
                # D-13b: per-folio re-check, BEFORE inference call.
                self._scope_check(folio)
                lines = self.infer_folio(folio)
                pred = self._serialize(folio, lines)
                sandbox.write_prediction(folio.id, pred)

                # A-01 per-folio paired promotion (replaces end-of-run
                # sandbox.promote()). On rollback, the ScopeViolation /
                # OSError / BudgetExceeded raises propagate; sandbox dir
                # remains for inspection.
                sandbox.promote_folio(
                    folio.id,
                    manifest_path=manifest_path,
                    bump_manifest=build_bump(self.BASELINE_ID, folio.id),
                )

            # run_meta written ONCE at end-of-run, directly to the final
            # results/<bl>/ dir per A-01 amendment (no end-of-run promote()
            # call to migrate it). D-18 latest-state-snapshot semantics.
            sandbox.write_run_meta_final(self._compose_run_meta())

            # D-15 bit-equality after all folios promoted. The CI-side
            # test_expected_totals.py provides the authoritative gate against
            # results/<bl>/; this in-run validate is a defensive double-check
            # against the sandbox's count() (which after per-folio promotion
            # only counts the run_meta sentinel).
            validate_expected_total_reports(
                manifest=self.manifest,
                baseline_id=self.BASELINE_ID,
                written_count=self._count_results(),
            )

        return 0

    def _count_results(self) -> int:
        """Count realistic predictions in the FINAL results/<bl>/ dir.

        Per A-01 amendment: per-folio promotion empties the sandbox of
        prediction files as each folio promotes. The D-15 bit-equality
        check therefore counts the FINAL dir (where promoted predictions
        live), not the sandbox.
        """
        from pathlib import Path as _Path

        final_dir = _Path(self.results_root) / self.BASELINE_ID
        if not final_dir.exists():
            return 0
        return sum(1 for p in final_dir.glob("*.json") if p.name != "run_meta.json")

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
                raise ScopeViolation(f"BL-08: folio(s) outside Leningrad scope: {bad!r}")

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
                f"BL-08: per-folio re-check failed: folio={folio.id} not in frozen scope"
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
            f.id
            for f in self.manifest.frozen_leningrad_folios()
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
            f"BL-08: per-folio re-check failed: folio={folio_id} vanished from manifest mid-run"
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
                    **({"llm_winner": ln.llm_winner} if ln.llm_winner is not None else {}),
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
        """Default run_meta payload, schema-conformant per D-19.

        Subclasses MAY override to populate ``pins``, ``budget``, ``combine``,
        and per-folio ``folios`` entries (e.g., BL-01 fills ``budget`` and
        ``combine.tie_break_winners``; BL-02 fills ``pins.kraken_model_hash``).

        The base default emits null-valued required keys for fields that
        every schema entry must declare but some baselines don't populate
        (BL-02/03/04 emit null inside ``budget`` and ``combine``; BL-01
        emits null inside ``pins`` keys it doesn't use).

        Validation runs at write time inside SandboxRun.write_run_meta;
        the payload returned here MUST satisfy schemas/run_meta.schema.json.
        """
        import socket

        return {
            "schema_version": self.SCHEMA_VERSION,
            "baseline_id": self.BASELINE_ID,
            "manifest_hash": getattr(self.manifest, "manifest_hash", None),
            "scorer_version": getattr(self.manifest, "scorer_version", None),
            "started_at_iso": getattr(self, "_started_at", None)
            or datetime.now(UTC).isoformat(timespec="seconds"),
            "completed_at_iso": datetime.now(UTC).isoformat(timespec="seconds"),
            "hostname": socket.gethostname(),
            "sibling_git_sha": None,
            "replay_mode": self.replay,
            "pins": {
                "kraken_model_hash": None,
                "nakdimon_model_hash": None,
                "dictabert_model_revision": None,
                "llm_pin_md_hash": None,
            },
            "budget": {
                "cap_per_folio": None,
                "cap_run": None,
                "used_total": None,
                "rate_table_snapshot": None,
            },
            "combine": {
                "tie_break_total": None,
                "tie_break_winners": None,
            },
            "folios": {},
        }
