"""Offline profiles. Same UUID scheme as vanilla (Java's UUID.nameUUIDFromBytes)."""
from __future__ import annotations
import hashlib, re, uuid
from .models import Account

_NAME = re.compile(r"^[A-Za-z0-9_]{3,16}$")


def offline_uuid(username: str) -> str:
    b = bytearray(hashlib.md5(f"OfflinePlayer:{username}".encode()).digest())
    b[6] = (b[6] & 0x0F) | 0x30      # version 3
    b[8] = (b[8] & 0x3F) | 0x80      # IETF variant
    return str(uuid.UUID(bytes=bytes(b)))


def offline_account(username: str) -> Account:
    if not _NAME.match(username):
        raise ValueError("Username must be 3-16 chars: letters, digits, underscore")
    return Account(username=username, uuid=offline_uuid(username), kind="offline")
