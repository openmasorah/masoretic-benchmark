#!/usr/bin/env python3
"""REL-09: pre-release egress audit.

Distinct from ``reject_private_paths.py`` (pre-commit guard, per-commit fire),
this script runs once at release-tag time and in the tag-push CI workflow that
Plan 04-04 wires. Defense in depth matters here: commit-time hooks catch local
mistakes early, while this release-time audit checks the complete public-bound
tree before a benchmark tag can ship.

Checks performed:
  1. Every folio in phase_0_manifest.json has manuscript == "leningrad" and
     book == "devarim".
  2. No tracked file lives under a path segment named scans.
  3. No tracked file contains the imported private-path denylist.
  4. No tracked file contains private corpus names outside audit-aware files.
  5. No tracked file contains "baalshem" outside BAALSHEM_WHITELIST.
     --ignore-baalshem-strings remains only as a deprecated compatibility flag.
  6. Every results/*/*.json manifest_hash matches phase_0_manifest.json.
  7. leaderboard.json validates against schemas/leaderboard.schema.json.
  8. iaa_report.json validates against schemas/iaa_report.schema.json.
  9. data/README.md YAML frontmatter, if present, contains required HF keys.
 10. --check-brand-words scans public copy for scholar-poison words.
 11. --release-tier requires iaa_report.json, if present, to carry
     iaa_status == "real".

Usage:
  python scripts/audit_release.py [--strict] [--ignore-baalshem-strings]
                                  [--check-brand-words] [--all]
                                  [--root PATH]

Exit codes:
  0  all checks passed
  1  one or more checks fired
  2  internal error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from reject_private_paths import DENYLIST as REJECT_DENYLIST  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT_DEFAULT))

BAALSHEM_WHITELIST = frozenset(
    {
        "scripts/audit_release.py",
        "scripts/reject_private_paths.py",
        "scripts/reject_binaries.py",
        "scripts/manifest_immutable.py",
        "tests/test_reject_private_paths.py",
        "tests/test_no_private_paths.py",
        "phase_0_manifest.json",
        "tests/release/test_audit_release_red_team.py",
        "tests/release/fixtures/planted_baalshem_string.txt",
        "tests/release/test_iaa_report_schema.py",
        "codebase-review/historical/ARCH-01_REPORT.md",
        "codebase-review/historical/DEVOPS-01_REPORT.md",
        "codebase-review/historical/DEBT-01_REPORT.md",
        "codebase-review/historical/DATA-01_REPORT.md",
        "codebase-review/historical/SHARED_BRIEF.md",
        "codebase-review/historical/FINAL_REVIEW.md",
        "codebase-review/historical/TEST-01_REPORT.md",
    }
)

PRIVATE_CORPUS_WHITELIST = BAALSHEM_WHITELIST | frozenset(
    {
        "baselines/tests/test_scope_violation.py",
        "masoretic_eval/schemas/phase_0_manifest.schema.json",
        "schemas/phase_0_manifest.schema.json",
        "scripts/reject_binaries.py",
        "tests/release/fixtures/planted_cairo_shmuel.json",
        "tests/test_manifest_v02_fields.py",
    }
)

PRIVATE_CORPUS_PATTERNS = (
    "Cairo Shmuel",
    "cairo_shmuel",
    "El Códice",
    "El Codice",
    "el_codice",
)
POISON_WORDS = (
    "best",
    "definitive",
    "most accurate",
    "deciphering",
    "finally",
    "Founder of",
)
BRAND_WORD_FILES = (
    "README.md",
    "METHODOLOGY.md",
    "LIMITATIONS.md",
    "data/README.md",
)
BAALSHEM_FULLWORD = re.compile(r"\b" + "baal" + "shem" + r"\b", re.IGNORECASE)


class AuditInternalError(RuntimeError):
    """Raised when a release audit input is unreadable or malformed."""


def _tracked_files(root: Path) -> list[Path]:
    """Return the git-tracked files under root, excluding untracked local files."""
    out = subprocess.check_output(["git", "-C", str(root), "ls-files"], text=True)
    return [root / line for line in out.splitlines() if line]


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AuditInternalError(f"{path} unreadable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AuditInternalError(f"{path} is not valid JSON: {exc}") from exc


def _iter_text_lines(path: Path) -> list[tuple[int, str]]:
    try:
        return list(enumerate(_read_text(path).splitlines(), 1))
    except OSError:
        return []


def _manifest(root: Path) -> dict[str, object]:
    manifest_path = root / "phase_0_manifest.json"
    if not manifest_path.exists():
        raise AuditInternalError(f"phase_0_manifest.json not found at {manifest_path}")
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise AuditInternalError("phase_0_manifest.json must be a JSON object")
    return manifest


def _manifest_hash(root: Path) -> str | None:
    manifest = _manifest(root)
    top_level_hash = manifest.get("manifest_hash")
    if isinstance(top_level_hash, str) and top_level_hash:
        return top_level_hash
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def check_leningrad_devarim(root: Path) -> list[str]:
    """REL-09: every manifest folio must be Leningrad Devarim."""
    errors: list[str] = []
    manifest = _manifest(root)
    folios = manifest.get("folios", [])
    if not isinstance(folios, list):
        return ["audit-fail: phase_0_manifest.json::folios is not an array"]
    for folio in folios:
        if not isinstance(folio, dict):
            errors.append("audit-fail: phase_0_manifest.json::folios contains non-object row")
            continue
        folio_id = folio.get("folio_id") or folio.get("id") or "<unknown>"
        if folio.get("manuscript") != "leningrad":
            errors.append(
                "audit-fail: "
                f"folio {folio_id} has manuscript={folio.get('manuscript')!r} "
                "(expected 'leningrad' per REL-09)"
            )
        if folio.get("book") != "devarim":
            errors.append(
                "audit-fail: "
                f"folio {folio_id} has book={folio.get('book')!r} "
                "(expected 'devarim' per REL-09)"
            )
    return errors


def check_no_scans_dir(root: Path) -> list[str]:
    """REL-09: no tracked file can live under scans/."""
    errors: list[str] = []
    for path in _tracked_files(root):
        rel = _rel(root, path)
        if "scans" in Path(rel).parts:
            errors.append(f"audit-fail: {rel}: tracked file under scans/")
    return errors


def check_denylist(root: Path) -> list[str]:
    """REL-09: no tracked file contains private workstation denylist content."""
    errors: list[str] = []
    for path in _tracked_files(root):
        rel = _rel(root, path)
        if rel in BAALSHEM_WHITELIST:
            continue
        text = _read_text(path)
        for needle in REJECT_DENYLIST:
            if "baal" + "shem" in needle.lower():
                continue
            if needle in text:
                errors.append(f"audit-fail: {rel}: contains denylist needle {needle!r}")
    return errors


def check_private_corpus_terms(root: Path) -> list[str]:
    """REL-09: no tracked file contains private corpus names outside audit fixtures."""
    errors: list[str] = []
    for path in _tracked_files(root):
        rel = _rel(root, path)
        if rel in PRIVATE_CORPUS_WHITELIST:
            continue
        for lineno, line in _iter_text_lines(path):
            for needle in PRIVATE_CORPUS_PATTERNS:
                if needle.lower() in line.lower():
                    errors.append(f"audit-fail: {rel}:{lineno}: contains {needle!r}")
    return errors


def check_baalshem_strings(root: Path) -> list[str]:
    """REL-09: no tracked file contains 'baalshem' outside the explicit whitelist."""
    errors: list[str] = []
    for path in _tracked_files(root):
        rel = _rel(root, path)
        if rel in BAALSHEM_WHITELIST:
            continue
        for lineno, line in _iter_text_lines(path):
            if BAALSHEM_FULLWORD.search(line):
                errors.append(f"audit-fail: {rel}:{lineno}: contains 'baalshem'")
    return errors


def check_results_manifest_hash(root: Path) -> list[str]:
    """REL-09: results files with manifest_hash must bind to the frozen manifest."""
    errors: list[str] = []
    expected = _manifest_hash(root)
    if not expected:
        return ["audit-fail: phase_0_manifest hash is missing or empty"]
    results_dir = root / "results"
    if not results_dir.exists():
        return errors
    # rglob, not glob("*/*.json"): the latter is one level deep and silently
    # skipped results/<baseline>/diagnostic/*.gt_fed.json, which do carry a
    # manifest_hash. A stale binding there passed the release gate.
    for path in results_dir.rglob("*.json"):
        try:
            data = _read_json(path)
        except AuditInternalError as exc:
            errors.append(f"audit-fail: {_rel(root, path)} unreadable: {exc}")
            continue
        if not isinstance(data, dict):
            continue
        actual = data.get("manifest_hash")
        if actual is not None and actual != expected:
            errors.append(
                f"audit-fail: {_rel(root, path)}::manifest_hash={actual!r} "
                f"mismatches phase_0_manifest.json::manifest_hash={expected!r}"
            )
    return errors


def _validate_json_schema(root: Path, payload_name: str, schema_name: str) -> list[str]:
    payload_path = root / payload_name
    schema_path = root / "schemas" / schema_name
    if not payload_path.exists() or not schema_path.exists():
        return []
    try:
        import jsonschema
    except ImportError as exc:
        raise AuditInternalError("jsonschema is required for release schema validation") from exc
    try:
        schema = _read_json(schema_path)
        payload = _read_json(payload_path)
        jsonschema.Draft202012Validator(schema).validate(payload)
    except jsonschema.ValidationError as exc:
        return [f"audit-fail: {payload_name} fails schema: {exc.message}"]
    return []


def check_leaderboard_schema(root: Path) -> list[str]:
    """REL-09: leaderboard.json validates when present."""
    return _validate_json_schema(root, "leaderboard.json", "leaderboard.schema.json")


def check_iaa_report_schema(root: Path) -> list[str]:
    """REL-09: iaa_report.json validates when present."""
    return _validate_json_schema(root, "iaa_report.json", "iaa_report.schema.json")


def check_dataset_card_yaml(root: Path) -> list[str]:
    """REL-09: HF dataset card metadata frontmatter has required keys when present."""
    card = root / "data" / "README.md"
    if not card.exists():
        return []
    text = card.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ["audit-fail: data/README.md missing YAML frontmatter"]
    try:
        _, yaml_text, _ = text.split("---", 2)
    except ValueError:
        return ["audit-fail: data/README.md malformed YAML frontmatter"]
    missing = [
        key for key in ("language:", "license:", "tags:") if key.lower() not in yaml_text.lower()
    ]
    if missing:
        return [f"audit-fail: data/README.md missing metadata keys: {', '.join(missing)}"]
    return []


def check_brand_words(root: Path) -> list[str]:
    """REL-09: public copy avoids scholar-poison words from the brand spec."""
    errors: list[str] = []
    for rel in BRAND_WORD_FILES:
        path = root / rel
        if not path.exists():
            continue
        for lineno, line in _iter_text_lines(path):
            for word in POISON_WORDS:
                if word.lower() in line.lower():
                    errors.append(f"audit-fail: {rel}:{lineno}: scholar-poison-word {word!r}")
    return errors


def check_iaa_report_real(root: Path) -> list[str]:
    """REL-09: reject placeholder IAA reports at release-tag time."""
    rep = root / "iaa_report.json"
    if not rep.exists():
        return []
    payload = _read_json(rep)
    if not isinstance(payload, dict):
        return ["audit-fail: iaa_report.json must be a JSON object"]
    status = payload.get("iaa_status")
    if status == "real":
        return []
    return [
        "audit-fail: iaa_report.json has "
        f"iaa_status={status!r} (expected 'real'); placeholder iaa_report.json "
        "must NOT ship in a release tag (BLOCKER 4 / WARNING 6 sentinel)"
    ]


def _is_release_ref() -> bool:
    ref = os.environ.get("GITHUB_REF", "")
    return ref.startswith("refs/tags/benchmark-v")


def _base_checks(
    ignore_baalshem_strings: bool,
    release_tier: bool,
) -> list[tuple[str, Callable[[Path], list[str]]]]:
    checks: list[tuple[str, Callable[[Path], list[str]]]] = [
        ("leningrad_devarim", check_leningrad_devarim),
        ("no_scans_dir", check_no_scans_dir),
        ("denylist", check_denylist),
        ("private_corpus_terms", check_private_corpus_terms),
        ("results_manifest_hash", check_results_manifest_hash),
        ("leaderboard_schema", check_leaderboard_schema),
        ("iaa_report_schema", check_iaa_report_schema),
        ("dataset_card_yaml", check_dataset_card_yaml),
    ]
    if release_tier or _is_release_ref():
        checks.append(("iaa_report_real", check_iaa_report_real))
    if not ignore_baalshem_strings:
        checks.append(("baalshem_strings", check_baalshem_strings))
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT_DEFAULT))
    parser.add_argument("--strict", action="store_true", help="kept for CI readability")
    parser.add_argument(
        "--ignore-baalshem-strings",
        action="store_true",
        help=(
            "DEPRECATED: was used during the Plan 04-03 rename window; "
            "rename is complete and audit defaults reject baalshem strings."
        ),
    )
    parser.add_argument("--check-brand-words", action="store_true")
    parser.add_argument(
        "--release-tier",
        action="store_true",
        help=(
            "Enforce tag/rc-only release blockers, including iaa_status == 'real'. "
            "Also auto-enforced when GITHUB_REF is refs/tags/benchmark-v*."
        ),
    )
    parser.add_argument("--all", action="store_true", help="run all checks after first failure")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    checks = _base_checks(args.ignore_baalshem_strings, args.release_tier)
    if args.check_brand_words:
        checks.append(("brand_words", check_brand_words))

    all_errors: list[str] = []
    try:
        for name, fn in checks:
            errors = fn(root)
            if not errors:
                continue
            print(f"\n=== {name} ===", file=sys.stderr)
            for error in errors:
                print(error, file=sys.stderr)
            all_errors.extend(errors)
            if not args.all:
                break
    except (AuditInternalError, subprocess.CalledProcessError) as exc:
        print(f"audit_release: internal error: {exc}", file=sys.stderr)
        return 2

    if all_errors:
        print(f"\naudit_release: {len(all_errors)} failure(s)", file=sys.stderr)
        return 1
    print("audit_release: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
