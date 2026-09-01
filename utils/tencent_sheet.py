"""从公开的腾讯在线表格读取投票候选项。"""
import base64
import html
import json
import logging
import re
import threading
import zlib
from collections.abc import Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from config import (
    TENCENT_ADVENTURE_TAB,
    TENCENT_SHEET_URL,
    TENCENT_TECHNOLOGY_TAB,
)


_log = logging.getLogger("mlcbot")
_CALLBACK_PATTERN = re.compile(r"clientVarsCallback\((.*)\)\s*", re.DOTALL)
_OPENDOC_PATTERN = re.compile(
    r'href="(?P<url>//docs\.qq\.com/dop-api/opendoc[^"]+)"'
)
_KNOWN_METADATA = frozenset(
    {
        "3.0.0",
        "Calibri",
        "Calibri Light",
        "Microsoft YaHei",
        "Arial",
        "Times New Roman",
        "Tahoma",
        "宋体",
        "新細明體",
        "常规",
    }
)
_HEX_COLOR_PATTERN = re.compile(r"[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?")
_cache: dict[str, tuple[str, ...]] = {}
_cache_lock = threading.Lock()


class TencentSheetError(RuntimeError):
    """腾讯表格无法读取或格式不符合预期。"""


def _url_for_tab(url: str, tab_id: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["tab"] = tab_id
    query.pop("scode", None)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _read_varint(data: bytes, position: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while position < len(data) and shift < 70:
        byte = data[position]
        position += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, position
        shift += 7
    raise ValueError("invalid varint")


def _protobuf_text_values(data: bytes, depth: int = 0) -> Iterator[str]:
    """递归提取 protobuf 长度字段中的 UTF-8 文本，不依赖私有 schema。"""
    if depth > 12:
        return

    position = 0
    while position < len(data):
        try:
            key, position = _read_varint(data, position)
        except ValueError:
            return
        wire_type = key & 0x07
        if key == 0:
            return
        if wire_type == 0:
            try:
                _, position = _read_varint(data, position)
            except ValueError:
                return
        elif wire_type == 1:
            position += 8
        elif wire_type == 2:
            try:
                length, position = _read_varint(data, position)
            except ValueError:
                return
            end = position + length
            if end > len(data):
                return
            value = data[position:end]
            position = end
            try:
                decoded = value.decode("utf-8")
            except UnicodeDecodeError:
                decoded = ""
            if decoded and all(
                character.isprintable() or character in "\r\n\t"
                for character in decoded
            ):
                yield decoded
            yield from _protobuf_text_values(value, depth + 1)
        elif wire_type == 5:
            position += 4
        else:
            return
        if position > len(data):
            return


def _clean_cell_text(value: str) -> str:
    return " ".join(value.replace("\x00", "").split()).strip()


def _extract_candidates(
    related_sheet: bytes,
    *,
    sheet_id: str,
    sheet_name: str,
    header_rows: int = 1,
) -> tuple[str, ...]:
    texts: list[str] = []
    for raw_value in _protobuf_text_values(related_sheet):
        value = _clean_cell_text(raw_value)
        if not value or len(value) > 100:
            continue
        if value in {sheet_id, sheet_name} or value in _KNOWN_METADATA:
            continue
        if _HEX_COLOR_PATTERN.fullmatch(value):
            continue
        if value not in texts:
            texts.append(value)

    if len(texts) <= header_rows:
        raise TencentSheetError(f"子表 {sheet_name} 未读取到候选项")
    return tuple(texts[header_rows:])


def _parse_sheet_response(
    response_text: str,
    *,
    sheet_id: str,
) -> tuple[str, tuple[str, ...]]:
    match = _CALLBACK_PATTERN.fullmatch(response_text.strip())
    if not match:
        raise TencentSheetError("腾讯表格数据响应格式异常")
    try:
        payload = json.loads(match.group(1))
        client_vars = payload["clientVars"]
        collab_vars = client_vars["collab_client_vars"]
        attributed_text = collab_vars["initialAttributedText"]["text"][0]
        block_datas = attributed_text["block_datas"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise TencentSheetError("腾讯表格响应缺少工作表数据") from exc

    sheet_name = sheet_id
    for header in client_vars.get("header", []):
        for sheet in header.get("d", []):
            if sheet.get("id") == sheet_id:
                sheet_name = str(sheet.get("name") or sheet_id)
                break
    if sheet_name == sheet_id:
        workbook = attributed_text.get("workbook", "")
        try:
            workbook_data = zlib.decompress(base64.b64decode(workbook))
            names = tuple(_protobuf_text_values(workbook_data))
            index = names.index(sheet_id)
            sheet_name = _clean_cell_text(names[index + 1]) or sheet_id
        except (ValueError, IndexError, TypeError, zlib.error):
            pass

    for block in block_datas:
        encoded = block.get("related_sheet")
        if not encoded:
            continue
        try:
            related_sheet = zlib.decompress(base64.b64decode(encoded))
        except (ValueError, TypeError, zlib.error) as exc:
            raise TencentSheetError("腾讯表格工作表数据解压失败") from exc
        candidates = _extract_candidates(
            related_sheet,
            sheet_id=sheet_id,
            sheet_name=sheet_name,
        )
        if candidates:
            return sheet_name, candidates
    raise TencentSheetError(f"子表 {sheet_name} 没有数据块")


def _fetch_tab(tab_id: str, *, timeout: float = 15.0) -> tuple[str, ...]:
    tab_url = _url_for_tab(TENCENT_SHEET_URL, tab_id)
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0", "Referer": tab_url}
    try:
        page = session.get(tab_url, headers=headers, timeout=timeout)
        page.raise_for_status()
        match = _OPENDOC_PATTERN.search(page.text)
        if not match:
            raise TencentSheetError("腾讯表格页面缺少数据地址")
        data_url = "https:" + html.unescape(match.group("url"))
        response = session.get(data_url, headers=headers, timeout=timeout)
        response.raise_for_status()
        _, candidates = _parse_sheet_response(response.text, sheet_id=tab_id)
    except requests.RequestException as exc:
        raise TencentSheetError("腾讯表格网络请求失败") from exc

    with _cache_lock:
        _cache[tab_id] = candidates
    return candidates


def _fetch_tab_with_fallback(tab_id: str) -> tuple[str, ...]:
    try:
        return _fetch_tab(tab_id)
    except TencentSheetError:
        with _cache_lock:
            cached = _cache.get(tab_id)
        if cached is None:
            raise
        _log.warning("腾讯表格读取失败，使用子表 %s 的最近缓存", tab_id)
        return cached


def fetch_poll_candidates(category: str) -> tuple[str, ...]:
    """按类别读取候选项；混合类别会按表格顺序合并并去重。"""
    if category == "adventure":
        return _fetch_tab_with_fallback(TENCENT_ADVENTURE_TAB)
    if category == "technology":
        return _fetch_tab_with_fallback(TENCENT_TECHNOLOGY_TAB)
    if category != "mixed":
        raise TencentSheetError("未知投票类别")

    combined = (
        *_fetch_tab_with_fallback(TENCENT_TECHNOLOGY_TAB),
        *_fetch_tab_with_fallback(TENCENT_ADVENTURE_TAB),
    )
    return tuple(dict.fromkeys(combined))
