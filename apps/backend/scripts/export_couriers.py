"""Извлечь все непустые записи Users без изменения исходных значений."""

import argparse
import json
import posixpath
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from lxml import etree

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _xml(archive: ZipFile, path: str) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(archive.read(path), parser=parser)
    if root.getroottree().docinfo.internalDTD is not None:
        raise ValueError("DTD is not allowed in XLSX")
    return root


def _text(element: etree._Element) -> str:
    return "".join(node.text or "" for node in element.findall(".//m:t", NS))


def _value(cell: etree._Element, strings: list[str]) -> str | bool | None:
    kind = cell.get("t")
    if kind == "inlineStr":
        return _text(cell) or None
    value = cell.find("m:v", NS)
    if value is None or value.text is None:
        if cell.find("m:f", NS) is not None:
            raise ValueError(f"Formula without cached value at {cell.get('r')}")
        return None
    if kind == "s":
        return strings[int(value.text)]
    if kind == "b":
        return value.text == "1"
    if kind == "e":
        raise ValueError(f"Excel error at {cell.get('r')}")
    # Числа остаются текстом: телефон/счёт не теряют точность при чтении JSON.
    return value.text


def export_users(path: Path) -> dict[str, Any]:
    with ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = [_text(item) for item in _xml(archive, "xl/sharedStrings.xml")]
        relationships = {
            node.get("Id"): node.get("Target")
            for node in _xml(archive, "xl/_rels/workbook.xml.rels")
        }
        workbook = _xml(archive, "xl/workbook.xml")
        sheets = workbook.findall("m:sheets/m:sheet", NS)
        sheet = next((item for item in sheets if item.get("name") == "Users"), None)
        if sheet is None:
            raise ValueError("Users sheet is missing")
        target = relationships.get(sheet.get(REL_ID))
        if not target:
            raise ValueError("Users sheet relationship is missing")
        sheet_path = (
            target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        )
        rows = _xml(archive, sheet_path).findall("m:sheetData/m:row", NS)
        headers: dict[str, str] = {}
        records = []
        for row in rows:
            cells = {
                str(cell.get("r")).rstrip("0123456789"): _value(cell, strings)
                for cell in row.findall("m:c", NS)
            }
            if not any(value is not None and value != "" for value in cells.values()):
                continue
            if not headers:
                headers = {col: str(value) for col, value in cells.items() if value is not None}
                if len(set(headers.values())) != len(headers) or "id" not in headers.values():
                    raise ValueError("Users headers must be unique and contain id")
                continue
            unknown = {col for col, value in cells.items() if value is not None} - headers.keys()
            if unknown:
                raise ValueError(f"Unnamed columns at row {row.get('r')}: {sorted(unknown)}")
            values = {name: cells.get(col) for col, name in headers.items()}
            records.append(
                {
                    "source_row": int(str(row.get("r"))),
                    "legacy_id": values.get("id"),
                    "values": values,
                }
            )
        if not records:
            raise ValueError("Users has no records")
        return {"schema_version": 1, "sheet": "Users", "couriers": records}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output must differ")
    result = export_users(args.input)
    write_json(args.output, result)
    print(json.dumps({"exported_count": len(result["couriers"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
