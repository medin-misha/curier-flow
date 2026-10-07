"""Преобразовать исходные Users в контракт импорта и отчёт по каждой строке."""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.modules.courier_module.schemas.imports import CourierImportRecord
from scripts.export_couriers import write_json

STATUSES = {
    "pending": "pending",
    "processing": "active",
    "in activation": "active",
    "active": "active",
    "inoperative": "inactive",
}
MAX_SOURCE_LENGTH = 64
PLATFORMS = {"bolt": "bolt_food", "bolt_food": "bolt_food", "foodora": "foodora", "wolt": "wolt"}
EXPECTED_COLUMNS = {
    "created_at",
    "name",
    "email",
    "phone",
    "how_found_it",
    "desired_transport",
    "birth_date",
    "telegram",
    "whatsapp",
    "city",
    "address",
    "work_in",
    "citizenship",
    "invoice",
    "status",
    "consent",
    "id",
}


def _string(value: object) -> str:
    return "" if value is None else str(value)


def _platforms(value: str, *, accept_question_platforms: bool, warnings: list[str]) -> list[str]:
    normalized = value.strip().lower().replace("\\n", " ")
    normalized = re.sub(r"bolt\s+food\b", "bolt_food", normalized)
    if normalized == "bolt перевод":
        normalized = "bolt"
        warnings.append("platform-transfer-suffix-removed")
    if "?" in normalized:
        if not accept_question_platforms:
            raise ValueError("uncertain-platform")
        normalized = normalized.replace("?", "")
        warnings.append("platform-question-mark-removed")
    tokens = [item for item in re.split(r"[,/\s]+", normalized) if item]
    if not tokens or any(item not in PLATFORMS for item in tokens):
        raise ValueError("unknown-platform")
    return list(dict.fromkeys(PLATFORMS[item] for item in tokens))


def _phone(value: str, prefix: str | None, warnings: list[str]) -> str:
    normalized = value.translate(str.maketrans("", "", " -()"))
    if prefix and re.fullmatch(r"\d{9}", normalized):
        warnings.append("local-phone-prefix-added")
        return prefix + normalized
    if normalized.startswith("00"):
        warnings.append("international-phone-prefix-normalized")
        return "+" + normalized[2:]
    if prefix and normalized.startswith(prefix[1:]) and len(normalized) == len(prefix) - 1 + 9:
        warnings.append("international-phone-plus-added")
        return "+" + normalized
    return normalized


def _consent(value: object) -> bool:
    normalized = _string(value).strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError("invalid-consent")
    return normalized == "true"


def _convert_record(
    record: dict[str, Any],
    *,
    local_phone_prefix: str | None,
    accept_question_platforms: bool,
    warnings: list[str],
) -> CourierImportRecord:
    values = record["values"]
    unknown = set(values) - EXPECTED_COLUMNS
    if unknown:
        raise ValueError("unknown-source-columns")
    text = {name: _string(value).strip() for name, value in values.items()}
    status = STATUSES.get(text.get("status", "").lower())
    if status is None:
        raise ValueError("unknown-status")
    platforms = _platforms(
        text.get("work_in", ""),
        accept_question_platforms=accept_question_platforms,
        warnings=warnings,
    )
    telegram = text.get("telegram", "")
    # WhatsApp остаётся исходным текстом, включая пробелы и префиксы.
    whatsapp = _string(values.get("whatsapp"))
    contact_platform = "telegram" if telegram else "whatsapp" if whatsapp.strip() else None
    contact = telegram or (whatsapp if whatsapp.strip() else None)
    if telegram and whatsapp.strip():
        warnings.append("secondary-whatsapp-preserved-in-source")
    source = text.get("how_found_it") or None
    if source and len(source) > MAX_SOURCE_LENGTH:
        warnings.append("long-source-preserved-in-source")
        source = None
    bank = text.get("invoice") or None
    if bank and not re.fullmatch(r"(?:\d+-)?\d+/\d{4}|[A-Z]{2}\d{2}[A-Z0-9 ]+", bank):
        warnings.append("bank-account-needs-review")
    courier = {
        "full_name": text.get("name", ""),
        "email": text.get("email", ""),
        "phone": _phone(text.get("phone", ""), local_phone_prefix, warnings),
        "date_of_birth": text.get("birth_date", ""),
        "created_at": text.get("created_at", ""),
        "city": text.get("city") or None,
        "address": text.get("address") or None,
        "citizenship": text.get("citizenship") or None,
        "bank_account": bank,
        "contact_platform": contact_platform,
        "contact": contact,
        "source": source,
        "consent_to_processing": _consent(values.get("consent")),
        "platform_accounts": [{"platform": platform, "status": status} for platform in platforms],
    }
    return CourierImportRecord.model_validate(
        {"source_row": record["source_row"], "legacy_id": record["legacy_id"], "courier": courier}
    )


def convert_users(
    source: dict[str, Any],
    *,
    local_phone_prefix: str | None = None,
    accept_question_platforms: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if source.get("schema_version") != 1 or source.get("sheet") != "Users":
        raise ValueError("Expected schema_version=1, sheet=Users")
    records = source["couriers"]
    if local_phone_prefix and re.fullmatch(r"\+[1-9]\d{0,3}", local_phone_prefix) is None:
        raise ValueError("Invalid local phone prefix")
    rows = [row["source_row"] for row in records]
    ids = [row["legacy_id"] for row in records]
    if len(rows) != len(set(rows)) or len(ids) != len(set(ids)):
        raise ValueError("Duplicate source_row or legacy_id")
    accepted = []
    issues = []
    identities: dict[str, dict[str, list[int]]] = {
        "email": defaultdict(list),
        "phone": defaultdict(list),
    }
    for record in records:
        warnings: list[str] = []
        errors: list[dict[str, str]] = []
        try:
            converted = _convert_record(
                record,
                local_phone_prefix=local_phone_prefix,
                accept_question_platforms=accept_question_platforms,
                warnings=warnings,
            )
        except ValidationError as error:
            errors = [
                {"field": ".".join(str(part) for part in entry["loc"]), "reason": entry["msg"]}
                for entry in error.errors(include_input=False, include_url=False)
            ]
        except ValueError as error:
            errors = [{"field": "source", "reason": str(error)}]
        else:
            accepted.append(converted.model_dump(mode="json"))
            identities["email"][converted.courier.email].append(converted.source_row)
            identities["phone"][converted.courier.phone].append(converted.source_row)
        if warnings or errors:
            issues.append(
                {
                    "source_row": record["source_row"],
                    "legacy_id": record["legacy_id"],
                    "warnings": warnings,
                    "errors": errors,
                }
            )
    duplicate_groups = [
        {"field": field, "source_rows": source_rows}
        for field, groups in identities.items()
        for source_rows in groups.values()
        if len(source_rows) > 1
    ]
    report = {
        "schema_version": 1,
        "input_count": len(records),
        "accepted_count": len(accepted),
        "rejected_count": len(records) - len(accepted),
        "options": {
            "local_phone_prefix": local_phone_prefix,
            "accept_question_platforms": accept_question_platforms,
        },
        "issues": issues,
        "duplicate_groups": duplicate_groups,
    }
    return {"schema_version": 1, "couriers": accepted}, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--local-phone-prefix")
    parser.add_argument("--accept-question-platforms", action="store_true")
    args = parser.parse_args()
    paths = (args.input, args.output, args.report)
    if len({path.resolve() for path in paths}) != len(paths):
        parser.error("Input, output and report must differ")
    result, report = convert_users(
        json.loads(args.input.read_text(encoding="utf-8")),
        local_phone_prefix=args.local_phone_prefix,
        accept_question_platforms=args.accept_question_platforms,
    )
    write_json(args.output, result)
    write_json(args.report, report)
    print(
        json.dumps(
            {name: report[name] for name in ("input_count", "accepted_count", "rejected_count")}
        )
    )
    if report["rejected_count"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
