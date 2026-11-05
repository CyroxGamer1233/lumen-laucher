"""Offline unit tests (no network, no Minecraft install). Plain asserts; fixtures avoided on purpose."""
import base64, json, tempfile, uuid, zipfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from lumen import config
from lumen.auth.offline import offline_account, offline_uuid
from lumen.launch.jvm import build_jvm_args, pick_heap_mb
from lumen.logging_setup import redact
from lumen.mods.manifest import ModInfo, detect_conflicts, read_fabric_mod, satisfies
from lumen.net.verify import ChecksumError, file_hash, safe_extract, verify
from lumen.updater.updater import canonical, parse_manifest


def tmp() -> Path:
    return Path(tempfile.mkdtemp())


def test_offline_uuid_is_v3_and_stable():
    u = uuid.UUID(offline_uuid("Steve"))
    assert u.version == 3 and offline_uuid("Steve") == offline_uuid("Steve")
    assert offline_uuid("Steve") != offline_uuid("Alex")


def test_offline_name_validation():
    for bad in ("ab", "x" * 17, "bad name", "ñame"):
        try:
            offline_account(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_jvm_heap_and_flags():
    assert pick_heap_mb(8192, "balanced") == 2703            # 33% of 8 GB
    assert pick_heap_mb(65536, "balanced") == 6144           # capped
    assert pick_heap_mb(4096, "low_end") >= 1536
    a = build_jvm_args("balanced", total_mb=16384)
    assert a[0] == a[1].replace("Xmx", "Xms") and "-XX:+UseG1GC" in a
    assert "-XX:+AlwaysPreTouch" in build_jvm_args("high_end", total_mb=16384)
    assert "-XX:+AlwaysPreTouch" not in a


def test_version_ranges():
    assert satisfies("1.21.1", ">=1.21 <1.22")
    assert not satisfies("1.20.4", ">=1.21")
    assert satisfies("1.21.1", "1.21.x") and satisfies("0.5.3", "*")
    assert satisfies("1.0.0", ["<0.9", ">=1.0"]) and satisfies("1.4.2", "^1.2")
    assert not satisfies("2.0.0", "^1.2") and satisfies("1.2.9", "~1.2.3")


def _mod(mid, ver="1.0.0", **kw):
    return ModInfo(mid, ver, Path(f"{mid}.jar"), **kw)


def test_conflict_detection():
    mods = [
        _mod("a", depends={"b": ">=2.0", "missing": "*"}),
        _mod("b", "1.5.0"),
        _mod("c", breaks={"b": "<2"}),
        _mod("d", conflicts={"b": "*"}, recommends={"zzz": "*"}),
        _mod("b", "1.5.0"),                                   # duplicate id
    ]
    msgs = [(i.severity, i.mod_id, i.message) for i in detect_conflicts(mods, "1.21.1")]
    text = "\n".join(m[2] for m in msgs)
    assert "requires b >=2.0, found 1.5.0" in text
    assert "requires 'missing'" in text
    assert any(s == "error" and m == "c" for s, m, _ in msgs)
    assert any(s == "warn" and m == "d" for s, m, _ in msgs)
    assert "Duplicate mod id" in text


def test_provides_satisfies_dependency_and_minecraft():
    mods = [_mod("fabric-api", "0.105.0", provides=["fabric"]), _mod("x", depends={"fabric": "*", "minecraft": "~1.21"})]
    assert detect_conflicts(mods, "1.21.1") == []


def test_read_fabric_mod_from_jar():
    d = tmp()
    j = d / "m.jar"
    with zipfile.ZipFile(j, "w") as z:
        z.writestr("fabric.mod.json", json.dumps({"schemaVersion": 1, "id": "demo", "version": "2.0", "depends": {"minecraft": "1.21.x"}}))
    m = read_fabric_mod(j)
    assert m and m.id == "demo" and m.depends["minecraft"] == "1.21.x"
    (d / "bad.jar").write_bytes(b"not a zip")
    assert read_fabric_mod(d / "bad.jar") is None


def test_checksum_and_zip_slip():
    d = tmp()
    f = d / "f.bin"
    f.write_bytes(b"hello")
    verify(f, file_hash(f, "sha256"))
    try:
        verify(f, "0" * 64)
        raise AssertionError("should fail")
    except ChecksumError:
        pass
    z = d / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../escape.txt", "x")
    try:
        safe_extract(z, d / "out")
        raise AssertionError("should fail")
    except ValueError:
        pass
    assert not (d / "escape.txt").exists()


def test_redaction():
    s = redact("--accessToken eyJhbGciOiJIUzI1NiJ9.abcdefghijk.sig123 Authorization: Bearer abc.def.ghi refresh_token=SECRET1")
    assert "eyJ" not in s and "abc.def.ghi" not in s and "SECRET1" not in s


def test_settings_export_import_roundtrip():
    d = tmp()
    s = config.Settings(ram_mb=4096, java_path="/opt/java/bin/java", jvm_profile="high_end")
    config.export_settings(s, d / "x.json")
    blob = json.loads((d / "x.json").read_text())
    assert "java_path" not in blob["settings"]
    out = config.import_settings(d / "x.json", config.Settings(java_path="/mine/java"))
    assert out.ram_mb == 4096 and out.jvm_profile == "high_end" and out.java_path == "/mine/java"
    (d / "bad.json").write_text(json.dumps({"app": "other", "schema": 1}))
    try:
        config.import_settings(d / "bad.json", s)
        raise AssertionError
    except ValueError:
        pass


def test_settings_clamped():
    assert config.load(Path("/nonexistent/x.json")).loader == "fabric"
    s = config._validate(config.Settings(ram_mb=999999, jvm_profile="evil", offline_username="a b!c"))
    assert s.ram_mb == 32768 and s.jvm_profile == "balanced" and s.offline_username == "abc"


def test_update_manifest_signature():
    key = Ed25519PrivateKey.generate()
    pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    payload = {"version": "0.2.0", "notes": "n", "assets": {"win": {"url": "https://x/y.exe", "sha256": "ab" * 32}}}
    man = {"payload": payload, "signature": base64.b64encode(key.sign(canonical(payload))).decode()}
    up = parse_manifest(man, pub, "0.1.0", "win")
    assert up and up.version == "0.2.0"
    assert parse_manifest(man, pub, "0.2.0", "win") is None            # already current
    man["payload"]["assets"]["win"]["url"] = "https://evil/y.exe"       # tamper
    try:
        parse_manifest(man, pub, "0.1.0", "win")
        raise AssertionError
    except ValueError:
        pass
