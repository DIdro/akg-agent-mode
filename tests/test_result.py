import json
from pathlib import Path
from core.result import ChannelResult, write_result


def test_write_result(tmp_path: Path):
    res = ChannelResult(
        channel="vk", week="2026-W29",
        period_from="2026-07-13", period_to="2026-07-19",
        metrics={"content_reach": 17600}, source="vision",
        screenshots=["vk_community.png"], status="ok",
    )
    p = write_result(res, tmp_path)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert p.name == "vk.json"
    assert data["metrics"]["content_reach"] == 17600
    assert data["needs_review"] is False
    assert data["collected_at"]  # проставлен
