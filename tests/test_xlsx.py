import io
import zipfile
from core.xlsx import parse_xlsx

_CT = """<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
</Types>"""
_SST = """<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">
<si><t>Заголовок</t></si><si><t>Пост 1</t></si></sst>"""
_SHEET = """<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c t="s"><v>0</v></c></row>
<row r="2"><c t="s"><v>1</v></c><c><v>42</v></c></row>
</sheetData></worksheet>"""


def _fake_xlsx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("xl/sharedStrings.xml", _SST)
        z.writestr("xl/worksheets/sheet1.xml", _SHEET)
    return buf.getvalue()


def test_parse_xlsx():
    rows = parse_xlsx(_fake_xlsx())
    assert rows[0] == ["Заголовок"]
    assert rows[1] == ["Пост 1", "42"]
