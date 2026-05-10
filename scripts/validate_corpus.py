"""Validate corpus/manuscripts.yaml against schemas/manuscript.schema.json.

Two checks run in sequence:

1. Schema authoring: Draft202012Validator.check_schema on the JSON Schema
   itself, then Draft202012Validator(schema).iter_errors over each entry in
   corpus/manuscripts.yaml.

2. Cross-check: every manuscript id referenced in phase_0_manifest.json
   folios MUST appear in the catalog. The reverse direction is NOT
   enforced -- the catalog is the wider authority and may legitimately list
   manuscripts the frozen manifest scope has not yet reached.

Exits 0 on success, 1 on validation/cross-check failure, 2 on missing inputs
or import failures.

Wired into pre-commit via the validate-corpus hook in .pre-commit-config.yaml.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover - guidance path
    sys.stderr.write(
        f"[corpus] missing dependency: {exc.name}. Install with: pip install pyyaml jsonschema\n"
    )
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "corpus" / "manuscripts.yaml"
SCHEMA_PATH = REPO_ROOT / "schemas" / "manuscript.schema.json"
MANIFEST_PATH = REPO_ROOT / "phase_0_manifest.json"


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        sys.stderr.write(f"[corpus] catalog not found at {path}\n")
        sys.exit(2)
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_json(path: Path) -> dict:
    if not path.is_file():
        sys.stderr.write(f"[corpus] schema not found at {path}\n")
        sys.exit(2)
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _validate_entries(entries: list[dict], schema: dict, failures: list[str]) -> None:
    validator = Draft202012Validator(schema)
    for index, entry in enumerate(entries):
        entry_label = entry.get("id") if isinstance(entry, dict) else None
        label = entry_label if entry_label else f"index_{index}"
        for error in validator.iter_errors(entry):
            path = list(error.absolute_path)
            msg = f"[corpus] entry {label} FAILED: {error.message} at {path}"
            sys.stderr.write(msg + "\n")
            failures.append(msg)


def _check_duplicates(entries: list[dict], failures: list[str]) -> set[str]:
    catalog_ids: list[str] = [
        entry["id"] for entry in entries if isinstance(entry, dict) and "id" in entry
    ]
    seen: dict[str, int] = {}
    for cid in catalog_ids:
        seen[cid] = seen.get(cid, 0) + 1
    duplicates = sorted(cid for cid, count in seen.items() if count > 1)
    if duplicates:
        msg = f"[corpus] duplicate ids in catalog: {duplicates}"
        sys.stderr.write(msg + "\n")
        failures.append(msg)
    return set(catalog_ids)


def _crosscheck_manifest(catalog_ids: set[str], failures: list[str]) -> None:
    if not MANIFEST_PATH.is_file():
        sys.stderr.write(
            f"[corpus] phase_0_manifest.json not found at {MANIFEST_PATH}; skipping cross-check\n"
        )
        return
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    folios = manifest.get("folios", [])
    manifest_ids: set[str] = {
        folio["manuscript"] for folio in folios if isinstance(folio, dict) and "manuscript" in folio
    }
    missing = sorted(manifest_ids - catalog_ids)
    for mid in missing:
        msg = f"[corpus] manifest references manuscript '{mid}' but catalog has no entry"
        sys.stderr.write(msg + "\n")
        failures.append(msg)


def main() -> int:
    failures: list[str] = []

    schema = _load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)

    doc = _load_yaml(CATALOG_PATH)
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, list) or not entries:
        sys.stderr.write("[corpus] catalog has no `entries` list or it is empty\n")
        return 1

    _validate_entries(entries, schema, failures)
    catalog_ids = _check_duplicates(entries, failures)
    _crosscheck_manifest(catalog_ids, failures)

    if failures:
        sys.stderr.write(f"[corpus] FAILED: {len(failures)} issue(s); see messages above\n")
        return 1

    print(f"[corpus] OK: {len(entries)} entries valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
