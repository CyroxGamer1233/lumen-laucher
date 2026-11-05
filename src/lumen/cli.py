"""Headless interface (also the easiest thing to script and test)."""
from __future__ import annotations
import argparse, os, sys
from pathlib import Path
from . import paths, config, logging_setup
from .auth.offline import offline_account
from .auth.store import AccountStore


def _store() -> AccountStore:
    return AccountStore(paths.accounts_index_path())


def cmd_login(_a) -> int:
    from .auth.microsoft import MicrosoftAuth
    auth = MicrosoftAuth(os.environ.get("LUMEN_MS_CLIENT_ID", ""))
    dc = auth.start_device_flow()
    print(f"Open {dc.verification_uri} and enter code: {dc.user_code}")
    ms_access, refresh = auth.poll_device_flow(dc)
    acct = auth.minecraft_login(ms_access)
    _store().save_microsoft(acct.uuid, acct.username, refresh)
    print(f"Signed in as {acct.username}")
    return 0


def _account(args, settings):
    if args.offline:
        if not _store().has_verified_ownership():
            sys.exit("Offline mode unlocks after one successful Microsoft sign-in on this device (run: lumen login).")
        return offline_account(settings.offline_username)
    from .auth.microsoft import MicrosoftAuth
    auth = MicrosoftAuth(os.environ.get("LUMEN_MS_CLIENT_ID", ""))
    accounts = _store().list_accounts()
    if not accounts:
        sys.exit("No saved account. Run: lumen login")
    uuid = next(iter(accounts))
    ms_access, new_refresh = auth.refresh(_store().load_refresh_token(uuid) or "")
    acct = auth.minecraft_login(ms_access)
    _store().save_microsoft(acct.uuid, acct.username, new_refresh)
    return acct


def cmd_launch(args) -> int:
    from .launch import service, process
    from .mods.manifest import scan_folder, detect_conflicts
    settings = config.load(paths.config_path())
    mc_dir = paths.minecraft_dir()
    game_dir = paths.instance_dir(f"{settings.loader}-{settings.mc_version}")
    version_id = service.prepare(settings.mc_version, settings.loader, mc_dir, on_status=print)
    mods = game_dir / "mods"
    mods.mkdir(exist_ok=True)
    errors = [i for i in detect_conflicts(scan_folder(mods), settings.mc_version) if i.severity == "error"]
    for i in errors:
        print(f"[mod error] {i.mod_id}: {i.message}")
    if errors and not args.force:
        return 2
    acct = _account(args, settings)
    cmd = service.build_command(version_id, acct, settings, mc_dir, game_dir)
    proc = process.launch(cmd, game_dir, paths.log_dir() / "game.log")
    return proc.wait()


def cmd_mods_check(_a) -> int:
    from .mods.manifest import scan_folder, detect_conflicts
    s = config.load(paths.config_path())
    d = paths.instance_dir(f"{s.loader}-{s.mc_version}") / "mods"
    d.mkdir(exist_ok=True)
    issues = detect_conflicts(scan_folder(d), s.mc_version)
    for i in issues:
        print(f"[{i.severity}] {i.mod_id}: {i.message}")
    return 1 if any(i.severity == "error" for i in issues) else 0


def cmd_settings(args) -> int:
    s = config.load(paths.config_path())
    if args.action == "export":
        config.export_settings(s, Path(args.file))
    else:
        config.save(config.import_settings(Path(args.file), s), paths.config_path())
    return 0


def main(argv: list[str] | None = None) -> int:
    logging_setup.setup(paths.log_dir())
    p = argparse.ArgumentParser(prog="lumen")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login").set_defaults(fn=cmd_login)
    la = sub.add_parser("launch")
    la.add_argument("--offline", action="store_true")
    la.add_argument("--force", action="store_true", help="launch despite mod errors")
    la.set_defaults(fn=cmd_launch)
    sub.add_parser("mods-check").set_defaults(fn=cmd_mods_check)
    st = sub.add_parser("settings")
    st.add_argument("action", choices=["export", "import"])
    st.add_argument("file")
    st.set_defaults(fn=cmd_settings)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
