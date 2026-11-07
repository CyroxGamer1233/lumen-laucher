"""session.get_account / provision.prepare_mods: the offline path is local-only."""
import json, tempfile
from pathlib import Path

from lumen import config, paths, session
from lumen.auth.microsoft import AuthError
from lumen.mods import provision


def tmp() -> Path:
    return Path(tempfile.mkdtemp())


def test_offline_get_account_needs_no_signin_keystore_or_network():
    cfg = tmp()
    saved = (paths.offline_profiles_path, session.store, session.MicrosoftAuth)
    paths.offline_profiles_path = lambda: cfg / "offline_profiles.json"
    def bomb(*a, **k): raise AssertionError("must not be used offline")
    session.store, session.MicrosoftAuth = bomb, bomb
    try:
        a = session.get_account(config.Settings(offline_username="Bench_9"), offline=True)
        assert a.kind == "offline" and a.username == "Bench_9" and a.access_token == "0" * 32
        b = session.get_account(config.Settings(), offline=True, profile="Alt_3")
        assert b.username == "Alt_3"
        c = session.get_account(config.Settings(), offline=True)           # last used wins over settings
        assert c.username == "Alt_3"
    finally:
        paths.offline_profiles_path, session.store, session.MicrosoftAuth = saved
    data = json.loads((cfg / "offline_profiles.json").read_text())
    assert set(data["profiles"]) == {"Bench_9", "Alt_3"}


def test_online_get_account_requires_choice_when_several_saved():
    cfg = tmp()
    (cfg / "accounts.json").write_text(json.dumps({
        "11111111-1111-1111-1111-111111111111": {"username": "Alex", "owned_verified_at": 1},
        "22222222-2222-2222-2222-222222222222": {"username": "Steve", "owned_verified_at": 2}}))
    saved = paths.accounts_index_path
    paths.accounts_index_path = lambda: cfg / "accounts.json"
    try:
        for kwargs in ({}, {"account": "nobody"}):
            try:
                session.get_account(config.Settings(), offline=False, **kwargs)
                raise AssertionError(kwargs)
            except AuthError:
                pass
    finally:
        paths.accounts_index_path = saved


def test_prepare_mods_offline_copies_local_client_mod_but_never_downloads():
    mods = tmp() / "mods"
    msgs: list[str] = []
    real = provision.modrinth.make_client
    def bomb(): raise AssertionError("no Modrinth client offline")
    provision.modrinth.make_client = bomb
    try:
        provision.prepare_mods(mods, "1.20.1", True, msgs.append, offline=True)
    finally:
        provision.modrinth.make_client = real
    assert any("skipping mod downloads" in m for m in msgs)
