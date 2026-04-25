"""In-memory fake Manifest for plan 03-02 unit tests.

Mirrors the post-03-01 Manifest API surface that BaselineBase calls:
  - .frozen_leningrad_folios() -> list[Folio-like]
  - .expected_reports_for(baseline_id) -> int (raises KeyError on absence)
  - .scorer_version: str
  - .manifest_hash: str | None  (optional; getattr defaults to None)

The fake never touches disk; tests construct a FakeManifest with whatever
folios + expected mapping they need and pass it directly to BaselineBase.
This keeps Task 2 unit tests independent of plan 03-01's manifest schema
bump, and independent of jsonschema validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FakeFolio:
    id: str
    manuscript: str = "leningrad"
    in_frozen_scope: bool = True


@dataclass
class FakeManifest:
    folios: list[FakeFolio] = field(default_factory=list)
    expected_reports_per_baseline: dict[str, int] = field(default_factory=dict)
    expected_total_reports: int | None = None
    scorer_version: str = "v0.1.0-scorer"
    manifest_hash: str | None = "fake-manifest-hash"

    def frozen_leningrad_folios(self) -> list[FakeFolio]:
        return [
            f for f in self.folios
            if f.manuscript == "leningrad" and f.in_frozen_scope
        ]

    def expected_reports_for(self, baseline_id: str) -> int:
        # Plan 03-01 precedence rule (Issue 5 fix): mapping wins iff non-empty.
        if self.expected_reports_per_baseline:
            return self.expected_reports_per_baseline[baseline_id]  # KeyError if absent
        if self.expected_total_reports is not None:
            return self.expected_total_reports
        raise KeyError(baseline_id)
