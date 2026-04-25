import hashlib
import sys
import types


def test_hash_format_and_determinism(tmp_path, monkeypatch):
    # Synthesize a fake nakdimon module with a known H5 file.
    h5 = tmp_path / "Nakdimon.h5"
    h5.write_bytes(b"FAKE_WEIGHTS_BYTES_FOR_TESTING")
    fake_pkg = types.ModuleType("nakdimon")
    fake_init = tmp_path / "__init__.py"
    fake_init.write_text("")
    fake_pkg.__file__ = str(fake_init)
    monkeypatch.setitem(sys.modules, "nakdimon", fake_pkg)
    # Stub importlib.metadata.version
    monkeypatch.setattr("oracles._hashing.version", lambda _name: "0.1.2")

    from oracles._hashing import _sha256_file, compute_nakdimon_model_hash

    h = compute_nakdimon_model_hash()
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)

    h5_sha = _sha256_file(h5)
    expected = hashlib.sha256(f"nakdimon==0.1.2:{h5_sha}".encode()).hexdigest()[:16]
    assert h == expected
