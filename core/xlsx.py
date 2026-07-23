"""Минимальный XLSX-ридер (порт из проверенного dzen_snapshot.py Маши)."""
import io
import zipfile
from xml.etree import ElementTree as ET

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _col_index(ref: str) -> int:
    """A1-style cell ref (e.g. 'C2') -> 0-based column index."""
    letters = "".join(ch for ch in ref if ch.isalpha())
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1


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
            indexed = []  # [(col_idx, value), ...] — seated at the cell's true position
            pos = 0
            for c in r.findall("s:c", NS):
                ref = c.get("r")
                idx = _col_index(ref) if ref else pos
                v = c.find("s:v", NS)
                if v is None or v.text is None:
                    val = ""
                elif c.get("t", "n") == "s":
                    val = sst[int(v.text)]
                else:
                    val = v.text
                indexed.append((idx, val))
                pos = idx + 1
            if not indexed:
                rows.append([])
                continue
            width = max(idx for idx, _ in indexed) + 1
            cells = [""] * width
            for idx, val in indexed:
                cells[idx] = val
            rows.append(cells)
        return rows
