#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 SQL dump 转换为 OpenSearch JSONL 数据。

该脚本会解析 `INSERT INTO ... VALUES` 语句，并将每一行数据输出为
一条 JSON 文档，方便后续通过 `import_to_opensearch.py` 导入。主要特性：

* 支持直接读取压缩包（例如 `case_recovery.zip`）中的所有 `.sql` 文件；
* 自动跳过无关表，或根据 `--tables` 参数仅选择部分表；
* 尽量保留原始字段与数据类型，不对字段名做额外修改；
* 输出的 JSON 行包含 `_id`、`_index` 以及 `_source`，与导入脚本保持兼容；
* 通过日志输出转换统计信息，便于排查潜在的解析问题。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Sequence, Tuple
from zipfile import ZipFile

LOGGER = logging.getLogger(__name__)

INSERT_REGEX = re.compile(
    r"INSERT\s+INTO\s+`?(?P<table>[^`(\s]+)`?\s*(?P<columns>\([^)]*\))?\s*VALUES\s*(?P<values>.+?);",
    re.IGNORECASE | re.DOTALL,
)
CREATE_TABLE_REGEX = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(?P<table>[^`(\s]+)`?\s*\(",
    re.IGNORECASE,
)
COLUMN_NAME_REGEX = re.compile(r"^`?(?P<name>[A-Za-z0-9_]+)`?")
NUMBER_REGEX = re.compile(r"^-?\d+(?:\.\d+)?$")


@dataclass
class InsertStatement:
    table: str
    columns: Sequence[str]
    values: Sequence[object]


class SQLParseError(RuntimeError):
    """Raised when a values tuple cannot be parsed."""


def _decode_bytes(data: bytes, encodings: Sequence[str]) -> str:
    last_exc: Optional[Exception] = None
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except Exception as exc:  # pragma: no cover - 非常规编码
            last_exc = exc
    if last_exc:
        raise last_exc
    return data.decode()


def _split_value_tuples(block: str) -> Iterator[str]:
    depth = 0
    in_string = False
    escape = False
    current: List[str] = []

    for char in block:
        if in_string:
            current.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "'":
                in_string = False
            continue

        if char == "'":
            in_string = True
            current.append(char)
            continue

        if char == "(":
            if depth == 0:
                current = ["("]
            else:
                current.append(char)
            depth += 1
            continue

        if char == ")":
            if depth > 0:
                current.append(char)
            depth -= 1
            if depth == 0:
                tuple_text = "".join(current).strip()
                if tuple_text.endswith(","):
                    tuple_text = tuple_text[:-1].rstrip()
                if tuple_text.startswith("(") and tuple_text.endswith(")"):
                    yield tuple_text[1:-1]
                else:
                    yield tuple_text
            continue

        if depth > 0:
            current.append(char)

    if depth != 0:
        raise SQLParseError("VALUES 语句括号不匹配")


def _parse_value_tuple(tuple_text: str) -> List[object]:
    values: List[object] = []
    length = len(tuple_text)
    index = 0

    while index < length:
        while index < length and tuple_text[index].isspace():
            index += 1
        if index >= length:
            break

        char = tuple_text[index]
        if char == "'":
            index += 1
            buffer: List[str] = []
            while index < length:
                current = tuple_text[index]
                if current == "'":
                    next_index = index + 1
                    if next_index < length and tuple_text[next_index] == "'":
                        buffer.append("'")
                        index += 2
                        continue
                    index += 1
                    break
                if current == "\\":
                    next_index = index + 1
                    if next_index < length:
                        buffer.append(tuple_text[next_index])
                        index += 2
                        continue
                buffer.append(current)
                index += 1
            values.append("".join(buffer))
        else:
            start = index
            while index < length and tuple_text[index] != ",":
                index += 1
            token = tuple_text[start:index].strip()
            upper = token.upper()
            if not token:
                values.append(None)
            elif upper == "NULL":
                values.append(None)
            elif upper in {"TRUE", "FALSE"}:
                values.append(upper == "TRUE")
            else:
                if NUMBER_REGEX.match(token):
                    if "." in token:
                        try:
                            values.append(float(token))
                        except ValueError:
                            values.append(token)
                    else:
                        try:
                            values.append(int(token))
                        except ValueError:
                            values.append(token)
                else:
                    values.append(token)
        while index < length and tuple_text[index].isspace():
            index += 1
        if index < length and tuple_text[index] == ",":
            index += 1

    return values


def _split_column_block(block: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    in_string: Optional[str] = None
    index = 0
    length = len(block)

    while index < length:
        char = block[index]

        if in_string:
            if char == "\\":
                current.append(char)
                if index + 1 < length:
                    current.append(block[index + 1])
                    index += 2
                    continue
                index += 1
                continue

            if char == in_string:
                if char == "'" and index + 1 < length and block[index + 1] == "'":
                    current.append(char)
                    current.append(block[index + 1])
                    index += 2
                    continue
                in_string = None

            current.append(char)
            index += 1
            continue

        if char in ("'", '"'):
            in_string = char
            current.append(char)
            index += 1
            continue

        if char == "(":
            depth += 1
            current.append(char)
            index += 1
            continue

        if char == ")":
            if depth > 0:
                depth -= 1
            current.append(char)
            index += 1
            continue

        if char == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            index += 1
            continue

        current.append(char)
        index += 1

    tail = "".join(current).strip()
    if tail:
        parts.append(tail)

    return parts


def _extract_parenthesized_block(text: str, start_index: int) -> Tuple[str, int]:
    depth = 0
    in_string: Optional[str] = None
    escape = False
    buffer: List[str] = []

    for index in range(start_index, len(text)):
        char = text[index]
        buffer.append(char)

        if in_string:
            if escape:
                escape = False
                continue

            if char == "\\":
                escape = True
                continue

            if char == in_string:
                if char == "'" and index + 1 < len(text) and text[index + 1] == "'":
                    buffer.append("'")
                    continue
                in_string = None
            continue

        if char in ("'", '"'):
            in_string = char
            continue

        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return "".join(buffer), index + 1

    raise SQLParseError("CREATE TABLE 定义缺少右括号")


def _extract_table_columns(sql_text: str) -> Dict[str, List[str]]:
    columns_map: Dict[str, List[str]] = {}
    position = 0
    reserved_prefixes = ("primary", "unique", "key", "constraint", "foreign", "index", "fulltext")

    while True:
        match = CREATE_TABLE_REGEX.search(sql_text, position)
        if not match:
            break

        table = match.group("table")
        block, end_index = _extract_parenthesized_block(sql_text, match.end() - 1)
        inner = block[1:-1]
        definitions = _split_column_block(inner)
        collected: List[str] = []

        for definition in definitions:
            stripped = definition.strip()
            if not stripped:
                continue
            lower = stripped.lstrip("`\"").lower()
            if lower.startswith(reserved_prefixes):
                continue

            name_match = COLUMN_NAME_REGEX.match(stripped)
            if name_match:
                collected.append(name_match.group("name"))

        if collected:
            columns_map[table.lower()] = collected

        position = end_index

    return columns_map


def _normalize_columns(
    raw_columns: Optional[str],
    value_count: int,
    *,
    fallback: Optional[Sequence[str]] = None,
    table: Optional[str] = None,
) -> List[str]:
    if raw_columns:
        inner = raw_columns.strip()[1:-1]
        columns = [col.strip().strip("`\"") for col in inner.split(",")]
        return [column for column in columns if column]

    if fallback and len(fallback) == value_count:
        return list(fallback)

    if fallback and table:
        LOGGER.warning(
            "表 %s 的列定义数量 (%s) 与数据数量 (%s) 不一致，已使用 col_x 占位列",
            table,
            len(fallback),
            value_count,
        )

    return [f"col_{idx}" for idx in range(value_count)]


def iter_insert_statements(
    sql_text: str,
    *,
    column_definitions: Optional[Dict[str, Sequence[str]]] = None,
) -> Iterator[InsertStatement]:
    for match in INSERT_REGEX.finditer(sql_text):
        table = match.group("table")
        raw_columns = match.group("columns")
        values_block = match.group("values")
        try:
            for tuple_text in _split_value_tuples(values_block):
                parsed_values = _parse_value_tuple(tuple_text)
                fallback = None
                if column_definitions:
                    fallback = column_definitions.get(table.lower())
                columns = _normalize_columns(
                    raw_columns,
                    len(parsed_values),
                    fallback=fallback,
                    table=table,
                )
                if len(columns) != len(parsed_values):
                    LOGGER.warning(
                        "列数量与数据数量不一致 (table=%s): %s vs %s", table, len(columns), len(parsed_values)
                    )
                    continue
                yield InsertStatement(table=table, columns=columns, values=parsed_values)
        except SQLParseError as exc:
            LOGGER.warning("解析 INSERT 语句失败 (table=%s): %s", table, exc)
            continue


def _determine_id(columns: Sequence[str], row: dict, table: str, fallback_counter: int) -> str:
    preferred = {"id", "case_id", "caseid", "doc_id", "document_id"}
    for column in columns:
        if column.lower() in preferred:
            value = row.get(column)
            if value is not None and value != "":
                return str(value)
    return f"{table}-{fallback_counter}"


def convert_zip_to_jsonl(
    zip_path: str,
    output_path: str,
    *,
    index_name: Optional[str] = "cases",
    include_tables: Optional[Sequence[str]] = None,
    decode_encodings: Optional[Sequence[str]] = None,
) -> Tuple[int, Counter]:
    if decode_encodings is None:
        decode_encodings = ("utf-8", "utf-8-sig", "gb18030", "latin-1")

    allowed_tables = {table.lower() for table in include_tables} if include_tables else None
    stats: Counter = Counter()
    written = 0

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with ZipFile(zip_path, "r") as archive, open(output_path, "w", encoding="utf-8") as handle:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            if not entry.filename.lower().endswith(".sql"):
                continue

            raw_text = _decode_bytes(archive.read(entry), decode_encodings)
            LOGGER.info("正在解析 SQL 文件: %s", entry.filename)
            column_map = _extract_table_columns(raw_text)

            for statement in iter_insert_statements(
                raw_text,
                column_definitions=column_map,
            ):
                table_lower = statement.table.lower()
                if allowed_tables and table_lower not in allowed_tables:
                    continue

                row = dict(zip(statement.columns, statement.values))
                stats[statement.table] += 1
                doc_id = _determine_id(statement.columns, row, statement.table, stats[statement.table])
                record = {"_source": row, "_id": doc_id}
                if index_name:
                    record["_index"] = index_name
                handle.write(json.dumps(record, ensure_ascii=False))
                handle.write("\n")
                written += 1

    return written, stats


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 SQL dump 转换为 OpenSearch JSONL 数据")
    parser.add_argument("--zip", required=True, help="包含 SQL 文件的压缩包，例如 case_recovery.zip")
    parser.add_argument("--output", "-o", required=True, help="输出 JSONL 文件路径")
    parser.add_argument("--index", "-i", default="cases", help="写入记录时使用的 _index 值；留空表示不写入")
    parser.add_argument(
        "--tables",
        nargs="*",
        help="仅转换指定的表名（不区分大小写）；若未指定则转换所有表",
    )
    parser.add_argument(
        "--encoding",
        nargs="*",
        default=["utf-8", "utf-8-sig", "gb18030", "latin-1"],
        help="按优先顺序尝试的文本编码",
    )
    parser.add_argument("--verbose", "-v", action="count", default=0, help="输出更详细的日志")
    return parser.parse_args(argv)


def configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity == 1:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    if not os.path.exists(args.zip):
        LOGGER.error("压缩包不存在: %s", args.zip)
        return 1

    try:
        total, stats = convert_zip_to_jsonl(
            args.zip,
            args.output,
            index_name=(args.index or None),
            include_tables=args.tables,
            decode_encodings=args.encoding,
        )
    except Exception as exc:  # pragma: no cover - 运行时异常统一兜底
        LOGGER.error("转换失败: %s", exc)
        return 1

    if total == 0:
        LOGGER.warning("未找到可转换的数据，请检查表名或 SQL 文件内容")
    else:
        LOGGER.info("成功写入 %s 条记录", total)
        for table, count in stats.items():
            LOGGER.info("  表 %s: %s 条", table, count)

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI 入口
    sys.exit(main())
