"""launch.service / localcheck with a fake minecraft_launcher_lib (no network, no Minecraft files)."""
import json, sys, tempfile, types
from pathlib import Path
from types import SimpleNamespace

from lumen import config
from lumen.auth.offline import OFFLINE_TOKEN, offline_account
from lumen.auth.models import Account
from lumen.launch import service
from lumen.launch.localcheck import installed_version_id, verify_local_install


def tmp() -> Path:
    return Path(tempfile.mkdtemp())


def seed_install(mc: Path, mc_version="1.21.1", loader_versions=("0.16.5",)) -> None:
    """Minimal on-disk Fabric install."""
    (mc / "versions" / mc_version).mkdir(parents=True)
    (mc / "versions" / mc_version / f"{mc_version}.jar").write_bytes(b"jar")
    (mc / "versions" / mc_version / f"{mc_version}.json").write_text(json.dumps({
        "id": mc_version, "assetIndex": {"id": "17"},
        "libraries": [{"name": "a:b:1", "downloads": {"artifact": {"path": "a/b/1/b-1.jar"}}},
                      {"name": "os:only:1", "rules": [{"action": "allow", "os": {"name": "osx"}}]}]}))
    (mc / "assets" / "indexes").mkdir(parents=True)
    (mc / "assets" / "indexes" / "17.json").write_text("{}")
    (mc / "libraries" / "a" / "b" / "1").mkdir(parents=True)
    (mc / "libraries" / "a" / "b" / "1" / "b-1.jar").write_bytes(b"x")
    for lv in loader_versions:
        vid = f"fabric-loader-{lv}-{mc_version}"
        (mc / "versions" / vid).mkdir(parents=True)
        (mc / "versions" / vid / f"{vid}.json").write_text(json.dumps({
            "id": vid, "inheritsFrom": mc_version,
            "libraries": [{"name": "net.fabricmc:fabric-loader:" + lv}]}))
        lib = mc / "libraries" / "net" / "fabricmc" / "fabric-loader" / lv
        lib.mkdir(parents=True, exist_ok=True)
        (lib / f"fabric-loader-{lv}.jar").write_bytes(b"x")


def fake_mll(calls: dict, exe: Path | None = None, runtime_info=True):
    m = types.ModuleType("minecraft_launcher_lib")
    info = {"name": "java-runtime-delta", "javaMajorVersion": 21} if runtime_info else None
    m.utils = SimpleNamespace(get_version_runtime_information=lambda vid, d: info)

    def install_rt(name, d):
        calls.setdefault("runtime_installed", []).append(name)

    m.runtime = SimpleNamespace(install_jvm_runtime=install_rt,
                                get_executable_path=lambda n, d: str(exe) if exe else None)

    def get_cmd(vid, d, opts):
        calls["options"] = opts
        return [opts.get("executablePath", "java"), *opts["jvmArguments"], "Main", "--username", opts["username"],
                "--uuid", opts["uuid"], "--accessToken", opts["token"], "--userType", "msa"]

    m.command = SimpleNamespace(get_minecraft_command=get_cmd)
    m.install = SimpleNamespace(install_minecraft_version=lambda v, d, callback=None: calls.setdefault("vanilla", []).append(v))
    m.fabric = SimpleNamespace(
        is_minecraft_version_supported=lambda v: True,
        get_latest_loader_version=lambda: "0.99.0",
        install_fabric=lambda v, d, loader_version=None, callback=None: calls.setdefault("fabric", []).append(loader_version))
    return m


class patched_mll:
    def __init__(self, mod): self.mod = mod
    def __enter__(self):
        self.old = sys.modules.get("minecraft_launcher_lib")
        sys.modules["minecraft_launcher_lib"] = self.mod
    def __exit__(self, *a):
        if self.old is None:
            sys.modules.pop("minecraft_launcher_lib", None)
        else:
            sys.modules["minecraft_launcher_lib"] = self.old


def test_installed_version_picks_newest_or_pinned_loader():
    mc = tmp()
    seed_install(mc, loader_versions=("0.15.11", "0.16.5", "0.9.0"))
    assert installed_version_id(mc, "1.21.1", "fabric") == "fabric-loader-0.16.5-1.21.1"
    assert installed_version_id(mc, "1.21.1", "fabric", "0.15.11") == "fabric-loader-0.15.11-1.21.1"
    assert installed_version_id(mc, "1.21.1", "fabric", "0.1.0") is None
    assert installed_version_id(mc, "1.21.1", "vanilla") == "1.21.1"
    assert installed_version_id(mc, "1.20.4", "fabric") is None
    assert installed_version_id(mc, "1.21.1", "forge") is None


def test_verify_local_install_reports_missing_files():
    mc = tmp()
    seed_install(mc)
    assert verify_local_install(mc, "fabric-loader-0.16.5-1.21.1") == []
    (mc / "assets" / "indexes" / "17.json").unlink()
    (mc / "libraries" / "a" / "b" / "1" / "b-1.jar").unlink()
    missing = verify_local_install(mc, "fabric-loader-0.16.5-1.21.1")
    assert "assets/indexes/17.json" in missing and "libraries/a/b/1/b-1.jar" in missing
    assert verify_local_install(mc, "nope") == ["versions/nope/nope.json"]


def test_prepare_offline_never_imports_or_calls_mll():
    mc = tmp()
    seed_install(mc)
    sys.modules.pop("minecraft_launcher_lib", None)
    calls: dict = {}
    # If prepare(offline=True) touched mll it would raise ImportError (module absent) or record calls.
    vid = service.prepare("1.21.1", "fabric", mc, offline=True)
    assert vid == "fabric-loader-0.16.5-1.21.1" and not calls
    try:
        service.prepare("1.20.4", "fabric", tmp(), offline=True)
        raise AssertionError
    except RuntimeError as e:
        assert "not installed" in str(e)


def test_prepare_online_uses_pinned_loader_else_latest():
    mc = tmp()
    calls: dict = {}
    with patched_mll(fake_mll(calls)):
        assert service.prepare("1.21.1", "fabric", mc, loader_version="0.16.5") == "fabric-loader-0.16.5-1.21.1"
        assert service.prepare("1.21.1", "fabric", mc) == "fabric-loader-0.99.0-1.21.1"
    assert calls["fabric"] == ["0.16.5", "0.99.0"]


def test_offline_options_dictionary_and_user_type():
    mc, game = tmp(), tmp()
    calls: dict = {}
    acct = offline_account("Bench_1")
    exe = game / "java"; exe.write_text("")
    with patched_mll(fake_mll(calls, exe=exe)):
        cmd = service.build_command("v", acct, config.Settings(), mc, game, offline=True)
    o = calls["options"]
    assert o["username"] == "Bench_1" and o["uuid"] == acct.uuid
    assert o["token"] == OFFLINE_TOKEN == "0" * 32
    assert o["meta"] == {"name": "Bench_1", "type": "legacy"}
    assert o["executablePath"] == str(exe)
    assert cmd[cmd.index("--userType") + 1] == "legacy"
    assert "runtime_installed" not in calls                          # offline never installs a runtime


def test_microsoft_options_keep_real_token_and_msa():
    calls: dict = {}
    acct = Account("Alex", "u-1", "microsoft", access_token="real-token")
    with patched_mll(fake_mll(calls)):
        cmd = service.build_command("v", acct, config.Settings(java_path="/opt/j/bin/java"), tmp(), tmp(), offline=False)
    assert calls["options"]["token"] == "real-token" and "meta" not in calls["options"]
    assert calls["options"]["executablePath"] == "/opt/j/bin/java"
    assert cmd[cmd.index("--userType") + 1] == "msa"


def test_runtime_installed_online_but_not_offline_and_errors_are_not_swallowed():
    calls: dict = {}
    exe = tmp() / "java"; exe.write_text("")
    holder = {"path": None}
    m = fake_mll(calls)
    m.runtime.get_executable_path = lambda n, d: holder["path"]
    def install(name, d):
        calls.setdefault("runtime_installed", []).append(name); holder["path"] = str(exe)
    m.runtime.install_jvm_runtime = install
    with patched_mll(m):
        major, got = service.resolve_java("v", config.Settings(), tmp(), offline=False)
    assert major == 21 and got == str(exe) and calls["runtime_installed"] == ["java-runtime-delta"]

    m2 = fake_mll({})
    real_which = service.shutil.which
    service.shutil.which = lambda _n: None
    try:
        with patched_mll(m2):
            try:
                service.resolve_java("v", config.Settings(), tmp(), offline=True)
                raise AssertionError("expected RuntimeError")
            except RuntimeError as e:
                assert "not installed" in str(e)
    finally:
        service.shutil.which = real_which


def test_settings_loader_pin_validation_and_set_value():
    s = config.Settings()
    assert config.set_value(s, "loader_version", "0.16.5").loader_version == "0.16.5"
    assert config.set_value(config.set_value(s, "loader_version", "0.16.5"), "loader_version", "latest").loader_version is None
    assert config.set_value(s, "ram_mb", "auto").ram_mb is None
    assert config.set_value(s, "ram_mb", "500").ram_mb == 1024                    # clamped, not rejected
    for key, bad in (("loader", "quilt"), ("jvm_profile", "x"), ("loader_version", "../x"), ("mc_version", "a b"), ("java_path", "/x")):
        try:
            config.set_value(s, key, bad)
            raise AssertionError((key, bad))
        except ValueError:
            pass
