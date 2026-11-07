"""CLI-level tests: offline launches are fully decoupled from Microsoft auth, keystore and network."""
import json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace

from lumen import cli, paths
from lumen.launch import process
import test_launch_service as tls


class Env:
    """Redirect every per-user path into a temp dir and trap forbidden collaborators."""
    def __init__(self):
        self.root = Path(tempfile.mkdtemp())
        self.mc = self.root / "mc"; self.mc.mkdir()
        self.cfg = self.root / "cfg"; self.cfg.mkdir()
        self.launched: list = []
        self.calls: dict = {}

    def __enter__(self):
        self.saved = {n: getattr(paths, n) for n in
                      ("minecraft_dir", "instance_dir", "config_path", "accounts_index_path",
                       "offline_profiles_path", "log_dir")}
        paths.minecraft_dir = lambda: self.mc
        def instance_dir(name):
            d = self.root / "inst" / name
            d.mkdir(parents=True, exist_ok=True)
            return d
        paths.instance_dir = instance_dir
        paths.config_path = lambda: self.cfg / "settings.json"
        paths.accounts_index_path = lambda: self.cfg / "accounts.json"
        paths.offline_profiles_path = lambda: self.cfg / "offline_profiles.json"
        paths.log_dir = lambda: self.root
        self.old_launch = process.launch
        def fake_launch(cmd, cwd, game_log):
            self.launched.append(cmd)
            return SimpleNamespace(wait=lambda: 0)
        process.launch = fake_launch
        import lumen.auth.microsoft as ms
        self.ms, self.old_ms = ms, ms.MicrosoftAuth
        def bomb(*a, **k): raise AssertionError("Microsoft auth must not run")
        ms.MicrosoftAuth = bomb
        self.old_store = cli.AccountStore
        class BombStore:
            def __init__(self, *a, **k): raise AssertionError("AccountStore/keystore must not be touched")
        cli.AccountStore = BombStore
        return self

    def __exit__(self, *a):
        for n, f in self.saved.items():
            setattr(paths, n, f)
        process.launch = self.old_launch
        self.ms.MicrosoftAuth = self.old_ms
        cli.AccountStore = self.old_store


def test_offline_launch_end_to_end_without_auth_keystore_or_network():
    with Env() as env:
        tls.seed_install(env.mc)
        sys.modules.pop("minecraft_launcher_lib", None)
        calls: dict = {}
        exe = env.root / "java"; exe.write_text("")
        with tls.patched_mll(tls.fake_mll(calls, exe=exe)):
            rc = cli.main(["launch", "--profile", "Bench_1"])
        assert rc == 0 and len(env.launched) == 1
        cmd = env.launched[0]
        assert cmd[cmd.index("--username") + 1] == "Bench_1"
        assert cmd[cmd.index("--accessToken") + 1] == "0" * 32
        assert cmd[cmd.index("--userType") + 1] == "legacy"
        assert "vanilla" not in calls and "fabric" not in calls          # nothing was installed/downloaded
        saved = json.loads((env.cfg / "offline_profiles.json").read_text())
        assert saved["last_used"] == "Bench_1" and "Bench_1" in saved["profiles"]
        assert not (env.cfg / "accounts.json").exists()


def test_bare_offline_flag_reuses_last_profile_then_settings_default():
    with Env() as env:
        tls.seed_install(env.mc)
        with tls.patched_mll(tls.fake_mll({}, exe=env.root)):
            assert cli.main(["launch", "--offline"]) == 0                 # settings default "Player"
            assert cli.main(["launch", "--profile", "Alt_2"]) == 0
            assert cli.main(["launch", "--offline"]) == 0                 # last used = Alt_2
        names = [c[c.index("--username") + 1] for c in env.launched]
        assert names == ["Player", "Alt_2", "Alt_2"]


def test_offline_launch_with_missing_files_exits_3_and_does_not_spawn():
    with Env() as env:
        tls.seed_install(env.mc)
        (env.mc / "assets" / "indexes" / "17.json").unlink()
        with tls.patched_mll(tls.fake_mll({}, exe=env.root)):
            assert cli.main(["launch", "--offline"]) == 3
        assert env.launched == []


def test_offline_launch_without_install_is_a_friendly_error():
    with Env() as env:
        with tls.patched_mll(tls.fake_mll({})):
            assert cli.main(["launch", "--offline"]) == 1
        assert env.launched == []


def test_bad_profile_name_is_friendly_error_not_traceback():
    with Env() as env:
        assert cli.main(["launch", "--profile", "bad name"]) == 1
        assert cli.main(["profile", "add", "ab"]) == 1


def test_profile_and_accounts_commands_are_keystore_free():
    with Env() as env:
        assert cli.main(["profile", "add", "Steve"]) == 0
        assert cli.main(["profile", "list"]) == 0
        assert cli.main(["profile", "remove", "Steve"]) == 0
        assert cli.main(["profile", "remove", "Steve"]) == 1


def test_online_launch_requires_explicit_account_when_several_saved():
    with Env() as env:
        cli.AccountStore = env.old_store                              # real store, JSON index only
        (env.cfg / "accounts.json").write_text(json.dumps({
            "11111111-1111-1111-1111-111111111111": {"username": "Alex", "owned_verified_at": 1},
            "22222222-2222-2222-2222-222222222222": {"username": "Steve", "owned_verified_at": 2}}))
        calls: dict = {}
        with tls.patched_mll(tls.fake_mll(calls)):
            assert cli.main(["launch"]) == 1                          # ambiguous -> error
            assert "vanilla" not in calls                             # ...before any download
            assert cli.main(["launch", "--account", "nobody"]) == 1
        assert cli.main(["logout", "--account", "steve"]) == 0
        left = json.loads((env.cfg / "accounts.json").read_text())
        assert list(left) == ["11111111-1111-1111-1111-111111111111"]


def test_set_command_pins_loader_and_rejects_garbage():
    with Env() as env:
        assert cli.main(["set", "loader_version", "0.16.5"]) == 0
        assert json.loads((env.cfg / "settings.json").read_text())["loader_version"] == "0.16.5"
        assert cli.main(["set", "loader", "quilt"]) == 1
        assert cli.main(["set", "java_path", "/x"]) == 1
