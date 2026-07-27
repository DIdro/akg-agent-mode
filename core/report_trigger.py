"""Триггер генерации+отправки отчёта через native-эндпоинт (stdlib)."""
import json
import urllib.request
import urllib.parse


def trigger_report(base_url: str, key: str | None, week: str) -> tuple[bool, str]:
    """POST {week} на base_url?key=<key>. Возвращает (ok, сообщение).
    Таймаут большой — генерация PDF на сервере может занять минуту-две."""
    url = base_url + (("?" + urllib.parse.urlencode({"key": key})) if key else "")
    payload = json.dumps({"week": week}).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return (200 <= r.status < 300), f"HTTP {r.status}: {r.read().decode()[:300]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
