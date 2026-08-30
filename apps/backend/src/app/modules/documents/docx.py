"""Строгий разбор и рендеринг placeholders внутри OOXML DOCX."""

from __future__ import annotations

import re
import stat
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, LargeZipFile, ZipFile

from lxml import etree

TemplateFields = dict[str, list[str]]

_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_PARAGRAPH_TAG = f"{{{_WORD_NAMESPACE}}}p"
_TEXT_TAG = f"{{{_WORD_NAMESPACE}}}t"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_CONTENT_TYPES_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"
_CONTENT_TYPE_OVERRIDE = f"{{{_CONTENT_TYPES_NAMESPACE}}}Override"
_CONTENT_TYPES = "[Content_Types].xml"
_DOCUMENT_XML = "word/document.xml"
_DOCX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
_FIELD_TOKEN = re.compile(r"\{(?P<group>[a-z][a-z0-9_]{0,63})\.(?P<field>[a-z][a-z0-9_]{0,63})\}")
_BRACED_TOKEN = re.compile(r"\{(?P<body>[^{}\r\n]+)\}")


class DocxTemplateError(ValueError):
    """DOCX повреждён, небезопасен или нарушает синтаксис шаблона."""


@dataclass(frozen=True, slots=True)
class DocxLimits:
    """Пределы распакованного DOCX и числа placeholders."""

    max_uncompressed_size: int
    max_archive_entries: int
    max_fields: int


def extract_template_fields(source: bytes, *, limits: DocxLimits) -> TemplateFields:
    """Проверить DOCX и вернуть каноническую сгруппированную схему полей."""
    try:
        with ZipFile(BytesIO(source)) as archive:
            _validate_archive(archive, limits=limits)
            broken = archive.testzip()
            if broken is not None:
                raise DocxTemplateError(f"DOCX entry has an invalid checksum: {broken}")
            groups: dict[str, set[str]] = {}
            for info in archive.infolist():
                if not _is_word_xml(info.filename):
                    continue
                root = _parse_xml(archive.read(info))
                for paragraph in root.iter(_PARAGRAPH_TAG):
                    text = _paragraph_text(paragraph)
                    _reject_malformed_tokens(text)
                    for match in _FIELD_TOKEN.finditer(text):
                        groups.setdefault(match.group("group"), set()).add(match.group("field"))
    except DocxTemplateError:
        raise
    except (BadZipFile, LargeZipFile, RuntimeError, etree.XMLSyntaxError) as error:
        raise DocxTemplateError("File is not a valid DOCX archive") from error

    fields = {group: sorted(groups[group]) for group in sorted(groups)}
    field_count = sum(len(names) for names in fields.values())
    if field_count == 0:
        raise DocxTemplateError("DOCX template contains no placeholders")
    if field_count > limits.max_fields:
        raise DocxTemplateError(
            f"DOCX template contains {field_count} fields; limit is {limits.max_fields}"
        )
    return fields


def render_template(
    source: bytes,
    values: dict[str, str],
    *,
    limits: DocxLimits,
) -> bytes:
    """Подставить проверенные строковые значения и вернуть новый DOCX."""
    try:
        with ZipFile(BytesIO(source)) as archive:
            _validate_archive(archive, limits=limits)
            output = BytesIO()
            with ZipFile(output, mode="w") as rendered:
                for info in archive.infolist():
                    body = archive.read(info)
                    if _is_word_xml(info.filename):
                        root = _parse_xml(body)
                        changed = False
                        for paragraph in root.iter(_PARAGRAPH_TAG):
                            changed = _replace_paragraph(paragraph, values) or changed
                        if changed:
                            body = etree.tostring(
                                root.getroottree(),
                                encoding="UTF-8",
                                xml_declaration=True,
                            )
                    rendered.writestr(info, body)
            return output.getvalue()
    except DocxTemplateError:
        raise
    except (BadZipFile, LargeZipFile, RuntimeError, etree.XMLSyntaxError) as error:
        raise DocxTemplateError("File is not a valid DOCX archive") from error


def _validate_archive(archive: ZipFile, *, limits: DocxLimits) -> None:
    """Проверить package-level структуру и пределы до распаковки."""
    infos = archive.infolist()
    if len(infos) > limits.max_archive_entries:
        raise DocxTemplateError(
            f"DOCX archive contains {len(infos)} entries; limit is {limits.max_archive_entries}"
        )

    names: set[str] = set()
    total_size = 0
    for info in infos:
        path = PurePosixPath(info.filename)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in info.filename
            or info.filename in names
        ):
            raise DocxTemplateError("DOCX archive contains an unsafe or duplicate path")
        names.add(info.filename)
        if info.flag_bits & 0x1:
            raise DocxTemplateError("Encrypted DOCX entries are not supported")
        file_type = (info.external_attr >> 16) & 0o170000
        if file_type == stat.S_IFLNK:
            raise DocxTemplateError("DOCX archive must not contain symbolic links")
        total_size += info.file_size
        if total_size > limits.max_uncompressed_size:
            raise DocxTemplateError(
                f"DOCX uncompressed size exceeds the {limits.max_uncompressed_size} byte limit"
            )

    if _CONTENT_TYPES not in names or _DOCUMENT_XML not in names:
        raise DocxTemplateError("DOCX package has no main Word document")
    if any(name.casefold().endswith("vbaproject.bin") for name in names):
        raise DocxTemplateError("Macro-enabled DOCX documents are not supported")
    content_types = _parse_xml(archive.read(_CONTENT_TYPES))
    main_types = [
        node.get("ContentType", "").lower()
        for node in content_types.iter(_CONTENT_TYPE_OVERRIDE)
        if node.get("PartName") == "/word/document.xml"
    ]
    if main_types != [_DOCX_MAIN_CONTENT_TYPE]:
        raise DocxTemplateError("Only non-macro DOCX documents are supported")


def _is_word_xml(name: str) -> bool:
    """Выбрать Word XML parts, где могут находиться текстовые параграфы."""
    return name.startswith("word/") and name.endswith(".xml")


def _parse_xml(body: bytes) -> etree._Element:
    """Разобрать OOXML без DTD, entity resolution и сетевого доступа."""
    if b"<!doctype" in body.lower():
        raise DocxTemplateError("DOCTYPE is forbidden in DOCX XML parts")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        remove_blank_text=False,
        huge_tree=False,
    )
    return etree.fromstring(body, parser=parser)


def _paragraph_text(paragraph: etree._Element) -> str:
    """Склеить Word runs одного параграфа для поиска разорванной метки."""
    return "".join(node.text or "" for node in paragraph.iter(_TEXT_TAG))


def _reject_malformed_tokens(text: str) -> None:
    """Считать любые фигурные dotted-конструкции зарезервированными метками."""
    for candidate in _BRACED_TOKEN.finditer(text):
        if "." in candidate.group("body") and _FIELD_TOKEN.fullmatch(candidate.group(0)) is None:
            raise DocxTemplateError(f"Malformed placeholder: {candidate.group(0)}")


def _replace_paragraph(paragraph: etree._Element, values: dict[str, str]) -> bool:
    """Заменить метки, даже если Word разделил их между несколькими runs."""
    nodes = list(paragraph.iter(_TEXT_TAG))
    original = [node.text or "" for node in nodes]
    text = "".join(original)
    matches = list(_FIELD_TOKEN.finditer(text))
    if not matches:
        return False

    boundaries: list[tuple[int, int]] = []
    position = 0
    for value in original:
        boundaries.append((position, position + len(value)))
        position += len(value)

    for match in reversed(matches):
        path = f"{match.group('group')}.{match.group('field')}"
        replacement = values[path]
        start_index, start_offset = _locate(boundaries, match.start())
        end_index, end_offset = _locate(boundaries, match.end() - 1)
        end_offset += 1

        start_node = nodes[start_index]
        end_node = nodes[end_index]
        if start_index == end_index:
            current = start_node.text or ""
            start_node.text = current[:start_offset] + replacement + current[end_offset:]
            _preserve_edge_spaces(start_node)
            continue

        start_text = start_node.text or ""
        end_text = end_node.text or ""
        start_node.text = start_text[:start_offset] + replacement
        for node in nodes[start_index + 1 : end_index]:
            node.text = ""
        end_node.text = end_text[end_offset:]
        _preserve_edge_spaces(start_node)
        _preserve_edge_spaces(end_node)
    return True


def _locate(boundaries: list[tuple[int, int]], position: int) -> tuple[int, int]:
    """Сопоставить позицию объединённого текста конкретному `w:t`."""
    for index, (start, end) in enumerate(boundaries):
        if start <= position < end:
            return index, position - start
    raise DocxTemplateError("Placeholder position is outside Word text nodes")


def _preserve_edge_spaces(node: etree._Element) -> None:
    """Попросить Word не схлопывать пробелы по краям изменённого `w:t`."""
    text = node.text or ""
    if text and (text[0].isspace() or text[-1].isspace()):
        node.set(_XML_SPACE, "preserve")
