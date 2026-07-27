import json
from core import webhook


def test_post_rows_sends_payload(monkeypatch):
    captured = {}

    class FakeResp:
        status = 200
        def read(self): return b'{"ok":true}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode())
        return FakeResp()

    monkeypatch.setattr(webhook.urllib.request, "urlopen", fake_urlopen)
    ok, msg = webhook.post_rows("https://x/native/webhook/agent-metrics", "SEC",
                                "2026-W29", [{"channel": "Корп. блог Дзен", "reach": 87}])
    assert ok is True
    assert "key=SEC" in captured["url"]
    assert captured["body"]["week"] == "2026-W29"
    assert captured["body"]["rows"][0]["reach"] == 87


def test_post_rows_handles_error(monkeypatch):
    def boom(req, timeout=0): raise OSError("network down")
    monkeypatch.setattr(webhook.urllib.request, "urlopen", boom)
    ok, msg = webhook.post_rows("https://x", "k", "2026-W29", [])
    assert ok is False
    assert "network down" in msg
