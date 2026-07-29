# Open Masorah corpus catalog

## Purpose

`manuscripts.yaml` is the canonical, structured catalog of every Hebrew
manuscript referenced anywhere in this benchmark — by `phase_0_manifest.json`,
by baseline runs, by the paper, or by `openmasorah.com`. Entries are validated
against [`../schemas/manuscript.schema.json`](../schemas/manuscript.schema.json)
(JSON Schema 2020-12). Treat this catalog as the single source of truth for
manuscript identity, image-source rights, and per-tier ground-truth licensing;
manifest manuscript ids must exist here before they can land in
`phase_0_manifest.json`.

## Adding a manuscript

1. Copy an existing entry block (the `leningrad` entry is a complete template;
   the `aleppo` entry shows the partial-coverage / not-yet-public shape).
2. Choose a slug for `id` matching `^[a-z][a-z0-9_]*$`. If this manuscript
   will ever appear in `phase_0_manifest.json` `folios[*].manuscript`, the
   slug MUST also exist in the manifest's manuscript enum
   (`schemas/phase_0_manifest.schema.json`). The validator cross-checks the
   manifest -> catalog direction; missing entries fail the hook.
3. Fill `identity`, `image_sources`, `ground_truth`, `pipeline`. `related`
   and `citations` are optional but recommended.
4. For private manuscripts (a collaborator's restricted scans, personal mss):
   set `pipeline.public_distributable: false`. NEVER paste private image URLs or
   scan paths in this file — the `reject-private-paths` pre-commit hook will
   reject the commit.
5. Run `python scripts/validate_corpus.py` locally before committing. The
   hook will run automatically on the next commit that touches `corpus/*.yaml`,
   `schemas/manuscript.schema.json`, or `scripts/validate_corpus.py`.

## Licensing guidance

- Tiers 1-3 GT must declare a clear `license_spdx`. Use a real SPDX id
  (`CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`, `MIT`, etc.) when possible. Use
  `NOASSERTION` only when the upstream source's license is genuinely unclear,
  and document the ambiguity in `notes`.
- Tier-4 metamark GT **data** (mark positions and labels) created in-house is
  **CC0-1.0** — factual annotation observations. The annotation schema and
  taxonomy are CC-BY-4.0 (see `LICENSE.md`). Third-party tier-4 GT must carry the
  upstream SPDX id.
- `image_sources[].rights` should be a URL when the upstream provider
  publishes a machine-readable rights statement (PDM, CC, RightsStatements.org).
  Otherwise use a short human-readable phrase.
- `pipeline.public_distributable: true` requires that EVERY tier and every
  image source is redistributable. If any source is `all_rights_reserved`, set
  `public_distributable: false`. `NOASSERTION` used to mark a **public-domain**
  source (e.g. ancient manuscript text, no rights to assert) does NOT block
  distribution; nor do rights-reserved images that are **reference-only** (IIIF
  links, never redistributed). Document the rationale in `notes`.
- Private/restricted scans must NEVER be referenced via local filesystem
  paths in this file. Use the upstream provider's URL or omit the
  `image_sources` entry entirely.

## Schema reference

The canonical contract lives at
[`../schemas/manuscript.schema.json`](../schemas/manuscript.schema.json).
Controlled vocabularies (defined under `$defs`):

- `coverage_enum`: `complete | partial | sample | none`
- `mark_type_enum` (tier 4): the canonical scorer vocabulary — `pe`, `samekh`,
  `large_letter`, `small_letter`, `suspended_letter`, `inverted_nun`,
  `puncta_extraordinaria`, `circellus`, `rafe`, `double_rafe` — plus four
  catalog-only phenomena that have no positional record type and so can be
  declared as coverage but not scored: `line_filler`, `stichographic_layout`,
  `dotted_letter`, `rashe_tevot`. Defined once in
  [`masoretic_eval/tier4_vocabulary.py`](../masoretic_eval/tier4_vocabulary.py);
  see [`docs/meta_marks_schema.md`](../docs/meta_marks_schema.md) for the
  per-mark table.
- `image_sources[].type`: `iiif_manifest | image_set | text_only |
  single_image`
- `image_sources[].resolution`: `high | medium | low | unknown`
- `image_sources[].coverage`: `complete | partial | sample`
- `pipeline.phase`: integer 0..5 mapping to roadmap phases
- `related[].relation`: `basis_of | compared_with | derived_from |
  superseded_by | references`

## Pre-commit

The `validate-corpus` hook in `.pre-commit-config.yaml` runs
`scripts/validate_corpus.py` automatically when any of the following change:

- `corpus/*.yaml` (the catalog itself)
- `schemas/manuscript.schema.json` (the contract)
- `scripts/validate_corpus.py` (the validator)

Hook deps (`pyyaml`, `jsonschema`) are installed by pre-commit into its
dedicated hook environment via `additional_dependencies`, so the validator
runs regardless of the contributor's local venv state. To run it directly
against your venv: `python scripts/validate_corpus.py` from the repo root.
