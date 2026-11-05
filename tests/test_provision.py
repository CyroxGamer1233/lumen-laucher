"""Offline tests for mod provisioning and jar-in-jar dependency detection."""
import io
import json
import tempfile
import zipfile
from pathlib import Path

from lumen.mods import provision
from lumen.mods.manifest import detect_conflicts, scan_folder


def tmp() -> Path:
    return Path(tempfile.mkdtemp())


def _jar_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(name, content if isinstance(content, (bytes, str)) else json.dumps(content))
    return buf.getvalue()


def test_nested_modules_satisfy_dependencies():
    d = tmp()
    inner = _jar_bytes({"fabric.mod.json": {"schemaVersion": 1, "id": "fabric-resource-loader-v0", "version": "1.2.0"}})
    (d / "fabric-api.jar").write_bytes(_jar_bytes({
        "fabric.mod.json": {"schemaVersion": 1, "id": "fabric-api", "version": "0.105.0+1.21.1",
                            "jars": [{"file": "META-INF/jars/inner.jar"}]},
        "META-INF/jars/inner.jar": inner,
    }))
    (d / "other.jar").write_bytes(_jar_bytes({
        "fabric.mod.json": {"schemaVersion": 1, "id": "other", "version": "1.0.0",
                            "depends": {"fabric-resource-loader-v0": ">=1.0.0", "fabric-api": "*"}},
    }))
    assert detect_conflicts(scan_folder(d), "1.21.1") == []


def test_missing_nested_module_still_reported():
    d = tmp()
    (d / "other.jar").write_bytes(_jar_bytes({
        "fabric.mod.json": {"schemaVersion": 1, "id": "other", "version": "1.0.0",
                            "depends": {"fabric-resource-loader-v0": "*"}},
    }))
    issues = detect_conflicts(scan_folder(d), "1.21.1")
    assert len(issues) == 1 and issues[0].severity == "error"


def test_ensure_client_mod_copies_and_replaces_old():
    src, mods = tmp(), tmp() / "mods"
    jar = src / "lumen-client-0.2.0.jar"
    jar.write_bytes(b"jar-bytes")
    mods.mkdir()
    (mods / "lumen-client-0.1.0.jar").write_bytes(b"old")
    real = provision.find_client_jar
    provision.find_client_jar = lambda: jar
    try:
        msg = provision.ensure_client_mod(mods, "1.21.1")
        assert "ready" in msg
        assert (mods / "lumen-client-0.2.0.jar").read_bytes() == b"jar-bytes"
        assert not (mods / "lumen-client-0.1.0.jar").exists()
        other = tmp() / "mods2"
        assert "skipped" in provision.ensure_client_mod(other, "1.20.1")
        assert not other.exists()
    finally:
        provision.find_client_jar = real


def test_find_client_jar_ignores_sources():
    d = tmp()
    (d / "lumen-client-0.2.0.jar").write_bytes(b"a")
    (d / "lumen-client-0.2.0-sources.jar").write_bytes(b"b")
    real = provision.bundled_dir
    provision.bundled_dir = lambda: d
    try:
        assert provision.find_client_jar().name == "lumen-client-0.2.0.jar"
    finally:
        provision.bundled_dir = real


def test_has_mod():
    d = tmp()
    (d / "m.jar").write_bytes(_jar_bytes({"fabric.mod.json": {"schemaVersion": 1, "id": "lumen", "version": "1"}}))
    assert provision.has_mod(d, "lumen") and not provision.has_mod(d, "nope")
    assert not provision.has_mod(d / "missing", "lumen")
