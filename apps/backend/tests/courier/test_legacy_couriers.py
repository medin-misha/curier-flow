"""Преобразование Excel без доступа к БД и без персональных тестовых данных."""

from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest

from app.modules.courier_module.schemas.imports import CourierImportBatch
from scripts.convert_couriers import convert_users
from scripts.export_couriers import export_users


def source(**updates: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "sheet": "Users",
        "couriers": [
            {
                "source_row": 2,
                "legacy_id": "old-id",
                "values": {
                    "name": " Courier ",
                    "email": " USER@EXAMPLE.COM ",
                    "phone": "777 123 456",
                    "birth_date": "1990-02-03",
                    "created_at": "2024-01-02 03:04:05+00:00",
                    "city": " Praha ",
                    "address": " Street 1 ",
                    "citizenship": "CZ",
                    "invoice": "123456789/0100",
                    "how_found_it": "Friend",
                    "consent": "True",
                    "telegram": None,
                    "whatsapp": "+ 420 (777) 123-456 ",
                    "work_in": "bolt?",
                    "status": "Active",
                    "desired_transport": "bike",
                    "id": "old-id",
                    **updates,
                },
            }
        ],
    }


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("Pending", "pending"),
        ("Processing", "active"),
        ("In activation", "active"),
        ("Active", "active"),
        ("Inoperative", "inactive"),
    ],
)
def test_statuses_phone_and_whatsapp(old: str, new: str) -> None:
    result, report = convert_users(
        source(status=old),
        local_phone_prefix="+420",
        accept_question_platforms=True,
    )
    validated = CourierImportBatch.model_validate(result)
    courier = validated.couriers[0].courier
    assert courier.email == "user@example.com"
    assert courier.phone == "+420777123456"
    assert courier.contact == "+ 420 (777) 123-456 "
    assert courier.contact_platform == "whatsapp"
    assert courier.platform_accounts[0].status == new
    assert report["rejected_count"] == 0
    assert "local-phone-prefix-added" in report["issues"][0]["warnings"]


@pytest.mark.parametrize("platforms", ["foodora,bolt", "bolt/foodora\\n", "bolt Foodora"])
def test_multiple_platforms(platforms: str) -> None:
    result, _ = convert_users(source(work_in=platforms), local_phone_prefix="+420")
    accounts = result["couriers"][0]["courier"]["platform_accounts"]
    assert {row["platform"] for row in accounts} == {"bolt_food", "foodora"}


@pytest.mark.parametrize(
    "updates",
    [
        {"status": "problem"},
        {"work_in": "Prague"},
        {"birth_date": None},
        {"birth_date": "2999-01-01"},
        {"phone": "not-a-phone"},
        {"consent": None},
    ],
)
def test_invalid_rows_remain_in_report(updates: dict[str, Any]) -> None:
    raw = source(**updates)
    result, report = convert_users(raw, local_phone_prefix="+420", accept_question_platforms=True)
    assert result["couriers"] == []
    assert report["input_count"] == report["rejected_count"] == 1
    assert report["issues"][0]["source_row"] == 2
    assert report["issues"][0]["errors"]
    assert raw == source(**updates)


def test_duplicates_are_preserved_and_source_is_not_truncated() -> None:
    raw = source(telegram="@courier", how_found_it="x" * 65)
    second = {**raw["couriers"][0], "source_row": 3, "legacy_id": "other-old-id"}
    raw["couriers"].append(second)
    result, report = convert_users(raw, local_phone_prefix="+420", accept_question_platforms=True)
    assert len(result["couriers"]) == 2
    assert len(report["duplicate_groups"]) == 2
    assert result["couriers"][0]["courier"]["source"] is None
    assert result["couriers"][0]["courier"]["contact"] == "@courier"
    assert raw["couriers"][0]["values"]["how_found_it"] == "x" * 65
    assert "secondary-whatsapp-preserved-in-source" in report["issues"][0]["warnings"]


def test_xlsx_selects_only_users_and_preserves_cells_and_row_numbers(tmp_path: Path) -> None:
    path = tmp_path / "input.xlsx"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<workbook
xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Users" r:id="r1"/><sheet name="Other" r:id="r2"/></sheets></workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<Relationships>
<Relationship Id="r1" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            """<sst
xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<si><t>id</t></si>
<si><t>phone</t></si>
<si><t>consent</t></si>
<si><t>extra</t></si>
</sst>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<worksheet
xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>
<row r="1">
<c r="A1" t="s"><v>0</v></c>
<c r="B1" t="s"><v>1</v></c>
<c r="C1" t="s"><v>2</v></c>
<c r="D1" t="s"><v>3</v></c></row>
<row r="2">
<c r="A2" t="inlineStr"><is><t>old-id</t></is></c>
<c r="B2"><v>777123456</v></c>
<c r="C2" t="b"><v>0</v></c>
<c r="D2" t="inlineStr"><is><t>original</t></is></c></row>
<row r="3"/><row r="4">
<c r="A4" t="inlineStr"><is><t>second</t></is></c></row>
</sheetData></worksheet>""",
        )
    result = export_users(path)
    assert len(result["couriers"]) == 2
    assert result["couriers"][1]["source_row"] == 4
    assert result["couriers"][0]["values"] == {
        "id": "old-id",
        "phone": "777123456",
        "consent": False,
        "extra": "original",
    }
