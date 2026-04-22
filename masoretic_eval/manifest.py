"""phase_0_manifest.json reader + validator. Single source of truth for frozen scope."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


class ManifestValidationError(Exception):
    pass


@dataclass(frozen=True)
class Folio:
    id: str
    manuscript: str
    book: str
    folio: str
    image_url: str
    iaa_folio: bool
    in_frozen_scope: bool
    gt_hash: str


@dataclass
class Manifest:
    version: str
    frozen_at: str
    folios: list[Folio]
    iaa_subset: list[str]
    fuses_fired: list[str]
    baselines_seeded: list[str]
    expected_reports_per_baseline: int
    expected_total_reports: int
    scorer_version: str
    nakdimon_model_hash: str
    notes: str

    @classmethod
    def load(cls, path: Path | str) -> Manifest:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        required = {
            "version", "frozen_at", "folios", "iaa_subset", "fuses_fired",
            "baselines_seeded", "expected_reports_per_baseline",
            "expected_total_reports", "scorer_version", "nakdimon_model_hash",
        }
        missing = required - set(data)
        if missing:
            raise ManifestValidationError(f"manifest missing required keys: {missing}")
        folios = [Folio(**f) for f in data["folios"]]
        return cls(
            version=data["version"],
            frozen_at=data["frozen_at"],
            folios=folios,
            iaa_subset=data["iaa_subset"],
            fuses_fired=data["fuses_fired"],
            baselines_seeded=data["baselines_seeded"],
            expected_reports_per_baseline=data["expected_reports_per_baseline"],
            expected_total_reports=data["expected_total_reports"],
            scorer_version=data["scorer_version"],
            nakdimon_model_hash=data["nakdimon_model_hash"],
            notes=data.get("notes", ""),
        )

    def frozen_folios(self) -> Iterator[Folio]:
        return (f for f in self.folios if f.in_frozen_scope)

    def iaa_folios(self) -> Iterator[Folio]:
        ids = set(self.iaa_subset)
        return (f for f in self.folios if f.id in ids and f.in_frozen_scope)

    def get_folio(self, folio_id: str) -> Folio:
        for f in self.folios:
            if f.id == folio_id:
                return f
        raise ManifestValidationError(f"no such folio: {folio_id}")

    def validate_prediction_coverage(self, predicted_ids: set[str]) -> None:
        """Raise if predictions don't exactly cover the frozen folio set."""
        frozen_ids = {f.id for f in self.frozen_folios()}
        missing = frozen_ids - predicted_ids
        extra = predicted_ids - frozen_ids
        if missing:
            raise ManifestValidationError(
                f"missing predictions for folios: {sorted(missing)}"
            )
        if extra:
            raise ManifestValidationError(
                f"prediction set contains unknown folios: {sorted(extra)}"
            )
