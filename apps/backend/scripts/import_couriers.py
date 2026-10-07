"""Проверить подготовленную пачку через API и явно применить импорт."""

import argparse
import json
import ssl
from pathlib import Path

import httpx

from app.modules.courier_module.schemas.imports import CourierImportBatch, CourierImportResponse
from scripts.export_couriers import write_json


def submit(
    client: httpx.Client, batch: CourierImportBatch, *, dry_run: bool
) -> CourierImportResponse:
    response = client.post(
        "/import-courier",
        params={"dry_run": str(dry_run).lower()},
        json=batch.model_dump(mode="json"),
    )
    response.raise_for_status()
    return CourierImportResponse.model_validate(response.json())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-conflicts", action="store_true")
    args = parser.parse_args()
    if args.output.resolve() in {args.input.resolve(), args.token_file.resolve()}:
        parser.error("Output must differ from input and token file")
    url = httpx.URL(args.url)
    if url.scheme != "https":
        parser.error("Use the HTTPS ingress URL")
    if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        parser.error("URL must contain only scheme and host")
    token = args.token_file.read_text(encoding="utf-8").strip()
    if not token:
        parser.error("Token file is empty")
    batch = CourierImportBatch.model_validate_json(args.input.read_text(encoding="utf-8"))
    tls = ssl.create_default_context(cafile=args.ca_file)
    with httpx.Client(
        base_url=args.url,
        headers={"authorization": f"Bearer {token}"},
        verify=tls,
        timeout=60,
    ) as client:
        preview = submit(client, batch, dry_run=True)
        write_json(args.output, {"preview": preview.model_dump(mode="json"), "applied": None})
        if preview.conflict_count and not args.allow_conflicts:
            print(json.dumps({"conflict_count": preview.conflict_count, "applied": False}))
            raise SystemExit(2)
        if args.apply:
            applied = submit(client, batch, dry_run=False)
            write_json(
                args.output,
                {
                    "preview": preview.model_dump(mode="json"),
                    "applied": applied.model_dump(mode="json"),
                },
            )
            print(json.dumps(applied.model_dump(mode="json", exclude={"results"})))
            if applied.conflict_count:
                raise SystemExit(2)
        else:
            print(json.dumps(preview.model_dump(mode="json", exclude={"results"})))


if __name__ == "__main__":
    main()
