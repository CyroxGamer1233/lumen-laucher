from pathlib import Path

from lumen.updater import updater


def test_unconfigured_updater_fails_clearly():
    assert not updater.is_configured()
    class NeverCalled:
        def get(self, *_a, **_k): raise AssertionError("must not hit the network")
    try:
        updater.check(NeverCalled(), "0.1.0", "win")
        raise AssertionError
    except updater.UpdaterNotConfigured as e:
        assert "not configured" in str(e)
    assert updater.is_configured("https://updates.example.com/latest.json", "A" * 43 + "=")


def test_download_name_ignores_query_string():
    seen = {}
    orig = updater.download_verified
    updater.download_verified = lambda c, url, dest, sha, algo: seen.setdefault("dest", dest)
    try:
        u = updater.Update("1.0.0", "https://x.org/dl/lumen-1.0.0.exe?sig=abc#frag", "ab" * 32, "")
        updater.download(None, u, Path("/tmp/stage"))
    finally:
        updater.download_verified = orig
    assert seen["dest"].name == "lumen-1.0.0.exe"
