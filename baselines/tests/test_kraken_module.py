"""Tests for the shared baselines._kraken wrapper + baselines._images helper.

Wave 3 plans (03-05 BL-03, 03-06 BL-04, 03-07 BL-01) import the following
symbols by name:

    from baselines._kraken import recognize_lines, KRAKEN_MODEL_HASH
    from baselines._images import fetch_image, image_sha256

The contract is structural: signatures and module-level constants are
load-bearing. These tests pin the shape so a wave-3 import never breaks
silently.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------
# baselines._kraken
# ---------------------------------------------------------------------


def test_kraken_model_hash_is_16_hex_chars():
    from baselines._kraken import KRAKEN_MODEL_HASH

    assert isinstance(KRAKEN_MODEL_HASH, str)
    assert re.fullmatch(r"[0-9a-f]{16}", KRAKEN_MODEL_HASH), (
        f"KRAKEN_MODEL_HASH not 16 hex chars: {KRAKEN_MODEL_HASH!r}"
    )


def test_kraken_model_hash_derives_from_pin_md():
    """Verify the constant is canonical-from-the-pin: re-derive from the pin
    row sha256 and compare. If the pin gets bumped, the constant moves."""
    from baselines._kraken import KRAKEN_MODEL_HASH, KRAKEN_VERSION

    REPO_ROOT = Path(__file__).resolve().parents[2]
    pin_md = (REPO_ROOT / "baselines" / "KRAKEN_PIN.md").read_text(encoding="utf-8")
    rows = [r for r in pin_md.splitlines() if r.startswith("| 2026-")]
    assert rows
    cols = [c.strip() for c in rows[0].strip("|").split("|")]
    pinned_sha = cols[3]
    seed = f"kraken=={KRAKEN_VERSION}:{pinned_sha}".encode("utf-8")
    expected = hashlib.sha256(seed).hexdigest()[:16]
    assert KRAKEN_MODEL_HASH == expected


def test_recognize_lines_signature_exported():
    """Wave 3 plans (03-05/03-06/03-07) import recognize_lines by name."""
    from baselines._kraken import recognize_lines

    assert callable(recognize_lines)


def test_recognize_lines_returns_line_records_with_kraken_confidence():
    """Per D-04: per-line LineRecord.kraken_confidence populated as the mean
    of per-character confidences from rpred.rpred."""
    from baselines._base import LineRecord

    fake_image = MagicMock()
    fake_baseline = MagicMock()
    fake_network = MagicMock()

    # Two fake ocr_record objects — minimum kraken yields per line.
    fake_records = []
    for text, confs, bbox in [
        ("שמע", [0.9, 0.85, 0.95], (10, 20, 500, 60)),
        ("ישראל", [0.7, 0.8, 0.9, 0.6, 0.85], (10, 80, 500, 120)),
    ]:
        rec = MagicMock()
        rec.__str__ = lambda self, t=text: t
        rec.confidences = confs
        rec.line_bbox = bbox
        fake_records.append(rec)

    image_open = MagicMock(return_value=MagicMock(convert=MagicMock(return_value=fake_image)))

    with patch("PIL.Image.open", image_open), \
         patch("kraken.blla.segment", return_value=fake_baseline), \
         patch("kraken.rpred.rpred", return_value=iter(fake_records)), \
         patch("baselines._kraken._load_model", return_value=fake_network):
        from baselines._kraken import recognize_lines
        out = recognize_lines(
            Path("/tmp/fake.jpg"),
            Path("/tmp/fake.mlmodel"),
            folio_id="leningrad_devarim_F195A",
        )

    assert isinstance(out, list)
    assert len(out) == 2
    assert all(isinstance(r, LineRecord) for r in out)
    # Per-char confidence mean
    assert out[0].tier1 == "שמע"
    assert 0.0 <= out[0].kraken_confidence <= 1.0
    assert abs(out[0].kraken_confidence - (0.9 + 0.85 + 0.95) / 3) < 1e-3
    assert out[0].line_id.startswith("leningrad_devarim_F195A_L")


def test_recognize_lines_raises_on_zero_records():
    """D-04: full-page Kraken failure (zero records) raises KrakenInferenceFailure
    naming the image path / folio id. SandboxRun __exit__ on exception leaves
    .in_progress/<bl>/ for inspection per D-14."""
    from baselines._errors import KrakenInferenceFailure

    fake_image = MagicMock()
    image_open = MagicMock(return_value=MagicMock(convert=MagicMock(return_value=fake_image)))

    with patch("PIL.Image.open", image_open), \
         patch("kraken.blla.segment", return_value=MagicMock()), \
         patch("kraken.rpred.rpred", return_value=iter([])), \
         patch("baselines._kraken._load_model", return_value=MagicMock()):
        from baselines._kraken import recognize_lines
        with pytest.raises(KrakenInferenceFailure) as exc:
            recognize_lines(
                Path("/tmp/missing.jpg"),
                Path("/tmp/fake.mlmodel"),
                folio_id="leningrad_devarim_FXXX",
            )
        assert "leningrad_devarim_FXXX" in str(exc.value)


def test_recognize_lines_raises_on_all_empty_text():
    """If every record has empty text, raise — there is no transcription
    extractable from the page (per D-04 full-page-failure semantics)."""
    from baselines._errors import KrakenInferenceFailure

    fake_image = MagicMock()
    image_open = MagicMock(return_value=MagicMock(convert=MagicMock(return_value=fake_image)))

    rec = MagicMock()
    rec.__str__ = lambda self: ""
    rec.confidences = []
    rec.line_bbox = (0, 0, 0, 0)

    with patch("PIL.Image.open", image_open), \
         patch("kraken.blla.segment", return_value=MagicMock()), \
         patch("kraken.rpred.rpred", return_value=iter([rec])), \
         patch("baselines._kraken._load_model", return_value=MagicMock()):
        from baselines._kraken import recognize_lines
        with pytest.raises(KrakenInferenceFailure):
            recognize_lines(
                Path("/tmp/blank.jpg"),
                Path("/tmp/fake.mlmodel"),
                folio_id="leningrad_devarim_BLANK",
            )


# ---------------------------------------------------------------------
# baselines._images
# ---------------------------------------------------------------------


def test_fetch_image_signature_exported():
    """Wave 3 plan 03-07 imports fetch_image by name."""
    from baselines._images import fetch_image

    assert callable(fetch_image)


def test_image_sha256_signature_exported():
    """Wave 3 plan 03-07 imports image_sha256 by name."""
    from baselines._images import image_sha256

    assert callable(image_sha256)


def test_image_sha256_matches_hashlib(tmp_path):
    """image_sha256 returns the standard sha256 hex digest of the file."""
    from baselines._images import image_sha256

    payload = b"some-fake-image-bytes-" + b"x" * 1000
    p = tmp_path / "x.jpg"
    p.write_bytes(payload)
    assert image_sha256(p) == hashlib.sha256(payload).hexdigest()


def test_fetch_image_caches_and_skips_second_call(tmp_path):
    """First call writes to cache; second call hits cache, no urlretrieve."""
    from baselines import _images

    folio_id = "leningrad_devarim_F195A"
    url = "https://archive.org/download/leningrad-codex-color/BIB_LENCDX_F195A.jpg"
    cache_dir = tmp_path / "images"

    fake_payload = b"\xff\xd8\xff\xe0fakejpeg"

    def fake_urlretrieve(u, dst):
        Path(dst).write_bytes(fake_payload)

    with patch.object(_images.urllib.request, "urlretrieve", side_effect=fake_urlretrieve) as m:
        out1 = _images.fetch_image(folio_id, url, cache_dir)
        out2 = _images.fetch_image(folio_id, url, cache_dir)

    assert out1 == out2
    assert out1.exists()
    assert out1.read_bytes() == fake_payload
    assert m.call_count == 1, "second call should hit cache, not re-download"


def test_fetch_image_preserves_extension(tmp_path):
    """archive.org URLs end in .jpg — preserve the suffix on the cached path."""
    from baselines import _images

    cache_dir = tmp_path / "images"

    def fake_urlretrieve(u, dst):
        Path(dst).write_bytes(b"x")

    with patch.object(_images.urllib.request, "urlretrieve", side_effect=fake_urlretrieve):
        p = _images.fetch_image(
            "leningrad_devarim_F195B",
            "https://archive.org/download/leningrad-codex-color/BIB_LENCDX_F195B.jpg",
            cache_dir,
        )
    assert p.suffix == ".jpg"
    assert p.name == "leningrad_devarim_F195B.jpg"
