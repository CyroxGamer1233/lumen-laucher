"""Microsoft -> Xbox Live -> XSTS -> Minecraft Services (device-code flow).

You must register your own Azure AD app ("public client", personal accounts,
allow public client flows) and request Minecraft Services access from Mojang.
No client secret is shipped in the launcher.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from .. import USER_AGENT
from .models import Account

TENANT = "consumers"
SCOPE = "XboxLive.signin offline_access"
LOGIN = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0"
XBL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE = "https://api.minecraftservices.com/minecraft/profile"

XSTS_ERRORS = {
    2148916233: "This Microsoft account has no Xbox profile. Create one at xbox.com.",
    2148916235: "Xbox Live is not available in your country/region.",
    2148916238: "Child account: add it to a Microsoft Family before signing in.",
}


class AuthError(Exception):
    pass


class GameNotOwned(AuthError):
    pass


@dataclass
class DeviceCode:
    user_code: str
    verification_uri: str
    device_code: str
    interval: int
    expires_in: int


class MicrosoftAuth:
    def __init__(self, client_id: str, http=None):
        if not client_id:
            raise AuthError("Missing Azure client id (set LUMEN_MS_CLIENT_ID).")
        import httpx
        self.client_id = client_id
        self.http = http or httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT})

    def start_device_flow(self) -> DeviceCode:
        r = self.http.post(f"{LOGIN}/devicecode", data={"client_id": self.client_id, "scope": SCOPE})
        if r.status_code != 200:
            raise AuthError(f"Device-code request failed ({r.status_code})")
        j = r.json()
        return DeviceCode(j["user_code"], j["verification_uri"], j["device_code"],
                          int(j.get("interval", 5)), int(j.get("expires_in", 900)))

    def poll_device_flow(self, dc: DeviceCode, sleep=time.sleep) -> tuple[str, str]:
        deadline = time.monotonic() + dc.expires_in
        interval = dc.interval
        while time.monotonic() < deadline:
            sleep(interval)
            r = self.http.post(f"{LOGIN}/token", data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": self.client_id, "device_code": dc.device_code})
            j = r.json()
            if r.status_code == 200:
                return j["access_token"], j["refresh_token"]
            err = j.get("error")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval += 5
                continue
            raise AuthError(f"Sign-in failed: {err or r.status_code}")
        raise AuthError("Sign-in code expired; try again.")

    def refresh(self, refresh_token: str) -> tuple[str, str]:
        r = self.http.post(f"{LOGIN}/token", data={
            "grant_type": "refresh_token", "client_id": self.client_id,
            "refresh_token": refresh_token, "scope": SCOPE})
        if r.status_code != 200:
            raise AuthError("Saved sign-in expired; please sign in again.")
        j = r.json()
        return j["access_token"], j.get("refresh_token", refresh_token)

    def minecraft_login(self, ms_access_token: str) -> Account:
        r = self.http.post(XBL, json={
            "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com",
                           "RpsTicket": f"d={ms_access_token}"},
            "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"})
        r.raise_for_status()
        xbl = r.json()
        uhs = xbl["DisplayClaims"]["xui"][0]["uhs"]

        r = self.http.post(XSTS, json={
            "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl["Token"]]},
            "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"})
        if r.status_code == 401:
            code = r.json().get("XErr")
            raise AuthError(XSTS_ERRORS.get(code, f"Xbox authorization refused (XErr {code})"))
        r.raise_for_status()
        xsts = r.json()["Token"]

        r = self.http.post(MC_LOGIN, json={"identityToken": f"XBL3.0 x={uhs};{xsts}"})
        r.raise_for_status()
        mc_token = r.json()["access_token"]

        r = self.http.get(MC_PROFILE, headers={"Authorization": f"Bearer {mc_token}"})
        if r.status_code == 404:
            raise GameNotOwned("This account does not own Minecraft: Java Edition.")
        r.raise_for_status()
        p = r.json()
        return Account(username=p["name"], uuid=p["id"], kind="microsoft", access_token=mc_token)
