import hashlib
import io
import json
import zipfile

import pytest

from lumen import modpack_installer


def test_modpack_file_download_retries_and_verifies_hash(tmp_path, monkeypatch):
    payload = b"verified mod jar"
    attempts = []

    def open_url(_request, timeout):
        assert timeout == 45
        attempts.append(True)
        if len(attempts) == 1:
            raise TimeoutError("temporary network interruption")
        return io.BytesIO(payload)

    monkeypatch.setattr(modpack_installer, "open_url", open_url)
    entry = {
        "path": "mods/example.jar",
        "hashes": {"sha1": hashlib.sha1(payload).hexdigest()},
        "downloads": ["https://example.test/mod.jar"],
    }

    path, cached = modpack_installer._download_one(tmp_path, entry)

    assert path.read_bytes() == payload
    assert cached is False
    assert len(attempts) == 2


def test_modpack_reports_all_required_files_that_failed(tmp_path, monkeypatch):
    archive_path = tmp_path / "pack.mrpack"
    index = {
        "formatVersion": 1,
        "name": "Broken pack",
        "dependencies": {"minecraft": "1.21.1"},
        "files": [
            {"path": "mods/a.jar", "hashes": {}, "downloads": ["https://example.test/a"]},
            {"path": "mods/b.jar", "hashes": {}, "downloads": ["https://example.test/b"]},
        ],
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("modrinth.index.json", json.dumps(index))

    def fail_one(_root, entry):
        raise RuntimeError(f"unavailable: {entry['path']}")

    monkeypatch.setattr(modpack_installer, "_download_one", fail_one)
    statuses = []
    progress = []

    with pytest.raises(RuntimeError, match="2 required modpack file"):
        modpack_installer.install_modrinth_pack(
            archive_path, tmp_path / "minecraft", tmp_path / "instance",
            statuses.append, lambda current, maximum: progress.append((current, maximum)),
        )

    assert any("mods/a.jar" in status for status in statuses)
    assert any("mods/b.jar" in status for status in statuses)
    assert progress[-1] == (2, 2)
