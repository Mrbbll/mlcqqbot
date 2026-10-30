"""验证顺序搜索、LLM 筛选后的正文提取、网络边界及真实 Agent 接入。"""

import base64
import json
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

from features.agent import service
from features.agent.tools import execute_tool, visible_tools
from features.agent.tools.common import ToolContext
from features.agent.tools import web_search as web


def tool_call(name, arguments, call_id="web-call"):
    """构造真实工具入口和模型循环都能使用的调用。"""
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def search_item(url="https://example.org/article", title="官方说明"):
    """模拟 DDGS 文本结果，保持官方返回字段名称。"""
    return {"title": title, "href": url, "body": "这是目录摘要，不是全文。"}


class WebSearchTests(unittest.IsolatedAsyncioTestCase):
    """以第三方库替身和实际 Trafilatura 检查完整搜索链路。"""

    def setUp(self):
        """准备普通用户上下文，不允许测试调用真实网络。"""
        self.context = ToolContext(user_id="reader")
        self.enterContext(patch.object(web, "AGENT_WEB_SEARCH_BACKENDS", ["bing", "wikipedia"]))
        self.enterContext(patch.object(web, "AGENT_WEB_SEARCH_TIMEOUT_SECONDS", 10))
        self.enterContext(patch.object(web, "AGENT_WEB_SEARCH_PROXY", ""))
        self.original_download = web._download_html
        self.original_search_backend = web._search_backend
        self.backend = self.enterContext(patch.object(web, "_search_backend"))
        self.download = self.enterContext(patch.object(web, "_download_html"))
        self.enterContext(patch("features.security.permissions.check_superuser", return_value=False))

    def search(self):
        """通过注册表校验模型关键词并执行实际搜索处理器。"""
        return execute_tool(tool_call("search_web", {"queries": ["官方用法", "使用示例"]}), self.context)

    def test_sequential_search_deduplicates_and_retains_partial_results(self):
        """某关键词失败时保留其他关键词的去重目录，且调用顺序与模型规划一致。"""
        self.backend.side_effect = [
            [search_item(), search_item("https://example.org/article#section")], RuntimeError("engine unavailable")]
        result = self.search()
        self.assertTrue(result.ok)
        self.assertTrue(result.data["partial"])
        self.assertEqual([call.args[0] for call in self.backend.call_args_list], ["官方用法", "使用示例"])
        self.assertEqual(len(result.data["items"]), 1)
        self.assertEqual(self.context.web_search_results["web-1"]["url"], "https://example.org/article")
        self.download.assert_not_called()

    def test_arguments_empty_search_and_request_isolation(self):
        """拒绝无效规划与跨请求编号，空目录不能被当作搜索成功。"""
        for queries in (["只有一个"], ["重复", "重复"], ["a" * 201, "b"], [" ", "b"]):
            self.assertFalse(execute_tool(tool_call("search_web", {"queries": queries}), self.context).ok)
        self.backend.return_value = []
        self.assertEqual(self.search().code, "search_empty")
        self.backend.return_value = [search_item()]
        self.search()
        result = execute_tool(tool_call("extract_web_pages", {"result_ids": ["web-1"]}), ToolContext())
        self.assertEqual(result.code, "unknown_result")
        self.download.assert_not_called()

    def test_timeout_switches_backend_and_recovers(self):
        """首个后端超时后切换一次，恢复后仍继续处理下一个关键词。"""
        self.backend.side_effect = [TimeoutException("timeout"), [search_item()], [search_item()]]
        result = self.search()
        self.assertTrue(result.ok)
        self.assertFalse(result.data["failures"])
        calls = self.backend.call_args_list
        self.assertEqual([call.kwargs["backend"] for call in calls], ["bing", "wikipedia", "bing"])
        self.assertEqual([call.args[0] for call in calls], ["官方用法", "官方用法", "使用示例"])
        self.assertEqual(self.backend.call_args_list[0].kwargs["timeout"], 10)

    def test_exhausted_retries_classify_errors_and_hide_proxy_credentials(self):
        """超时与限流各自分类；只重试一次，日志不输出异常正文或代理凭证。"""
        proxy = "http://user:private-password@127.0.0.1:7890"
        self.backend.side_effect = [TimeoutException(proxy), TimeoutException(proxy), RatelimitException(proxy), RatelimitException(proxy)]
        with patch.object(web, "AGENT_WEB_SEARCH_PROXY", proxy), self.assertLogs("mlcbot", level="WARNING") as logs:
            result = self.search()
        self.assertEqual(result.code, "search_unavailable")
        self.assertTrue(result.retryable)
        self.assertEqual([item["code"] for item in result.data["failures"]], ["timeout", "rate_limited"])
        self.assertEqual(self.backend.call_count, 4)
        self.assertEqual(self.backend.call_args.kwargs["proxy"], proxy)
        self.assertNotIn("private-password", str(logs.output) + result.to_json())
        self.assertIn("backend=wikipedia attempt=2", str(logs.output))

    def test_slow_query_reserves_time_for_next_keyword(self):
        """首个查询耗完分配预算后不再重试，剩余时间留给下一个关键词。"""
        clock = [0.0]
        self.context.timeout_seconds = 8

        def engine(*args, **kwargs):
            """模拟首个后端消耗当前关键词全部预算。"""
            if clock[0] == 0:
                clock[0] = 4.0
                raise TimeoutException("timeout")
            return [search_item()]

        self.backend.side_effect = engine
        with patch.object(web.time, "monotonic", side_effect=lambda: clock[0]):
            result = self.search()
        self.assertTrue(result.ok)
        self.assertEqual(self.backend.call_count, 2)
        self.assertEqual(result.data["failures"][0]["code"], "timeout")
        self.assertEqual([call.kwargs["timeout"] for call in self.backend.call_args_list], [2, 2])

    def test_insufficient_budget_does_not_start_network(self):
        """总预算不足一秒时不启动至少一秒的请求，不把失败当作无匹配结果。"""
        self.context.timeout_seconds = 0.1
        result = self.search()
        self.assertEqual(result.code, "search_unavailable")
        self.assertTrue(all(item["code"] == "timeout" for item in result.data["failures"]))
        self.backend.assert_not_called()

    def test_bing_routes_to_china_and_wikipedia_stays_on_ddgs(self):
        """bing 显式走中国版，Wikipedia 继续使用 DDGS，代理和超时均传递。"""
        with patch("features.agent.tools.web_search.bing_china.search_bing_china", return_value=[search_item()]) as china, patch("ddgs.DDGS") as ddgs:
            self.original_search_backend("问题", timeout=10, proxy="http://localhost:7890", backend="bing")
            china.assert_called_once_with("问题", timeout=10, proxy="http://localhost:7890")
            ddgs.assert_not_called()
            self.original_search_backend("问题", timeout=10, proxy=None, backend="wikipedia")
            ddgs.return_value.text.assert_called_once_with("问题", max_results=3, backend="wikipedia")

    def test_china_request_parameters_and_real_html_parser(self):
        """实际解析必应样式 HTML 并解码跳转网址，请求明确带中国地区参数。"""
        from features.agent.tools.web_search.bing_china import search_bing_china
        encoded = base64.urlsafe_b64encode(b"https://example.org/article").decode()
        html = f'<html><ol><li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u=a1{encoded}">官方说明</a></h2><p>中文摘要</p></li></ol></html>'
        with patch("ddgs.base.HttpClient") as client:
            client.return_value.request.return_value = SimpleNamespace(status_code=200, text=html)
            items = search_bing_china("使用示例", timeout=10, proxy=None)
        request = client.return_value.request.call_args
        self.assertEqual(request.args, ("GET", "https://cn.bing.com/search"))
        self.assertEqual(request.kwargs["params"]["mkt"], "zh-CN")
        self.assertEqual(request.kwargs["params"]["cc"], "CN")
        self.assertEqual(request.kwargs["params"]["ensearch"], "0")
        self.assertEqual(items, [{"title": "官方说明", "href": "https://example.org/article", "body": "中文摘要"}])
        client.assert_called_once_with(timeout=10, proxy=None, verify=True)

    def test_china_verification_page_is_a_backend_failure(self):
        """站点验证页面不能被误当作搜索结果，异常可触发既有备用后端逻辑。"""
        from features.agent.tools.web_search.bing_china import search_bing_china
        with patch("ddgs.base.HttpClient") as client:
            client.return_value.request.return_value = SimpleNamespace(status_code=200, text="<html><p>请完成验证</p></html>")
            with self.assertRaises(DDGSException):
                search_bing_china("使用示例", timeout=10, proxy=None)

    def test_china_alternate_title_structure(self):
        """复现 26.3 查询返回 div.b_algoheader 而非 h2 时丢失全部结果的问题。"""
        from features.agent.tools.web_search.bing_china import search_bing_china
        html = '<html><li class="b_algo"><div class="b_tpcn"><a href="https://example.org/">站点</a></div><div class="b_algoheader"><a href="https://example.org/mc"><strong>26.3</strong> 更新日志</a></div><div class="b_caption"><p>更新内容</p></div></li></html>'
        with patch("ddgs.base.HttpClient") as client:
            client.return_value.request.return_value = SimpleNamespace(status_code=200, text=html)
            items = search_bing_china("Minecraft 26.3 更新日志", timeout=10, proxy=None)
        self.assertEqual(items, [{"title": "26.3 更新日志", "href": "https://example.org/mc", "body": "更新内容"}])

    def test_china_failure_reasons_are_specific_and_sanitized(self):
        """HTTP、空响应、验证、解析变化与 TLS 故障有独立原因码。"""
        from features.agent.tools.web_search.bing_china import BingChinaError, search_bing_china
        cases = [(429, "rate limited", "rate_limited"), (403, "forbidden", "http_error"),
                 (200, "", "empty_response"), (200, '<html><div id="b_captcha">验证</div></html>', "verification_required"),
                 (200, '<html><li class="b_algo"><h4>新结构</h4></li></html>', "parse_mismatch"),
                 (200, '<html><li class="b_no">无匹配</li></html>', "no_results"),
                 (200, "<html>unexpected</html>", "unexpected_page")]
        for status, html, reason in cases:
            with self.subTest(reason=reason), patch("ddgs.base.HttpClient") as client:
                client.return_value.request.return_value = SimpleNamespace(status_code=status, text=html)
                with self.assertRaises(BingChinaError) as caught:
                    search_bing_china("问题", timeout=10, proxy=None)
                self.assertEqual(caught.exception.reason, reason)
                self.assertEqual(caught.exception.diagnostics["http_status"], status)
                self.assertEqual(caught.exception.diagnostics["response_chars"], len(html))
        with patch("ddgs.base.HttpClient") as client:
            client.return_value.request.side_effect = DDGSException("TLS error http://user:private-password@proxy")
            with self.assertRaises(BingChinaError) as caught:
                search_bing_china("问题", timeout=10, proxy=None)
        self.assertEqual(str(caught.exception), "tls_error")

    def test_china_diagnostics_survive_backend_fallback(self):
        """具体原因进入日志和失败结果，且不妨碍使用 Wikipedia 备用结果。"""
        from features.agent.tools.web_search.bing_china import BingChinaError
        error = BingChinaError("parse_mismatch", {"http_status": 200, "response_chars": 60000, "result_blocks": 5})
        self.backend.side_effect = [error, TimeoutException("timeout"), [search_item()]]
        with self.assertLogs("mlcbot", level="WARNING") as logs:
            result = self.search()
        self.assertTrue(result.ok)
        attempt = result.data["failures"][0]["attempts"][0]
        self.assertEqual(attempt["reason"], "parse_mismatch")
        self.assertEqual(attempt["result_blocks"], 5)
        self.assertIn("reason=parse_mismatch http_status=200 response_chars=60000 result_blocks=5", str(logs.output))

    def test_real_trafilatura_extracts_selected_page_and_retains_source(self):
        """真实正文提取排除目录摘要，且仅下载模型选定的来源。"""
        self.backend.side_effect = [[search_item()], [search_item("https://example.org/other")]]
        self.search()
        body = "网络搜索先生成关键词，再筛选相关来源，最后提取正文并附上来源网址。" * 30
        self.download.return_value = (f"<html><body><article><h1>搜索说明</h1><p>{body}</p></article></body></html>".encode(), "https://example.org/other")
        result = execute_tool(tool_call("extract_web_pages", {"result_ids": ["web-2"]}), self.context)
        self.assertTrue(result.ok)
        self.assertEqual(self.download.call_args.args[0], "https://example.org/other")
        self.assertEqual(result.data["pages"][0]["id"], "web-2")
        self.assertIn("最后提取正文", result.data["pages"][0]["text"])
        self.assertNotIn("目录摘要", result.data["pages"][0]["text"])

    def test_extraction_partial_failure_and_length_limits(self):
        """单页失败保留已读取来源，长正文必须有截断标记。"""
        self.context.web_search_results = {f"web-{i}": {"title": "说明", "url": f"https://example.org/{i}"} for i in range(1, 4)}
        self.download.side_effect = [(b"html", "https://example.org/1"), web.requests.Timeout("test timeout"), (b"html", "https://example.org/3")]
        with patch("trafilatura.extract", side_effect=["正文" * 2000, None]):
            result = web.extract_web_pages(web.ExtractWebPagesArgs(result_ids=["web-1", "web-2", "web-3"]), self.context)
        self.assertTrue(result.ok)
        self.assertTrue(result.truncated)
        self.assertEqual(len(result.data["pages"][0]["text"]), web.MAX_TEXT_CHARS)
        self.assertEqual([item["code"] for item in result.data["failures"]], ["timeout", "empty_content"])
        self.assertLessEqual(len(result.to_json()), 8000)

    def test_public_url_validation(self):
        """非 HTTP、内网、混合 DNS 和带凭证的地址均不可访问。"""
        for url in ("file:///etc/passwd", "https://user:pass@example.org", "http://example.org:22"):
            with self.assertRaises(ValueError):
                web._normalize_url(url)
        for addresses in (["127.0.0.1"], ["::1"], ["169.254.169.254"], ["8.8.8.8", "10.0.0.1"]):
            answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]
            with patch.object(web.socket, "getaddrinfo", return_value=answers), self.assertRaises(ValueError):
                web._validate_public_url("https://example.org")

    def test_download_validates_redirects_and_bounds_response(self):
        """真实下载路径逐跳检查目的地址、禁止自动跳转并限制响应体大小。"""
        with patch.object(web, "_download_html", wraps=self.original_download), \
             patch.object(web.requests, "Session") as session, \
             patch.object(web, "_validate_public_url", side_effect=[None, ValueError("private address")]) as validate:
            response = session.return_value.__enter__.return_value.get.return_value.__enter__.return_value
            response.is_redirect = True
            response.headers = {"Location": "http://127.0.0.1/admin"}
            with self.assertRaises(ValueError):
                web._download_html("https://example.org", web.time.monotonic() + 30)
            self.assertEqual(validate.call_args.args[0], "http://127.0.0.1/admin")
            client = session.return_value.__enter__.return_value
            self.assertFalse(client.get.call_args.kwargs["allow_redirects"])
            response.is_redirect = response.is_permanent_redirect = False
            response.headers = {"Content-Type": "text/html"}
            response.iter_content.return_value = [b"a" * (web.MAX_HTML_BYTES + 1)]
            validate.side_effect = None
            with self.assertRaises(ValueError):
                web._download_html("https://example.org", web.time.monotonic() + 30)

    async def test_agent_reads_directory_before_selected_extraction(self):
        """真实 Agent 循环先把目录交回 LLM，再执行其筛选，并将正文交回生成回答。"""
        self.backend.return_value = [search_item()]
        self.download.return_value = (b"html", "https://example.org/article")
        snapshots = []

        async def model(conversation, **kwargs):
            """记录每轮模型实际收到的数据，并模拟规划和筛选。"""
            snapshots.append(json.loads(json.dumps(conversation)))
            if len(snapshots) == 1:
                return {"tool_calls": [tool_call("search_web", {"queries": ["官方说明", "用法示例"]})]}
            if len(snapshots) == 2:
                return {"tool_calls": [tool_call("extract_web_pages", {"result_ids": ["web-1"]}, "extract-call")]}
            return {"content": "来自正文的答案 https://example.org/article"}

        with patch.object(service, "AGENT_API_URL", "fake"), patch.object(service, "AGENT_API_KEY", "fake"), \
             patch.object(service, "AGENT_MODEL", "fake"), patch.object(service, "_ask_model", side_effect=model), \
             patch.object(service, "record_tool_call"), patch("trafilatura.extract", return_value="真实正文"):
            reply = await service.handle_agent("请联网查询", "reader", group_id="web-test")
        self.assertIn("来自正文的答案", reply)
        self.assertIn('"items"', snapshots[1][-1]["content"])
        self.assertNotIn('"pages"', snapshots[1][-1]["content"])
        self.assertIn("真实正文", snapshots[2][-1]["content"])
        names = {item["function"]["name"] for item in visible_tools("reader")}
        self.assertTrue({"search_web", "extract_web_pages"} <= names)
