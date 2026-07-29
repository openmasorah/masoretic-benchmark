"""masoretic_eval — 4-tier CER scorer for medieval Hebrew manuscripts."""

#: MUST equal ``[project].version`` in pyproject.toml and ``scorer_version`` in
#: phase_0_manifest.json. This is not a label: ``output_schema.py`` stamps it
#: into every emitted result and ``scripts/verify_gt_hash.py`` writes it into
#: the manifest, from which ``baselines/src/baselines/_base.py`` cascades it
#: into every ``run_meta.json``. All three are asserted equal, against
#: ``importlib.metadata``, by tests/test_scorer_version_cascade.py.
__version__ = "0.3.0"
