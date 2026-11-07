"""Headless interface (also the easiest thing to script and test)."""
from __future__ import annotations
import argparse, logging, os, sys
from pathlib import Path
from . import paths, config, logging_setup
from .auth.profiles import OfflineProfileStore
from .auth.store import AccountStore, NoSecureStorage

log = logging.getLogger("lumen.cli")


def _store() -> AccountStore:
    return AccountStore(paths.accounts_index_path())


def _profiles() -> OfflineProfileStore:
    return OfflineProfileStore(paths.offline_profiles_path())


def _client_id(settings: config.Settings) -> str:
    return os.environ.get("LUMEN_MS_CLIENT_ID", "") or settings.ms_client_id


# --- accounts ---------------------------------------------------------------------------------

def cmd_login(_a) -> int:
    from .auth.microsoft import MicrosoftAuth
    auth = MicrosoftAuth(_client_id(config.load(paths.config_path())))
    dc = auth.start_device_flow()
    print(f"Open {dc.verification_uri} and enter code: {dc.user_code}")
    ms_access, refresh = auth.poll_device_flow(dc)
    acct = auth.minecraft_login(ms_access)
    _store().save_microsoft(acct.uuid, acct.username, refresh)
    print(f"Signed in as {acct.username}")
    return 0


def _pick_saved_account(selector: str | None) -> str:
    """UUID of the saved Microsoft account to use (never guesses between several)."""
    store = _store()
    accounts = store.list_accounts()
    if not accounts:
        raise RuntimeError("No saved account. Run: lumen login")
    names = ", ".join(str(v.get("username", "?")) for v in accounts.values())
    if selector:
        uuid = store.find(selector)
        if uuid is None:
            raise ValueError(f"No saved account matches {selector!r} (saved: {names})")
        return uuid
    if len(accounts) > 1:
        raise ValueError(f"Several accounts are saved ({names}); choose one with --account")
    return next(iter(accounts))


def _microsoft_account(uuid: str, settings: config.Settings):
    from .auth.microsoft import MicrosoftAuth
    auth = MicrosoftAuth(_client_id(settings))
    store = _store()
    token = store.load_refresh_token(uuid)
    if not token:
        raise RuntimeError("Saved sign-in not found in the OS keystore; run: lumen login")
    ms_access, new_refresh = auth.refresh(token)
    acct = auth.minecraft_login(ms_access)
    store.save_microsoft(acct.uuid, acct.username, new_refresh)
    return acct


def cmd_logout(args) -> int:
    store = _store()
    uuid = _pick_saved_account(args.account)
    name = store.list_accounts().get(uuid, {}).get("username", uuid)
    store.remove(uuid)
    print(f"Signed out {name}")
    return 0


def cmd_accounts(_a) -> int:
    for uuid, meta in _store().list_accounts().items():          # JSON index only; no keystore access
        print(f"microsoft  {meta.get('username', '?')}  {uuid}")
    ps = _profiles()
    last = ps.last_used()
    for n in ps.names():
        print(f"offline    {n}  {ps.uuid_for(n)}{'  (last used)' if n == last else ''}")
    return 0


# --- offline profiles ---------------------------------------------------------------------------

def cmd_profile(args) -> int:
    ps = _profiles()
    if args.action == "add":
        acct = ps.add(args.name)
        print(f"{acct.username}  {acct.uuid}")
    elif args.action == "remove":
        if not ps.remove(args.name):
            print(f"No offline profile named {args.name!r}", file=sys.stderr)
            return 1
    else:
        for n in ps.names():
            print(f"{n}  {ps.uuid_for(n)}")
    return 0


# --- launch -----------------------------------------------------------------------------------

def cmd_launch(args) -> int:
    from .launch import service, process
    from .launch.localcheck import verify_local_install
    from .mods.manifest import scan_folder, detect_conflicts
    settings = config.load(paths.config_path())
    offline = bool(args.offline or args.profile)
    mc_dir = paths.minecraft_dir()
    game_dir = paths.instance_dir(f"{settings.loader}-{settings.mc_version}")

    acct = None
    saved_uuid = None
    if not offline:
        saved_uuid = _pick_saved_account(args.account)      # fail fast, before any download
    if offline:
        # Local-only: no AccountStore, no keystore, no Microsoft/Xbox calls, no downloads.
        acct = _profiles().select(args.profile, default=settings.offline_username)
        print(f"[offline] {acct.username} ({acct.uuid}); skipping all network authentication")

    version_id = service.prepare(settings.mc_version, settings.loader, mc_dir, on_status=print,
                                 offline=offline, loader_version=settings.loader_version)
    if offline:
        missing = verify_local_install(mc_dir, version_id)
        for rel in missing[:20]:
            print(f"[missing] {rel}")
        if missing:
            print(f"{len(missing)} required file(s) missing; cannot launch offline "
                  "(run one online launch first, or pre-seed the Minecraft directory).", file=sys.stderr)
            return 3

    mods = game_dir / "mods"
    mods.mkdir(exist_ok=True)
    if offline and settings.loader == "fabric":
        from .mods import provision              # local copy of the bundled client mod; no downloads
        print(provision.ensure_client_mod(mods, settings.mc_version))
    errors = [i for i in detect_conflicts(scan_folder(mods), settings.mc_version) if i.severity == "error"]
    for i in errors:
        print(f"[mod error] {i.mod_id}: {i.message}")
    if errors and not args.force:
        return 2

    if acct is None:                       # fetched late so the token is fresh after the install
        acct = _microsoft_account(saved_uuid, settings)
    cmd = service.build_command(version_id, acct, settings, mc_dir, game_dir, offline=offline, on_status=print)
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


# --- settings ---------------------------------------------------------------------------------

def cmd_settings(args) -> int:
    s = config.load(paths.config_path())
    if args.action == "export":
        config.export_settings(s, Path(args.file))
    else:
        config.save(config.import_settings(Path(args.file), s), paths.config_path())
    return 0


def cmd_set(args) -> int:
    s = config.set_value(config.load(paths.config_path()), args.key, args.value)
    config.save(s, paths.config_path())
    print(f"{args.key} = {getattr(s, args.key)}")
    return 0


# --- plumbing ---------------------------------------------------------------------------------

def _user_errors() -> tuple[type[BaseException], ...]:
    from .auth.microsoft import AuthError
    from .net.verify import ChecksumError
    return (AuthError, NoSecureStorage, ChecksumError, ValueError, RuntimeError, OSError)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lumen")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login").set_defaults(fn=cmd_login)
    lo = sub.add_parser("logout", help="forget a saved Microsoft account")
    lo.add_argument("--account", help="username or UUID (needed when several are saved)")
    lo.set_defaults(fn=cmd_logout)
    sub.add_parser("accounts", help="list saved accounts and offline profiles").set_defaults(fn=cmd_accounts)

    la = sub.add_parser("launch")
    la.add_argument("--offline", action="store_true",
                    help="local session: no Microsoft sign-in, keystore or network (uses an offline profile)")
    la.add_argument("--profile", metavar="NAME", help="offline profile to use (implies --offline)")
    la.add_argument("--account", help="saved Microsoft account (username or UUID)")
    la.add_argument("--force", action="store_true", help="launch despite mod errors")
    la.set_defaults(fn=cmd_launch)

    pr = sub.add_parser("profile", help="manage local offline profiles (offline_profiles.json)")
    pr.add_argument("action", choices=["add", "list", "remove"])
    pr.add_argument("name", nargs="?")
    pr.set_defaults(fn=cmd_profile)

    sub.add_parser("mods-check").set_defaults(fn=cmd_mods_check)
    st = sub.add_parser("settings")
    st.add_argument("action", choices=["export", "import"])
    st.add_argument("file")
    st.set_defaults(fn=cmd_settings)
    se = sub.add_parser("set", help=f"change one setting ({', '.join(sorted(config.SETTABLE))})")
    se.add_argument("key")
    se.add_argument("value", help="e.g. `set loader_version 0.16.5`; use `latest` to unpin")
    se.set_defaults(fn=cmd_set)
    return p


def main(argv: list[str] | None = None) -> int:
    logging_setup.setup(paths.log_dir())
    p = build_parser()
    args = p.parse_args(argv)
    if args.cmd == "profile" and args.action in ("add", "remove") and not args.name:
        p.error(f"profile {args.action} needs a NAME")
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130
    except _user_errors() as e:
        log.debug("command failed", exc_info=True)
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:                       # e.g. httpx.HTTPError, without importing httpx up front
        if type(e).__module__.split(".")[0] == "httpx":
            log.debug("network failure", exc_info=True)
            print(f"error: network request failed ({e})", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
