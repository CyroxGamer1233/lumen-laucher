"""Offline identities. Same UUID scheme as vanilla (Java's UUID.nameUUIDFromBytes).

Vanilla computes MD5("OfflinePlayer:<name>") and stamps the version-3 / IETF-variant bits.
There is NO namespace prefix. (``uuid.uuid3(ns, name)`` hashes ``ns.bytes + name`` and therefore
yields a *different* UUID from the one vanilla clients and offline-mode servers derive, which breaks
player-data continuity on any world or server that was ever opened offline.)
"""
from __future__ import annotations
import hashlib, re, uuid
from .models import Account

_NAME = re.compile(r"^[A-Za-z0-9_]{3,16}$")

# Static placeholder for --accessToken in offline sessions. Not a secret, never sent anywhere.
OFFLINE_TOKEN = "0" * 32


def offline_uuid(username: str) -> str:
    """Deterministic UUID for ANY string (validation of the name is a separate concern)."""
    b = bytearray(hashlib.md5(f"OfflinePlayer:{username}".encode("utf-8")).digest())
    b[6] = (b[6] & 0x0F) | 0x30      # version 3
    b[8] = (b[8] & 0x3F) | 0x80      # IETF variant
    return str(uuid.UUID(bytes=bytes(b)))


def valid_username(username: str) -> bool:
    return bool(_NAME.match(username))


def offline_account(username: str) -> Account:
    if not valid_username(username):
        raise ValueError("Username must be 3-16 chars: letters, digits, underscore")
    return Account(username=username, uuid=offline_uuid(username), kind="offline",
                   access_token=OFFLINE_TOKEN)
