"""Minecraft Java status ping without an external server-status dependency."""
from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass


@dataclass
class ServerStatus:
    host: str
    port: int = 25565
    online: bool = False
    latency_ms: int | None = None
    version: str = ""
    motd: str = ""
    players_online: int = 0
    players_max: int = 0
    favicon: str | None = None
    error: str | None = None


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        part = value & 0x7F
        value >>= 7
        out.append(part | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _read_varint(sock: socket.socket) -> int:
    value = shift = 0
    while shift < 35:
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError("server closed connection")
        value |= (byte[0] & 0x7F) << shift
        if not byte[0] & 0x80:
            return value
        shift += 7
    raise ValueError("invalid VarInt")


def _read(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("server closed connection")
        data.extend(chunk)
    return bytes(data)


def query(host: str, port: int = 25565, timeout: float = 4.0) -> ServerStatus:
    result = ServerStatus(host, port)
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            address = host.encode("utf-8")
            handshake = _varint(0) + _varint(767) + _varint(len(address)) + address
            handshake += port.to_bytes(2, "big") + _varint(1)
            sock.sendall(_varint(len(handshake) + 1) + _varint(0) + handshake)
            sock.sendall(_varint(1) + _varint(0))
            packet_length = _read_varint(sock)
            packet = _read(sock, packet_length)
            index = 0
            while packet[index] & 0x80:
                index += 1
            index += 1
            text_length = packet[index]
            index += 1
            if text_length & 0x80:
                # Status JSON is normally under 128 bytes only for tiny servers;
                # use a proper VarInt parser for all responses.
                shift = 7
                text_length &= 0x7F
                while packet[index - 1] & 0x80:
                    text_length |= (packet[index] & 0x7F) << shift
                    shift += 7
                    index += 1
            payload = json.loads(packet[index:index + text_length].decode("utf-8"))
        result.online = True
        result.latency_ms = round((time.monotonic() - started) * 1000)
        version = payload.get("version") or {}
        players = payload.get("players") or {}
        description = payload.get("description", "")
        result.version = version.get("name", "")
        result.motd = description if isinstance(description, str) else _chat_text(description)
        result.players_online = int(players.get("online", 0))
        result.players_max = int(players.get("max", 0))
        result.favicon = payload.get("favicon")
    except Exception as exc:
        result.error = str(exc)
    return result


def _chat_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("text", "")) + "".join(_chat_text(x) for x in value.get("extra", []))
    return ""

