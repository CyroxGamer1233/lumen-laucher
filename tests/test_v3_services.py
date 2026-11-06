import base64
import json

from lumen import servers, skins


def test_server_chat_text():
    assert servers._chat_text({"text": "A", "extra": [{"text": "B"}]}) == "AB"


def test_server_status_defaults():
    status = servers.ServerStatus("localhost")
    assert not status.online and status.port == 25565


def test_skin_texture_payload():
    value = base64.b64encode(json.dumps({
        "textures": {
            "SKIN": {"url": "https://textures.minecraft.net/skin/demo",
                     "metadata": {"model": "slim"}},
        }
    }).encode()).decode()
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"id": "abc", "name": "Player", "properties": [{"name": "textures", "value": value}]}
    class Client:
        def get(self, url): return Response()
    result = skins.lookup("abc", Client())
    assert result.name == "Player"
    assert result.skin_url.endswith("/demo")
    assert result.model == "slim"

