"""Sign-in and account selection shared by the CLI and the GUI."""
from __future__ import annotations

import os
from collections.abc import Callable

from . import paths
from .auth.microsoft import AuthError, MicrosoftAuth
from .auth.models import Account
from .auth.profiles import OfflineProfileStore
from .auth.store import AccountStore


def client_id(settings) -> str:
    return os.environ.get("LUMEN_MS_CLIENT_ID", "").strip() or getattr(settings, "ms_client_id", "").strip()


def store() -> AccountStore:
    return AccountStore(paths.accounts_index_path())


def offline_profiles() -> OfflineProfileStore:
    """Local-only identities (offline_profiles.json); never touches accounts.json or the keystore."""
    return OfflineProfileStore(paths.offline_profiles_path())


def sign_in(settings, on_code: Callable[[str, str], None]) -> Account:
    """Device-code sign-in. `on_code(user_code, url)` tells the user what to type where."""
    auth = MicrosoftAuth(client_id(settings))
    dc = auth.start_device_flow()
    on_code(dc.user_code, dc.verification_uri)
    ms_access, refresh = auth.poll_device_flow(dc)
    acct = auth.minecraft_login(ms_access)
    store().save_microsoft(acct.uuid, acct.username, refresh)
    return acct


def get_offline_account(settings, profile: str | None = None) -> Account:
    """Local session: explicit profile > last used > settings.offline_username.

    Pure local file access. No Microsoft/Xbox calls, no OS keystore, no network.
    """
    return offline_profiles().select(profile, default=settings.offline_username)


def get_account(settings, offline: bool, profile: str | None = None, account: str | None = None) -> Account:
    if offline:
        return get_offline_account(settings, profile)
    st = store()
    accounts = st.list_accounts()
    if not accounts:
        raise AuthError("Please sign in with Microsoft first.")
    if account:
        uuid = st.find(account)
        if uuid is None:
            raise AuthError(f"No saved account matches {account!r}.")
    elif len(accounts) == 1:
        uuid = next(iter(accounts))
    else:
        names = ", ".join(str(v.get("username", "?")) for v in accounts.values())
        raise AuthError(f"Several accounts are saved ({names}); choose one.")
    token = st.load_refresh_token(uuid)
    if not token:
        raise AuthError("Saved sign-in is missing; please sign in again.")
    auth = MicrosoftAuth(client_id(settings))
    ms_access, new_refresh = auth.refresh(token)
    acct = auth.minecraft_login(ms_access)
    st.save_microsoft(acct.uuid, acct.username, new_refresh)
    return acct
