"""POST строк реестра на native-эндпоинт агента (stdlib, без зависимостей)."""
import json
import urllib.request
import urllib.parse


def post_rows(url: str, key: str | None, week: str, rows: list[dict]) -> tuple[bool, str]:
    """POST {week, rows, source} на url?key=<key>. Возвращает (ok, сообщение)."""
    full = url + (("?" + urllib.parse.urlencode({"key": key})) if key else "")
    payload = json.dumps({"week": week, "rows": rows, "source": "agent-mode"}).encode()
    req = urllib.request.Request(full, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode()[:200]
            return (200 <= r.status < 300), f"HTTP {r.status}: {body}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
