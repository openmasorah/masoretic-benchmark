"""D-13 two-layer ScopeViolation preflight tests.

Plan 03-02 Task 2 behavior tests 1 + 2:
  - Test 1 (D-13a script-start): folio_ids contains an id NOT in the
    Leningrad-frozen set -> ScopeViolation BEFORE infer_folio is called.
  - Test 2 (D-13b per-folio re-check): manifest mutated mid-run so a
    folio's manuscript flips to "cairo" -> ScopeViolation BEFORE that
    folio's infer_folio runs.
"""

from __future__ import annotations

import pytest
from baselines._base import BaselineBase, LineRecord
from baselines._errors import ScopeViolation

from tests._fake_manifest import FakeFolio, FakeManifest


class _SpyBaseline(BaselineBase):
    """Test double that records every infer_folio call."""

    BASELINE_ID = "biblia_kraken"

    def __init__(self, manifest, results_root, **kw):
        super().__init__(manifest, results_root, **kw)
        self.calls: list[str] = []

    def infer_folio(self, folio):
        self.calls.append(folio.id)
        return [
            LineRecord(
                line_id=f"{folio.id}_L001",
                bbox=(0, 0, 1, 1),
                tier1="א",
                tier2="א",
                tier3="א",
                tier4_records=(),
            )
        ]


def _ctor(tmp_path, manifest):
    """Construct a spy baseline against a FakeManifest, bypassing the
    masoretic_eval.manifest.Manifest.load call inside BaselineBase.__init__.

    BaselineBase expects manifest_path; we monkey-patch __init__ side via
    direct attribute set since the FakeManifest has the required surface.
    """
    bl = _SpyBaseline.__new__(_SpyBaseline)
    bl.manifest = manifest
    bl.results_root = tmp_path
    bl.replay = False
    bl.calls = []
    if not bl.BASELINE_ID:
        raise AssertionError("subclass must set BASELINE_ID")
    return bl


def test_d13a_preflight_rejects_non_leningrad_folio_id(tmp_path):
    """Script-start preflight: --folio-id outside frozen-Leningrad set raises
    ScopeViolation BEFORE any infer_folio call."""
    manifest = FakeManifest(
        folios=[FakeFolio(id="leningrad_devarim_F118B_fixture")],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )
    bl = _ctor(tmp_path, manifest)

    with pytest.raises(ScopeViolation, match=r"BL-08.*not_in_scope"):
        bl.run(folio_ids=["not_in_scope"])

    assert bl.calls == [], "infer_folio must NOT have been called"
    # Sandbox should be empty (preflight fails before sandbox enter)
    assert (
        not (tmp_path / ".in_progress").exists()
        or not any((tmp_path / ".in_progress" / "biblia_kraken").iterdir())
        if (tmp_path / ".in_progress" / "biblia_kraken").exists()
        else True
    )


def test_d13a_preflight_accepts_in_scope_folio_id(tmp_path):
    """Sanity: a folio_id that IS in the Leningrad-frozen set passes preflight."""
    fid = "leningrad_devarim_F118B_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )
    bl = _ctor(tmp_path, manifest)
    rc = bl.run(folio_ids=[fid])
    assert rc == 0
    assert bl.calls == [fid]


def test_d13b_per_folio_recheck_catches_manuscript_mutation(tmp_path):
    """Per-folio re-check: between iter_folios and infer_folio, if the
    folio's manuscript flips to non-leningrad, ScopeViolation fires
    BEFORE infer_folio runs.
    """
    fid_ok = "leningrad_devarim_F118B_fixture"
    fid_bad = "cairo_shmuel_smuggle"

    manifest = FakeManifest(
        folios=[FakeFolio(id=fid_ok), FakeFolio(id=fid_bad, manuscript="leningrad")],
        expected_reports_per_baseline={"biblia_kraken": 2},
    )

    # Subclass that mutates the manifest mid-run between two folios
    class MutatingBaseline(_SpyBaseline):
        BASELINE_ID = "biblia_kraken"

        def infer_folio(self, folio):
            # AFTER the first (legitimate) folio is processed, flip
            # the second folio's manuscript label so the per-folio
            # re-check trips on the next iteration.
            self.calls.append(folio.id)
            for i, f in enumerate(manifest.folios):
                if f.id == fid_bad:
                    manifest.folios[i] = FakeFolio(id=fid_bad, manuscript="cairo")
            return [
                LineRecord(
                    line_id=f"{folio.id}_L001",
                    bbox=(0, 0, 1, 1),
                    tier1="א",
                    tier2="א",
                    tier3="א",
                    tier4_records=(),
                )
            ]

    bl2 = MutatingBaseline.__new__(MutatingBaseline)
    bl2.manifest = manifest
    bl2.results_root = tmp_path
    bl2.replay = False
    bl2.calls = []

    with pytest.raises(ScopeViolation) as ei:
        bl2.run()

    msg = str(ei.value)
    assert "BL-08" in msg
    assert fid_bad in msg
    assert "cairo" in msg

    # The first (good) folio was processed; the second (mutated) was NOT.
    assert bl2.calls == [fid_ok], f"unexpected call order: {bl2.calls}"


def test_d13b_per_folio_recheck_catches_in_frozen_scope_flip(tmp_path):
    """Per-folio re-check: in_frozen_scope: true -> false trips
    ScopeViolation. Phase-1 01-12 narrowing rule allows this flip;
    Phase-3 baselines refuse to score outside the frozen set."""
    fid = "leningrad_devarim_F118B_fixture"
    manifest = FakeManifest(
        folios=[FakeFolio(id=fid)],
        expected_reports_per_baseline={"biblia_kraken": 1},
    )
    # Mutate before run so iter_folios sees the flipped folio
    # (script-start preflight does NOT see this folio because
    # frozen_leningrad_folios filters it out, so we put a SECOND
    # in-scope folio first to ensure the loop runs.)
    fid2 = "second_leningrad_folio"
    manifest.folios.insert(0, FakeFolio(id=fid2, manuscript="leningrad", in_frozen_scope=True))
    manifest.expected_reports_per_baseline["biblia_kraken"] = 2

    # Now flip the second folio's in_frozen_scope to False; iter_folios
    # filters it out via frozen_leningrad_folios, so it is never iterated.
    # To exercise per-folio re-check on the in_frozen_scope path, we mutate
    # AFTER iter_folios has resolved its first batch — emulate by mutating
    # mid-iteration in infer_folio.
    class FlipperBaseline(_SpyBaseline):
        BASELINE_ID = "biblia_kraken"

        def infer_folio(self, folio):
            self.calls.append(folio.id)
            for i, f in enumerate(manifest.folios):
                if f.id == fid:
                    manifest.folios[i] = FakeFolio(
                        id=fid, manuscript="leningrad", in_frozen_scope=False
                    )
            return []

    bl2 = FlipperBaseline.__new__(FlipperBaseline)
    bl2.manifest = manifest
    bl2.results_root = tmp_path
    bl2.replay = False
    bl2.calls = []

    with pytest.raises(ScopeViolation, match=r"BL-08.*not in frozen scope"):
        bl2.run()
    assert bl2.calls == [fid2]
