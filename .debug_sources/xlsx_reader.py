from __future__ import annotations

import datetime as _dt
import math
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def col_to_index(col: str) -> int:
    n = 0
    for ch in col.upper():
        if "A" <= ch <= "Z":
            n = n * 26 + (ord(ch) - 64)
    return n - 1


def split_cell_ref(ref: str) -> Tuple[int, int]:
    m = re.match(r"([A-Z]+)(\d+)", ref.upper())
    if not m:
        return 0, 0
    return int(m.group(2)) - 1, col_to_index(m.group(1))


def _parse_range(ref: str) -> Tuple[int, int, int, int]:
    if ":" not in ref:
        r, c = split_cell_ref(ref)
        return r, c, r, c
    a, b = ref.split(":", 1)
    r1, c1 = split_cell_ref(a)
    r2, c2 = split_cell_ref(b)
    return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)


def excel_serial_to_datetime(value: float) -> _dt.datetime:
    # Excel's Windows 1900 date system. The 1899-12-30 origin handles the fake 1900-02-29.
    base = _dt.datetime(1899, 12, 30)
    return base + _dt.timedelta(days=float(value))


def _looks_like_date_format(fmt: str) -> bool:
    if not fmt:
        return False
    # Remove quoted literals and escaped characters; then inspect date/time tokens.
    f = re.sub(r'"[^\"]*"', '', fmt.lower())
    f = re.sub(r"\\.", "", f)
    # Avoid treating pure numeric formats with m as date accidentally.
    return bool(re.search(r"(^|[^a-z])(d{1,4}|y{2,4}|h{1,2}|s{1,2}|m{1,4})([^a-z]|$)", f))


@dataclass
class SheetData:
    name: str
    matrix: List[List[Any]]
    formulas_without_cached_values: int = 0


class XlsxWorkbook:
    """Minimal XLSX/XLSM reader using only Python stdlib.

    Designed for saved media plans: reads cached formula results when present,
    shared strings, inline strings, numbers, booleans, merged cells and common dates.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if self.path.suffix.lower() not in {".xlsx", ".xlsm"}:
            raise ValueError("Поддерживаются .xlsx и .xlsm. Старый .xls нужно сохранить как .xlsx.")
        self._zip = zipfile.ZipFile(self.path, "r")
        self.shared_strings = self._read_shared_strings()
        self.date_style_ids = self._read_date_style_ids()
        self.sheet_paths = self._read_sheet_paths()

    def close(self):
        self._zip.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _read_xml(self, name: str) -> Optional[ET.Element]:
        try:
            with self._zip.open(name) as f:
                return ET.parse(f).getroot()
        except KeyError:
            return None

    def _read_shared_strings(self) -> List[str]:
        root = self._read_xml("xl/sharedStrings.xml")
        if root is None:
            return []
        out = []
        for si in root.findall(_q(NS_MAIN, "si")):
            parts: List[str] = []
            # Plain <t> or rich text <r><t>
            direct = si.find(_q(NS_MAIN, "t"))
            if direct is not None:
                parts.append(direct.text or "")
            for r in si.findall(_q(NS_MAIN, "r")):
                t = r.find(_q(NS_MAIN, "t"))
                if t is not None:
                    parts.append(t.text or "")
            out.append("".join(parts))
        return out

    def _read_date_style_ids(self) -> set[int]:
        root = self._read_xml("xl/styles.xml")
        if root is None:
            return set()

        custom: Dict[int, str] = {}
        numfmts = root.find(_q(NS_MAIN, "numFmts"))
        if numfmts is not None:
            for nf in numfmts.findall(_q(NS_MAIN, "numFmt")):
                try:
                    custom[int(nf.attrib.get("numFmtId", "0"))] = nf.attrib.get("formatCode", "")
                except Exception:
                    pass

        # Common built-in Excel date formats.
        builtin_date_ids = {
            14, 15, 16, 17, 18, 19, 20, 21, 22,
            27, 30, 36, 45, 46, 47, 50, 57,
        }

        ids = set()
        cellxfs = root.find(_q(NS_MAIN, "cellXfs"))
        if cellxfs is None:
            return ids
        for idx, xf in enumerate(cellxfs.findall(_q(NS_MAIN, "xf"))):
            try:
                nf_id = int(xf.attrib.get("numFmtId", "0"))
            except Exception:
                nf_id = 0
            fmt = custom.get(nf_id, "")
            if nf_id in builtin_date_ids or _looks_like_date_format(fmt):
                ids.add(idx)
        return ids

    def _read_sheet_paths(self) -> List[Tuple[str, str]]:
        wb_root = self._read_xml("xl/workbook.xml")
        rel_root = self._read_xml("xl/_rels/workbook.xml.rels")
        if wb_root is None:
            return []

        rel_map: Dict[str, str] = {}
        if rel_root is not None:
            for rel in rel_root.findall(_q(NS_PKG_REL, "Relationship")):
                rid = rel.attrib.get("Id")
                target = rel.attrib.get("Target")
                if rid and target:
                    if target.startswith("/"):
                        target = target.lstrip("/")
                    elif not target.startswith("xl/"):
                        target = "xl/" + target.lstrip("/")
                    rel_map[rid] = target

        out = []
        sheets = wb_root.find(_q(NS_MAIN, "sheets"))
        if sheets is None:
            return out
        for s in sheets.findall(_q(NS_MAIN, "sheet")):
            name = s.attrib.get("name", "Sheet")
            rid = s.attrib.get(_q(NS_REL, "id"))
            target = rel_map.get(rid or "")
            if target:
                out.append((name, target))
        return out

    def sheet_names(self) -> List[str]:
        return [x[0] for x in self.sheet_paths]

    def _cell_value(self, cell: ET.Element) -> Tuple[Any, bool]:
        t = cell.attrib.get("t")
        style_id = int(cell.attrib.get("s", "0") or 0)
        formula = cell.find(_q(NS_MAIN, "f"))
        v_node = cell.find(_q(NS_MAIN, "v"))

        if t == "inlineStr":
            is_node = cell.find(_q(NS_MAIN, "is"))
            if is_node is None:
                return "", False
            texts = []
            direct = is_node.find(_q(NS_MAIN, "t"))
            if direct is not None:
                texts.append(direct.text or "")
            for r in is_node.findall(_q(NS_MAIN, "r")):
                tt = r.find(_q(NS_MAIN, "t"))
                if tt is not None:
                    texts.append(tt.text or "")
            return "".join(texts), False

        raw = v_node.text if v_node is not None else None
        missing_cached_formula = formula is not None and raw is None

        if raw is None:
            return None, missing_cached_formula
        if t == "s":
            try:
                return self.shared_strings[int(raw)], missing_cached_formula
            except Exception:
                return raw, missing_cached_formula
        if t in {"str", "e"}:
            return raw, missing_cached_formula
        if t == "b":
            return raw == "1", missing_cached_formula

        try:
            num = float(raw)
            if style_id in self.date_style_ids:
                dt = excel_serial_to_datetime(num)
                # Most media plans only need date precision.
                if abs(num - int(num)) < 1e-9:
                    return dt.date(), missing_cached_formula
                return dt, missing_cached_formula
            if abs(num - int(num)) < 1e-12:
                return int(num), missing_cached_formula
            return num, missing_cached_formula
        except Exception:
            return raw, missing_cached_formula

    def read_sheet(self, sheet_name: str, max_rows: int = 10000, max_cols: int = 400) -> SheetData:
        path = None
        for name, p in self.sheet_paths:
            if name == sheet_name:
                path = p
                break
        if path is None:
            raise KeyError(sheet_name)

        root = self._read_xml(path)
        if root is None:
            return SheetData(sheet_name, [])

        values: Dict[Tuple[int, int], Any] = {}
        max_r = -1
        max_c = -1
        formula_missing = 0

        sheet_data = root.find(_q(NS_MAIN, "sheetData"))
        if sheet_data is not None:
            for row in sheet_data.findall(_q(NS_MAIN, "row")):
                # Worksheet rows are stored in ascending order. Respect max_rows before
                # walking every cell: discovery only needs the media-plan header/table
                # area and large reference tabs can otherwise contain tens of thousands
                # of irrelevant cells. Full parsing still uses the normal 10k-row limit.
                try:
                    row_index = int(row.attrib.get("r", "0") or 0) - 1
                except Exception:
                    row_index = -1
                if row_index >= max_rows:
                    break
                for c in row.findall(_q(NS_MAIN, "c")):
                    ref = c.attrib.get("r")
                    if not ref:
                        continue
                    rr, cc = split_cell_ref(ref)
                    if rr >= max_rows or cc >= max_cols:
                        continue
                    val, missing = self._cell_value(c)
                    if missing:
                        formula_missing += 1
                    values[(rr, cc)] = val
                    max_r = max(max_r, rr)
                    max_c = max(max_c, cc)

        # Spread merged-cell top-left values to all cells in merge range.
        merges = root.find(_q(NS_MAIN, "mergeCells"))
        if merges is not None:
            for mc in merges.findall(_q(NS_MAIN, "mergeCell")):
                ref = mc.attrib.get("ref")
                if not ref:
                    continue
                r1, c1, r2, c2 = _parse_range(ref)
                if r1 >= max_rows or c1 >= max_cols:
                    continue
                val = values.get((r1, c1))
                for rr in range(r1, min(r2, max_rows - 1) + 1):
                    for cc in range(c1, min(c2, max_cols - 1) + 1):
                        if (rr, cc) not in values:
                            values[(rr, cc)] = val
                            max_r = max(max_r, rr)
                            max_c = max(max_c, cc)

        if max_r < 0 or max_c < 0:
            return SheetData(sheet_name, [], formula_missing)

        matrix = [[None] * (max_c + 1) for _ in range(max_r + 1)]
        for (r, c), v in values.items():
            if r < len(matrix) and c < len(matrix[r]):
                matrix[r][c] = v
        return SheetData(sheet_name, matrix, formula_missing)


    def read_sheet_preview(self, sheet_name: str, max_rows: int = 360, max_cols: int = 180) -> SheetData:
        """Streaming sheet preview for workbook discovery.

        Unlike :meth:`read_sheet`, this method never builds the full worksheet XML tree.
        It walks rows with ``iterparse`` and clears them immediately, so large targeting/
        reference tabs do not make plan discovery disproportionately expensive. Merged
        cells inside the preview range are preserved.
        """
        path = None
        for name, p in self.sheet_paths:
            if name == sheet_name:
                path = p
                break
        if path is None:
            raise KeyError(sheet_name)

        values: Dict[Tuple[int, int], Any] = {}
        merges: List[str] = []
        max_r = -1
        max_c = -1
        formula_missing = 0
        try:
            with self._zip.open(path) as fh:
                for _event, elem in ET.iterparse(fh, events=("end",)):
                    if elem.tag == _q(NS_MAIN, "row"):
                        try:
                            rr_hint = int(elem.attrib.get("r", "0") or 0) - 1
                        except Exception:
                            rr_hint = -1
                        # Discovery never needs rows below the table-search window. Stop
                        # decompressing/parsing the XML entirely once that boundary is hit.
                        if rr_hint >= max_rows:
                            elem.clear()
                            break
                        for c in elem.findall(_q(NS_MAIN, "c")):
                            ref = c.attrib.get("r")
                            if not ref:
                                continue
                            rr, cc = split_cell_ref(ref)
                            if rr >= max_rows or cc >= max_cols:
                                continue
                            val, missing = self._cell_value(c)
                            if missing:
                                formula_missing += 1
                            values[(rr, cc)] = val
                            max_r = max(max_r, rr)
                            max_c = max(max_c, cc)
                        elem.clear()
                    elif elem.tag == _q(NS_MAIN, "mergeCell"):
                        ref = elem.attrib.get("ref")
                        if ref:
                            merges.append(ref)
                        elem.clear()
        except KeyError:
            return SheetData(sheet_name, [])

        for ref in merges:
            r1, c1, r2, c2 = _parse_range(ref)
            if r1 >= max_rows or c1 >= max_cols:
                continue
            val = values.get((r1, c1))
            for rr in range(r1, min(r2, max_rows - 1) + 1):
                for cc in range(c1, min(c2, max_cols - 1) + 1):
                    if (rr, cc) not in values:
                        values[(rr, cc)] = val
                        max_r = max(max_r, rr)
                        max_c = max(max_c, cc)

        if max_r < 0 or max_c < 0:
            return SheetData(sheet_name, [], formula_missing)
        matrix = [[None] * (max_c + 1) for _ in range(max_r + 1)]
        for (r, c), v in values.items():
            if r < len(matrix) and c < len(matrix[r]):
                matrix[r][c] = v
        return SheetData(sheet_name, matrix, formula_missing)

    def read_all(self) -> Dict[str, SheetData]:
        return {name: self.read_sheet(name) for name in self.sheet_names()}
