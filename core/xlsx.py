"""Минимальный XLSX-ридер (порт из проверенного dzen_snapshot.py Маши)."""
import io
import zipfile
from xml.etree import ElementTree as ET

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def parse_xlsx(blob: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        sst = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("s:si", NS):
                t = si.find(".//s:t", NS)
                sst.append(t.text if t is not None and t.text else "")
        sheet = next((n for n in z.namelist()
                      if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")), None)
        if not sheet:
            return []
        root = ET.fromstring(z.read(sheet))
        rows = []
        for r in root.findall(".//s:row", NS):
            cells = []
            for c in r.findall("s:c", NS):
                v = c.find("s:v", NS)
                if v is None or v.text is None:
                    cells.append("")
                elif c.get("t", "n") == "s":
                    cells.append(sst[int(v.text)])
                else:
                    cells.append(v.text)
            rows.append(cells)
        return rows
