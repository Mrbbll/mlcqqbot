"""通过独立的中国版适配器复用 DDGS 的 Bing HTML 解析和链接解码。"""

from dataclasses import asdict

from ddgs.engines.bing import Bing
from ddgs.exceptions import DDGSException, TimeoutException


class BingChinaError(DDGSException):
    """仅携带固定原因码和数值诊断，不保存关键词、响应正文或代理凭证。"""

    def __init__(self, reason: str, diagnostics: dict | None = None):
        """初始化可安全写入日志的错误原因与页面统计。"""
        super().__init__(reason)
        self.reason = reason
        self.diagnostics = diagnostics or {}


class BingChina(Bing):
    """显式访问必应中国地区入口，不修改 DDGS 内置的禁用后端。"""

    name = "bing_cn"
    disabled = False
    search_url = "https://cn.bing.com/search"
    # 中国版会在 h2 与 div.b_algoheader 两种标题结构之间切换。
    _title_link = "(.//h2//a[@href] | .//*[contains(concat(' ', normalize-space(@class), ' '), ' b_algoheader ')]//a[@href])[1]"
    elements_xpath = {"title": f"{_title_link}//text()", "href": f"{_title_link}/@href", "body": ".//p//text()"}

    def __init__(self, *args, **kwargs):
        """初始化每次查询独立的页面统计，兼容直接调用解析方法。"""
        super().__init__(*args, **kwargs)
        self.diagnostics = {}

    def request(self, *args, **kwargs):
        """区分网络、HTTP 和空响应，保存脱敏统计供后续解析诊断使用。"""
        try:
            response = self.http_client.request(*args, **kwargs)
        except TimeoutException:
            raise
        except DDGSException as exc:
            # 仅将原始异常用于本地分类，绝不向日志或模型返回其正文。
            detail = str(exc).lower()
            reason = ("tls_error" if any(token in detail for token in ("tls", "certificate", "selectedunofferedkxgroup"))
                      else "dns_error" if any(token in detail for token in ("dns", "resolve host", "name resolution"))
                      else "connection_error")
            raise BingChinaError(reason) from None
        self.diagnostics = {"http_status": response.status_code, "response_chars": len(response.text or "")}
        if response.status_code != 200:
            raise BingChinaError("rate_limited" if response.status_code == 429 else "http_error", self.diagnostics)
        if not response.text or not response.text.strip():
            raise BingChinaError("empty_response", self.diagnostics)
        return response.text

    def extract_results(self, html_text):
        """解析两种结果标题结构，并区分验证、空结果和未知页面结构。"""
        tree = self.extract_tree(html_text)
        self.diagnostics["result_blocks"] = len(tree.xpath(self.items_xpath))
        results = super().extract_results(html_text)
        if any(item.title and item.href for item in results):
            return results
        if tree.xpath("//*[@id='b_captcha' or @id='b_captchaDiv' or @id='b_captcha_div'] | //form[contains(@action, '/turing/')] "):
            reason = "verification_required"
        elif self.diagnostics["result_blocks"]:
            reason = "parse_mismatch"
        elif tree.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' b_no ')]"):
            reason = "no_results"
        else:
            reason = "unexpected_page"
        raise BingChinaError(reason, self.diagnostics)

    def build_payload(self, query, region, safesearch, timelimit, page=1, **kwargs):
        """固定中文和中国地区参数，避免继承国际版的地区设置。"""
        return {"q": query, "mkt": "zh-CN", "cc": "CN", "setlang": "zh-hans",
                "ensearch": "0", "count": "3", "first": str((page - 1) * 10 + 1)}


def search_bing_china(query: str, timeout: int, proxy: str | None) -> list[dict]:
    """搜索中国版并规范化结果；无结果或验证页面交给现有备用后端处理。"""
    engine = BingChina(timeout=timeout, proxy=proxy)
    results = engine.search(query, region="cn-zh") or []
    items = [asdict(item) for item in results if item.title and item.href][:3]
    if not items:
        raise BingChinaError("no_usable_results", engine.diagnostics)
    return items
