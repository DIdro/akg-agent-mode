import json
from core import report_trigger


def test_trigger_report_posts_week(monkeypatch):
    cap = {}

    class R:
        status = 200
        def read(self): return b'{"ok":true,"generated":true,"sent":true}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=0):
        cap["url"] = req.full_url
        cap["body"] = json.loads(req.data.decode())
        return R()

    monkeypatch.setattr(report_trigger.urllib.request, "urlopen", fake)
    ok, msg = report_trigger.trigger_report(
        "https://x/native/webhook/generate-report", "K", "2026-W29")
    assert ok is True
    assert "key=K" in cap["url"]
    assert cap["body"]["week"] == "2026-W29"


def test_trigger_report_error(monkeypatch):
    def boom(req, timeout=0): raise OSError("down")
    monkeypatch.setattr(report_trigger.urllib.request, "urlopen", boom)
    ok, msg = report_trigger.trigger_report("https://x", "K", "2026-W29")
    assert ok is False
    assert "down" in msg
