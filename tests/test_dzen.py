import io
import zipfile

from core.xlsx import parse_xlsx
from channels.dzen import _aggregate_posts, COLS

_CT = """<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
</Types>"""

# Колонки: A=0 B=1 C=2(title) D=3 E=4(reads) F=5(shows) G=6(opens) H=7(time_min)
# I=8(comments) J=9(subs) K=10(likes) — совпадает с COLS в channels/dzen.py.
# row 1: заголовок отчёта, row 2: шапка колонок, row 3: строка "Всего",
# rows 4-5: два поста (аггрегация читает rows[3:], т.е. индексы 2..4 списка).
_SHEET = """<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="str"><v>Отчёт по публикациям</v></c></row>
<row r="2"><c r="A2" t="str"><v>Дата</v></c><c r="C2" t="str"><v>Заголовок</v></c></row>
<row r="3"><c r="A3" t="str"><v>Всего</v></c></row>
<row r="4">
<c r="C4" t="str"><v>Пост 1</v></c>
<c r="E4"><v>10</v></c>
<c r="F4"><v>100</v></c>
<c r="G4"><v>20</v></c>
<c r="H4"><v>1.5</v></c>
<c r="I4"><v>2</v></c>
<c r="J4"><v>1</v></c>
<c r="K4"><v>5</v></c>
</row>
<row r="5">
<c r="C5" t="str"><v>Пост 2</v></c>
<c r="E5"><v>20</v></c>
<c r="F5"><v>200</v></c>
<c r="G5"><v>40</v></c>
<c r="H5"><v>3</v></c>
<c r="I5"><v>4</v></c>
<c r="J5"><v>2</v></c>
<c r="K5"><v>8</v></c>
</row>
</sheetData></worksheet>"""


def _fake_dzen_xlsx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("xl/worksheets/sheet1.xml", _SHEET)
    return buf.getvalue()


def test_aggregate_posts_sums_across_two_posts():
    rows = parse_xlsx(_fake_dzen_xlsx())
    posts = _aggregate_posts(rows, "article")

    assert len(posts) == 2
    assert posts[0]["title"] == "Пост 1"
    assert posts[1]["title"] == "Пост 2"
    assert all(p["type"] == "article" for p in posts)

    totals = {k: 0 for k in COLS}
    for post in posts:
        for k in totals:
            totals[k] += post[k]

    assert totals["reads"] == 30
    assert totals["shows"] == 300
    assert totals["opens"] == 60
    # 1.5 -> int(1.5)=1, 3 -> int(3.0)=3
    assert totals["time_min"] == 4
    assert totals["comments"] == 6
    assert totals["subs"] == 3
    assert totals["likes"] == 13


def test_aggregate_posts_coerces_fractional_time_min_without_crashing():
    rows = parse_xlsx(_fake_dzen_xlsx())
    posts = _aggregate_posts(rows, "brief")

    # Строка поста 1 несёт дробное значение "1.5" в колонке time_min —
    # int(float(...)) должен обрезать его до 1, а не упасть.
    assert posts[0]["time_min"] == 1
    assert isinstance(posts[0]["time_min"], int)
