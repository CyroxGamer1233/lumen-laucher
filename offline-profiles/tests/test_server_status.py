import json
import socketserver
import threading

from lumen.server_status import parse_server_address, query_minecraft_server


def _read_varint(stream):
    value = 0
    shift = 0
    while True:
        byte = stream.recv(1)[0]
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value
        shift += 7


def _encode_varint(value):
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        result.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(result)


class StatusHandler(socketserver.BaseRequestHandler):
    def handle(self):
        handshake_length = _read_varint(self.request)
        self.request.recv(handshake_length)
        request_length = _read_varint(self.request)
        self.request.recv(request_length)

        payload = json.dumps({
            "version": {"name": "1.21.1"},
            "players": {"online": 12, "max": 80},
            "description": {"text": "Welcome ", "extra": [{"text": "to Lumen"}]},
            "favicon": "data:image/png;base64,dGVzdA==",
        }).encode()
        packet = b"\x00" + _encode_varint(len(payload)) + payload
        self.request.sendall(_encode_varint(len(packet)) + packet)


def test_status_query_reads_motd_version_players_and_ping():
    with socketserver.TCPServer(("127.0.0.1", 0), StatusHandler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = query_minecraft_server("127.0.0.1", server.server_address[1])
        finally:
            server.shutdown()
            thread.join(timeout=2)

    assert result["online"] is True
    assert result["version"] == "1.21.1"
    assert result["players_online"] == 12
    assert result["players_max"] == 80
    assert result["motd"] == "Welcome to Lumen"
    assert result["favicon"] == "data:image/png;base64,dGVzdA=="
    assert result["latency_ms"] >= 0


def test_server_address_parser_handles_ports_and_bracketed_ipv6():
    assert parse_server_address("example.test") == ("example.test", 25565)
    assert parse_server_address("example.test:25570") == ("example.test", 25570)
    assert parse_server_address("[::1]:25570") == ("::1", 25570)
