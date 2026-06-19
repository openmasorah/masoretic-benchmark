"""Input byte-pinning: mismatch raises IaaInputMismatch unless --force."""

from __future__ import annotations

from pathlib import Path

import pytest

from masoretic_eval.iaa.compute import IaaInputMismatch, compute_iaa

_A = "אבג֯ד׃\n"
_B = "אבג֯ד׃\n"
_VFM = [("Deut.99.1", "F999A")]


def test_matching_sha_passes(tmp_path: Path):
    a_path = tmp_path / "a.txt"
    b_path = tmp_path / "b.txt"
    a_path.write_text(_A, encoding="utf-8")
    b_path.write_text(_B, encoding="utf-8")
    # Read sha first so we pass the *correct* hashes.
    from masoretic_eval.iaa.compute import _sha256

    compute_iaa(
        a_path,
        b_path,
        _VFM,
        bootstrap_b=8,
        expected_a_sha256=_sha256(a_path),
        expected_b_sha256=_sha256(b_path),
    )


def test_mismatched_a_sha_raises(tmp_path: Path):
    a_path = tmp_path / "a.txt"
    b_path = tmp_path / "b.txt"
    a_path.write_text(_A, encoding="utf-8")
    b_path.write_text(_B, encoding="utf-8")
    with pytest.raises(IaaInputMismatch, match="A-side SHA256"):
        compute_iaa(
            a_path,
            b_path,
            _VFM,
            bootstrap_b=8,
            expected_a_sha256="0" * 64,
        )


def test_mismatched_b_sha_raises(tmp_path: Path):
    a_path = tmp_path / "a.txt"
    b_path = tmp_path / "b.txt"
    a_path.write_text(_A, encoding="utf-8")
    b_path.write_text(_B, encoding="utf-8")
    with pytest.raises(IaaInputMismatch, match="B-side SHA256"):
        compute_iaa(
            a_path,
            b_path,
            _VFM,
            bootstrap_b=8,
            expected_b_sha256="0" * 64,
        )


def test_force_bypasses_mismatch(tmp_path: Path):
    a_path = tmp_path / "a.txt"
    b_path = tmp_path / "b.txt"
    a_path.write_text(_A, encoding="utf-8")
    b_path.write_text(_B, encoding="utf-8")
    # force=True: mismatched hashes are ignored.
    result = compute_iaa(
        a_path,
        b_path,
        _VFM,
        bootstrap_b=8,
        expected_a_sha256="0" * 64,
        expected_b_sha256="0" * 64,
        force=True,
    )
    # Metadata still records the actual hashes — provenance not lost.
    assert result.metadata["a_sha256"] != "0" * 64
    assert result.metadata["b_sha256"] != "0" * 64
