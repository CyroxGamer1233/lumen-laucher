from __future__ import annotations

import json
import socket
import struct
import time


def parse_server_address(address: str) -> tuple[str, int]:
    address = address.strip()
    if address.startswith("["):
        closing = address.find("]")
        if closing < 0:
            raise ValueError("IPv6 addresses must use [address]:port format")
        host = address[1:closing]
        suffix = address[closing + 1:]
        if suffix and not suffix.startswith(":"):
            raise ValueError("Invalid text after IPv6 address")
        port_text = suffix[1:] if suffix else ""
    else:
        host, separator, port_text = address.partition(":")
        if separator and ":" in port_text:
            raise ValueError("IPv6 addresses must use [address]:port format")
    port = int(port_text) if port_text else 25565
    if not host or not 1 <= port <= 65535:
        raise ValueError("Enter a server address with a port from 1 to 65535")
    return host, port


def _encode_varint(value: int) -> bytes:
    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            encoded.append(byte | 0x80)
        else:
            encoded.append(byte)
            return bytes(encoded)


def _read_varint(stream: socket.socket) -> int:
    value = 0
    for index in range(5):
        byte = stream.recv(1)
        if not byte:
            raise RuntimeError("Server closed the connection during status response")
        value |= (byte[0] & 0x7F) << (7 * index)
        if not byte[0] & 0x80:
            return value
    raise RuntimeError("Server sent an invalid status packet length")


def _read_exact(stream: socket.socket, length: int) -> bytes:
    result = bytearray()
    while len(result) < length:
        chunk = stream.recv(length - len(result))
        if not chunk:
            raise RuntimeError("Server closed the connection during status response")
        result.extend(chunk)
    return bytes(result)


def _description_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_description_text(part) for part in value)
    if isinstance(value, dict):
        text = str(value.get("text", ""))
        return text + _description_text(value.get("extra", []))
    return ""


def query_minecraft_server(host: str, port: int = 25565, timeout: float = 4) -> dict:
    if not host or len(host) > 255 or any(char.isspace() for char in host):
        raise ValueError("Enter a valid Minecraft server address")
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")

    encoded_host = host.encode("utf-8")
    handshake = (
        b"\x00"
        + _encode_varint(767)
        + _encode_varint(len(encoded_host))
        + encoded_host
        + struct.pack(">H", port)
        + b"\x01"
    )
    packet = _encode_varint(len(handshake)) + handshake
    started = time.perf_counter()
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.settimeout(timeout)
        connection.sendall(packet)
        connection.sendall(b"\x01\x00")
        packet_length = _read_varint(connection)
        if packet_length < 1 or packet_length > 1_048_576:
            raise RuntimeError("Server returned an invalid status response")
        packet_data = _read_exact(connection, packet_length)

    packet_id, offset = _decode_varint_with_offset(packet_data, 0)
    string_length, offset = _decode_varint_with_offset(packet_data, offset)
    if packet_id != 0 or string_length != len(packet_data) - offset:
        raise RuntimeError("Server returned an invalid status response")
    try:
        status = json.loads(packet_data[offset:offset + string_length].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Server returned malformed status data") from error

    if not isinstance(status, dict):
        raise RuntimeError("Server returned an invalid status response")
    version = status.get("version") or {}
    players = status.get("players") or {}
    if not isinstance(version, dict) or not isinstance(players, dict):
        raise RuntimeError("Server returned an invalid status response")
    try:
        players_online = int(players.get("online") or 0)
        players_max = int(players.get("max") or 0)
    except (TypeError, ValueError) as error:
        raise RuntimeError("Server returned invalid player counts") from error
    favicon = status.get("favicon")
    if not isinstance(favicon, str) or not favicon.startswith("data:image/png;base64,") or len(favicon) > 100_000:
        favicon = None
    return {
        "online": True,
        "version": str(version.get("name") or "Unknown"),
        "motd": _description_text(status.get("description")).strip(),
        "players_online": players_online,
        "players_max": players_max,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "favicon": favicon,
    }


def _decode_varint_with_offset(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for index in range(5):
        if offset + index >= len(data):
            raise RuntimeError("Server returned an incomplete status packet")
        byte = data[offset + index]
        value |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return value, offset + index + 1
    raise RuntimeError("Server returned an invalid status packet")
