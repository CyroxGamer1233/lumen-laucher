"""Sign-in and account selection shared by the CLI and the GUI."""
from __future__ import annotations

import os
from collections.abc import Callable

from . import paths
from .auth.microsoft import AuthError, MicrosoftAuth
from .auth.models import Account
from .auth.offline import offline_account
from .auth.store import AccountStore


def client_id(settings) -> str:
    return os.environ.get("LUMEN_MS_CLIENT_ID") or settings.ms_client_id


def store() -> AccountStore:
    return AccountStore(paths.accounts_index_path())


def sign_in(settings, on_code: Callable[[str, str], None]) -> Account:
    """Device-code sign-in. `on_code(user_code, url)` tells the user what to type where."""
    auth = MicrosoftAuth(client_id(settings))
    dc = auth.start_device_flow()
    on_code(dc.user_code, dc.verification_uri)
    ms_access, refresh = auth.poll_device_flow(dc)
    acct = auth.minecraft_login(ms_access)
    store().save_microsoft(acct.uuid, acct.username, refresh)
    return acct


def get_account(settings, offline: bool) -> Account:
    st = store()
    if offline:
        if not st.has_verified_ownership():
            raise AuthError("Offline mode unlocks after one successful Microsoft sign-in on this device.")
        return offline_account(settings.offline_username)
    accounts = st.list_accounts()
    if not accounts:
        raise AuthError("Please sign in with Microsoft first.")
    uuid = next(iter(accounts))
    token = st.load_refresh_token(uuid)
    if not token:
        raise AuthError("Saved sign-in is missing; please sign in again.")
    auth = MicrosoftAuth(client_id(settings))
    ms_access, new_refresh = auth.refresh(token)
    acct = auth.minecraft_login(ms_access)
    st.save_microsoft(acct.uuid, acct.username, new_refresh)
    return acct
