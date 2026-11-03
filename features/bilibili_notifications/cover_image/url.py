"""规范化可安全用于开播通知 Markdown 图片的 Bilibili 封面地址。"""

from urllib.parse import quote, urlsplit, urlunsplit


def normalize_room_cover_url(url: str) -> str:
    """仅接受 Bilibili 图片 CDN 地址，并转换为 Markdown 可用的 HTTPS URL。"""
    try:
        parsed_url = urlsplit(str(url or "").strip())
        hostname = (parsed_url.hostname or "").casefold()
        port = parsed_url.port
    except ValueError:
        return ""
    if (
        parsed_url.scheme.casefold() not in {"http", "https"}
        or not hostname.endswith(".hdslb.com")
        or parsed_url.username is not None
        or parsed_url.password is not None
        or port not in (None, 443)
    ):
        return ""

    path = quote(parsed_url.path, safe="/%:@!$&'*,;=-._~")
    query = quote(parsed_url.query, safe="=&?/%:@!$'*,;+-._~")
    return urlunsplit(("https", parsed_url.netloc, path, query, ""))
