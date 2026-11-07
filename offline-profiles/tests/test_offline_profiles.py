"""Offline profile manager: deterministic identities, isolated storage, no keystore/network."""
import json, sys, tempfile, uuid
from pathlib import Path

from lumen.auth.offline import OFFLINE_TOKEN, offline_account, offline_uuid
from lumen.auth.profiles import OfflineProfileStore, ProfileError
from lumen.auth.store import AccountStore


def tmp() -> Path:
    return Path(tempfile.mkdtemp())


def test_uuid_is_deterministic_v3_for_any_string():
    for name in ("Steve", "a", "x" * 40, "ñame with spaces", ""):
        u = uuid.UUID(offline_uuid(name))
        assert u.version == 3 and u.variant == uuid.RFC_4122
        assert offline_uuid(name) == offline_uuid(name)
    assert offline_uuid("Steve") != offline_uuid("steve")          # case-sensitive, like vanilla


def test_uuid_matches_vanilla_scheme_not_namespaced_uuid3():
    import hashlib
    raw = bytearray(hashlib.md5(b"OfflinePlayer:Steve").digest())
    raw[6] = (raw[6] & 0x0F) | 0x30
    raw[8] = (raw[8] & 0x3F) | 0x80
    assert offline_uuid("Steve") == str(uuid.UUID(bytes=bytes(raw)))
    ns = uuid.UUID("14ee085c-c073-3be6-8a3b-ac83387b003a")
    assert offline_uuid("Steve") != str(uuid.uuid3(ns, "OfflinePlayer:Steve"))   # documented difference


def test_offline_account_uses_static_placeholder_token():
    a = offline_account("Steve")
    assert a.kind == "offline" and a.access_token == OFFLINE_TOKEN
    assert len(OFFLINE_TOKEN) == 32 and set(OFFLINE_TOKEN) <= set("0123456789abcdef")


def test_profile_store_roundtrip_and_last_used():
    d = tmp()
    ps = OfflineProfileStore(d / "offline_profiles.json")
    assert ps.names() == [] and ps.last_used() is None
    a = ps.select("Bench_1")
    b = ps.select(None, default="Player")                           # falls back to last used
    assert a.uuid == b.uuid and ps.last_used() == "Bench_1"
    ps.add("Other")
    assert ps.names() == ["Bench_1", "Other"]
    assert ps.get("Other").uuid == offline_uuid("Other")
    assert ps.remove("Bench_1") and ps.last_used() is None and not ps.remove("Bench_1")


def test_profile_store_rejects_bad_names_and_unknown_profiles():
    ps = OfflineProfileStore(tmp() / "p.json")
    for bad in ("ab", "x" * 17, "bad name"):
        try:
            ps.add(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    try:
        ps.select("bad name")
        raise AssertionError
    except ProfileError:
        pass
    try:
        ps.get("ghost")
        raise AssertionError
    except ProfileError:
        pass


def test_profile_file_is_separate_and_secret_free():
    d = tmp()
    ps = OfflineProfileStore(d / "offline_profiles.json")
    ps.select("Steve")
    blob = (d / "offline_profiles.json").read_text()
    data = json.loads(blob)
    assert set(data) == {"schema", "profiles", "last_used"}
    assert "token" not in blob.lower() and OFFLINE_TOKEN not in blob
    assert not (d / "accounts.json").exists()                       # production index untouched
    assert AccountStore(d / "accounts.json").list_accounts() == {}


def test_corrupt_profile_file_is_tolerated():
    d = tmp()
    (d / "p.json").write_text("{not json")
    ps = OfflineProfileStore(d / "p.json")
    assert ps.names() == []
    ps.add("Steve")
    assert ps.names() == ["Steve"]


def test_profiles_module_does_not_import_keyring_or_httpx():
    import importlib
    for m in ("keyring", "httpx"):
        sys.modules.pop(m, None)
    import lumen.auth.profiles as p
    importlib.reload(p)
    assert "keyring" not in sys.modules and "httpx" not in sys.modules
