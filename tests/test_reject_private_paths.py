from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "reject_private_paths.py"
PRIVATE_PATTERNS = (
    "baal" + "shem",
    "Workspace/" + "masorah",
    "/Users/" + "benlamm",
)
# The exact contractually-immutable provenance occurrence in phase_0_manifest.json
# (the append-only changelog row at :71). Legitimately names the codename; must
# stay and must NOT be flagged. Built from fragments so this test file does not
# itself trip the whole-tree scanner.
_IMMUTABLE_PROVENANCE = "baal" + "shem" + "@bc7255ecaa3eb872885467d3a59e9e6352d5668a"


@pytest.fixture()
def reject_private_paths():
    spec = importlib.util.spec_from_file_location("reject_private_paths", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_main_accepts_clean_file(tmp_path, reject_private_paths):
    clean = tmp_path / "clean.txt"
    clean.write_text("public benchmark metadata only\n", encoding="utf-8")

    assert reject_private_paths.main([str(clean)]) == 0


def test_main_rejects_private_path_leaks(tmp_path, reject_private_paths, capsys):
    leaking = tmp_path / "leaking.txt"
    leaking.write_text(
        f"do not publish {PRIVATE_PATTERNS[0]} or {PRIVATE_PATTERNS[1]}\n",
        encoding="utf-8",
    )

    assert reject_private_paths.main([str(leaking)]) == 1
    stderr = capsys.readouterr().err
    assert "REJECT" in stderr
    assert str(leaking) in stderr


def test_main_skips_missing_paths(tmp_path, reject_private_paths):
    missing = tmp_path / "deleted.txt"

    assert reject_private_paths.main([str(missing)]) == 0


def test_main_without_args_scans_git_ls_files(tmp_path, reject_private_paths, monkeypatch):
    clean = tmp_path / "clean.txt"
    clean.write_text("clean\n", encoding="utf-8")
    leaking = tmp_path / "leaking.txt"
    leaking.write_text(f"leak: {PRIVATE_PATTERNS[0]}\n", encoding="utf-8")
    missing = tmp_path / "missing.txt"

    monkeypatch.setattr(
        reject_private_paths,
        "_git_ls_files",
        lambda: [str(clean), str(leaking), str(missing)],
    )

    assert reject_private_paths.main([]) == 1


def test_matching_is_case_insensitive(tmp_path, reject_private_paths):
    leaking = tmp_path / "leaking.txt"
    # Upper-cased codename must still be caught.
    leaking.write_text("see " + "BAAL" + "SHEM" + " in this dump\n", encoding="utf-8")

    assert reject_private_paths.main([str(leaking)]) == 1


def test_metatest_hardcoded_private_literals_are_rejected(tmp_path, reject_private_paths):
    """Anti-regression antibody for the original incident.

    The guard was silently neutered when a rename sweep edited DENYLIST to the
    public org name; tests stayed green because they asserted the renamed value.
    These literals are assembled here INDEPENDENTLY of DENYLIST (never imported
    from it), so a future sweep that blinds the denylist turns this test RED.
    Assembled from fragments so this test file does not itself trip the
    whole-tree scanner.
    """
    codename = tmp_path / "codename.txt"
    codename.write_text("stray ref /home/x/" + "baal" + "shem" + "/gt-infra\n", encoding="utf-8")
    assert reject_private_paths.main([str(codename)]) == 1

    # The operator path entry is equally blind-able by a sweep — pin it too.
    operator = tmp_path / "operator.txt"
    operator.write_text("traceback at " + "/Users/" + "benlamm" + "/x\n", encoding="utf-8")
    assert reject_private_paths.main([str(operator)]) == 1


def test_immutable_manifest_provenance_string_is_exempt(tmp_path, reject_private_paths):
    """The append-only changelog row legitimately names the codename (CLAUDE.md).

    The exact provenance occurrence must pass so the immutable manifest is not
    held hostage by the guard.
    """
    manifest = tmp_path / "phase_0_manifest.json"
    manifest.write_text(
        '{"reason": "import from ' + _IMMUTABLE_PROVENANCE + '; values preserved"}\n',
        encoding="utf-8",
    )

    assert reject_private_paths.main([str(manifest)]) == 0


def test_other_codename_occurrence_is_still_rejected(tmp_path, reject_private_paths):
    """Exemption is pinned to the exact known string — any OTHER occurrence trips.

    Guards against the file-level allowlist failure mode: a real leak dropped
    elsewhere in the manifest must still be caught.
    """
    manifest = tmp_path / "phase_0_manifest.json"
    manifest.write_text(
        '{"reason": "import from ' + "baal" + "shem" + '@deadbeef"}\n',
        encoding="utf-8",
    )

    assert reject_private_paths.main([str(manifest)]) == 1


def test_guard_infra_paths_with_codename_are_exempt(reject_private_paths):
    """The recovered release-audit machinery legitimately carries the codename.

    audit_release.py and its red-team test reference the codename as detection
    logic; the planted fixture IS an intentional leak the red-team test must
    detect. These exact repo-relative paths are exempt for the codename token
    only — mirrors the path whitelist audit_release.py applies for that token.
    """
    codename = "baal" + "shem"
    for rel in (
        "scripts/audit_release.py",
        "tests/release/test_audit_release_red_team.py",
        "tests/release/fixtures/planted_" + codename + "_string.txt",
    ):
        assert reject_private_paths.main([rel]) == 0, rel


def test_path_exemption_is_token_scoped(reject_private_paths):
    """Exemption is pinned to (token, path): a DIFFERENT denylist token in an
    exempt path still trips, and the codename token in any OTHER path still
    trips. This is what keeps the path exemption from becoming a blanket hole.
    """
    codename = "baal" + "shem"
    operator = "/Users/" + "benlamm"
    # The codename is exempt for the audit script...
    assert reject_private_paths._is_path_exempt("scripts/audit_release.py", codename)
    # ...but an operator-path leak in that SAME file is not exempt.
    assert not reject_private_paths._is_path_exempt("scripts/audit_release.py", operator)
    # ...and the codename in a non-listed path is not exempt.
    assert not reject_private_paths._is_path_exempt("masoretic_eval/cli.py", codename)
    assert not reject_private_paths._is_path_exempt(None, codename)
