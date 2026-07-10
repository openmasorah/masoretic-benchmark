"""phase_0_manifest.json reader + validator. Single source of truth for frozen scope.

v0.2 dual-read (Phase 3 plan 03-01, A-1)
----------------------------------------
On disk, the manifest is at v0.2 (sibling repo schema bumped 2026-04-25).
For backward compatibility during the migration window, ``Manifest.load``
also accepts a v0.1-shaped document by coercing missing v0.2 fields to
their legacy defaults *in memory*. The on-disk file is never modified by
``load``; the writer-layer is unchanged (Phase 1 D-12 atomic-rename
discipline still applies).

Coercion rules (v0.1 -> v0.2 in-memory only):
  * ``iaa_subset``                     missing -> ``[]``
  * ``baselines_seeded``               missing -> ``[]``
  * ``expected_reports_per_baseline``  missing -> ``{}``
  * ``nakdimon_model_hash: null``      -> ``""``

The package-local v0.2 JSON Schema
(``masoretic_eval/schemas/phase_0_manifest.schema.json``) is the
authoritative validator. After in-memory coercion, every loaded document is
re-validated against the v0.2 schema; truly malformed documents (e.g. v0.2
doc missing ``iaa_subset`` outright -- not a v0.1 doc) raise
``ManifestValidationError`` with the missing-field name.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = Path(__file__).parent / "schemas" / "phase_0_manifest.schema.json"


class ManifestValidationError(Exception):
    pass


@dataclass(frozen=True)
class Folio:
    id: str
    manuscript: str
    book: str
    folio: str
    image_url: str
    iaa_folio: bool = False
    in_frozen_scope: bool = True
    gt_hash: str | None = None
    # Provenance for gt_hash. D-28 named adjudicated_gt_<folio>.json as canonical
    # GT; it was never produced, so gt_hash is computed over a derived projection
    # and the source it derives from must travel with it.
    gt_source: str | None = None


def _coerce_v01_to_v02_in_memory(doc: dict[str, Any]) -> dict[str, Any]:
    """Add v0.2 default values for fields missing in v0.1 documents.

    Non-destructive: returns a shallow-copied dict; the caller's dict is
    not mutated. The on-disk file is never touched by load().
    """
    out = dict(doc)
    out.setdefault("iaa_subset", [])
    out.setdefault("baselines_seeded", [])
    out.setdefault("expected_reports_per_baseline", {})
    # v0.1 allowed null; v0.2 requires string. Coerce null to "".
    if out.get("nakdimon_model_hash") is None:
        out["nakdimon_model_hash"] = ""
    return out


def _canonical_manifest_hash(raw_doc: dict[str, Any]) -> str:
    canonical = json.dumps(
        raw_doc,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class Manifest:
    """Loaded phase_0_manifest.json (v0.2 schema, v0.1 read-compat)."""

    version: str
    frozen_at: str
    folios: list[Folio]
    iaa_subset: list[str]
    baselines_seeded: list[str]
    expected_reports_per_baseline: dict[str, int]
    expected_total_reports: int | dict[str, int]
    scorer_version: str
    nakdimon_model_hash: str
    manifest_hash: str
    fuses_fired: list[Any] = field(default_factory=list)
    notes: str = ""
    # The verbatim coerced document, used by expected_reports_for() to
    # consult the legacy scalar when the per-baseline mapping is empty.
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, path: Path | str) -> Manifest:
        raw_doc = json.loads(Path(path).read_text(encoding="utf-8"))
        manifest_hash = _canonical_manifest_hash(raw_doc)
        # Coerce v0.1 missing fields BEFORE validation so v0.1 docs pass.
        doc = _coerce_v01_to_v02_in_memory(raw_doc)
        # Validate against the v0.2 schema. Truly malformed docs (e.g. a
        # v0.2 doc missing iaa_subset -- not legacy v0.1) still raise.
        try:
            schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
            jsonschema.validate(doc, schema)
        except jsonschema.ValidationError as e:
            raise ManifestValidationError(
                f"manifest validation failed: {e.message} at {list(e.path)}"
            ) from e

        folios = [
            Folio(
                id=f["id"],
                manuscript=f["manuscript"],
                book=f["book"],
                folio=f["folio"],
                image_url=f["image_url"],
                iaa_folio=f.get("iaa_folio", False),
                in_frozen_scope=f["in_frozen_scope"],
                gt_hash=f.get("gt_hash"),
                gt_source=f.get("gt_source"),
            )
            for f in doc["folios"]
        ]
        return cls(
            version=doc["version"],
            frozen_at=doc["frozen_at"],
            folios=folios,
            iaa_subset=list(doc["iaa_subset"]),
            baselines_seeded=list(doc["baselines_seeded"]),
            expected_reports_per_baseline=dict(doc["expected_reports_per_baseline"]),
            expected_total_reports=doc["expected_total_reports"],
            scorer_version=doc["scorer_version"],
            nakdimon_model_hash=doc["nakdimon_model_hash"],
            manifest_hash=manifest_hash,
            fuses_fired=list(doc.get("fuses_fired", [])),
            notes=doc.get("notes", ""),
            _raw=doc,
        )

    # ------------------------------------------------------------------
    # Iteration helpers
    # ------------------------------------------------------------------

    def frozen_folios(self) -> Iterator[Folio]:
        return (f for f in self.folios if f.in_frozen_scope)

    def frozen_leningrad_folios(self) -> list[Folio]:
        """Return frozen folios whose manuscript == 'leningrad'.

        Phase 3 BL-08 preflight calls this: ScopeViolation is raised when
        a baseline run touches a folio outside the frozen Leningrad set.
        """
        return [f for f in self.folios if f.manuscript == "leningrad" and f.in_frozen_scope]

    def iaa_folios(self) -> Iterator[Folio]:
        ids = set(self.iaa_subset)
        return (f for f in self.folios if f.id in ids and f.in_frozen_scope)

    def get_folio(self, folio_id: str) -> Folio:
        for f in self.folios:
            if f.id == folio_id:
                return f
        raise ManifestValidationError(f"no such folio: {folio_id}")

    # ------------------------------------------------------------------
    # Per-baseline expected report count (Issue 5 precedence rule)
    # ------------------------------------------------------------------

    def expected_reports_for(self, baseline_id: str) -> int:
        """Return the expected report count for the named baseline.

        v0.2 readers MUST treat the per-baseline mapping as authoritative
        whenever it has any keys; legacy scalar is only consulted when the
        mapping is empty (v0.1 compat).

        Raises:
            KeyError: if the per-baseline mapping is non-empty but does
                not contain ``baseline_id``. This NEVER silently falls
                back to the legacy ``expected_total_reports`` scalar -- a
                v0.2 manifest with a populated mapping is canonical.

            KeyError: if both the per-baseline mapping is empty AND the
                legacy scalar is absent or non-integer.
        """
        if self.expected_reports_per_baseline:
            # Non-empty mapping -> canonical (A-1, Issue 5).
            return self.expected_reports_per_baseline[baseline_id]
        # Empty mapping -> v0.1 compat: fall back to legacy scalar.
        legacy = self._raw.get("expected_total_reports")
        if isinstance(legacy, int):
            return legacy
        raise KeyError(baseline_id)

    # ------------------------------------------------------------------
    # Coverage check (unchanged from v0.1 reader)
    # ------------------------------------------------------------------

    def validate_prediction_coverage(self, predicted_ids: set[str]) -> None:
        """Raise if predictions don't exactly cover the frozen folio set."""
        frozen_ids = {f.id for f in self.frozen_folios()}
        missing = frozen_ids - predicted_ids
        extra = predicted_ids - frozen_ids
        if missing:
            raise ManifestValidationError(f"missing predictions for folios: {sorted(missing)}")
        if extra:
            raise ManifestValidationError(
                f"prediction set contains unknown folios: {sorted(extra)}"
            )
