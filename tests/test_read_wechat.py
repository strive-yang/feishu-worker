"""Synthetic in-memory pages only; no real article cache or network access."""

from email.message import Message
import gzip
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import zlib


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "read_wechat", ROOT / ".agents/skills/feishu-wechat-knowledge/scripts/read_wechat.py")
wechat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wechat)
URL = "https://mp.weixin.qq.com/s/fixture"
PAGE = '''<html><head><meta property="og:title" content="测试技术文章">
<meta name="author" content="测试作者"></head><body>
<h1 id="activity-name">测试技术文章</h1><a id="js_name">测试公众号</a>
<div id="js_content"><p>第一段 &amp; 技术。</p><section><p>第二段。</p></section>
<script>do_not_include()</script><style>do_not_include</style>
<img data-src="https://example.invalid/diagram.png" alt="测试图">
<a href="https://example.invalid/paper">参考资料</a>
<a href="javascript:alert(1)">不可执行</a></div>
<p>do_not_include_footer</p><script>var ct = "1700000000";</script></body></html>'''


class Response:
    def __init__(self, body, compression="", final_url=URL):
        self.body = body
        self.status = 200
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"
        self.headers["Content-Encoding"] = compression
        self.final_url = final_url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.body[:size]

    def geturl(self):
        return self.final_url


class WeChatTests(unittest.TestCase):
    def test_article_metadata_body_images_and_links(self):
        article = wechat.parse_article(PAGE, URL)
        self.assertEqual(article["state"], "parsed")
        self.assertEqual(article["original_url"], URL)
        self.assertEqual(article["title"], "测试技术文章")
        self.assertEqual(article["publisher"], "测试公众号")
        self.assertEqual(article["author"], "测试作者")
        self.assertTrue(article["published_at"].endswith("+08:00"))
        self.assertIn("第一段 & 技术。", article["body"])
        self.assertNotIn("do_not_include", article["body"])
        self.assertEqual(len(article["images"]), 1)
        self.assertEqual(article["images"][0]["alt"], "测试图")
        self.assertEqual(article["links"], ["https://example.invalid/paper"])

    def test_verification_missing_body_incomplete_and_title_mismatch(self):
        cases = [
            ("<p>环境异常，请去验证</p>", "access_verification_required"),
            ("<p>ordinary page</p>", "body_not_found"),
            ('<div id="js_content">body</div>', "incomplete_article"),
            (PAGE.replace('content="测试技术文章"', 'content="另一个标题"'), "title_mismatch"),
        ]
        for page, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(wechat.parse_article(page, URL)["state"], expected)

    def test_missing_time_is_not_invented(self):
        article = wechat.parse_article(PAGE.replace('var ct = "1700000000";', ""), URL)
        self.assertIsNone(article["published_at"])
        self.assertIsNone(article["published_at_source"])

    def test_url_boundary(self):
        for url in (URL, "https://mp.weixin.qq.com/s?__biz=fixture&mid=1&idx=1&sn=fixture"):
            self.assertTrue(wechat.allowed_url(url))
        for url in ("http://mp.weixin.qq.com/s/x", "https://example.invalid/s/x",
                    "https://mp.weixin.qq.com.evil.invalid/s/x", "https://mp.weixin.qq.com/",
                    "https://user@mp.weixin.qq.com/s/x", "https://mp.weixin.qq.com:444/s/x",
                    "https://mp.weixin.qq.com:bad/s/x", "file:///s/x"):
            with self.subTest(url=url):
                self.assertFalse(wechat.allowed_url(url))

    def test_invalid_url_does_not_make_a_request(self):
        with patch.object(wechat, "build_opener") as opener:
            self.assertEqual(wechat.read_article("https://example.invalid/s/x")["state"], "unsupported_url")
            opener.assert_not_called()

    def test_redirect_boundary(self):
        handler = wechat.WeChatRedirects()
        with self.assertRaises(ValueError):
            handler.redirect_request(None, None, 302, "", {}, "https://example.invalid/s/x")

    def test_utf8_gb18030_and_invalid_declared_charset(self):
        text = '<meta charset="gb18030">测试'
        page, charset = wechat.decode_page(text.encode("gb18030"), "invalid-charset")
        self.assertEqual(page, text)
        self.assertEqual(charset, "gb18030")
        self.assertEqual(wechat.decode_page("测试".encode())[0], "测试")

    def read_response(self, response):
        with patch.object(wechat, "build_opener") as opener:
            opener.return_value.open.return_value = response
            return wechat.read_article(URL)

    def test_plain_gzip_and_deflate_responses(self):
        raw = PAGE.encode()
        for compression, body in (("", raw), ("gzip", gzip.compress(raw)), ("deflate", zlib.compress(raw))):
            with self.subTest(compression=compression):
                article = self.read_response(Response(body, compression))
                self.assertEqual(article["state"], "parsed")
                self.assertEqual(article["http_status"], 200)

    def test_size_limit_compression_and_final_url(self):
        with patch.object(wechat, "MAX_BYTES", 32):
            self.assertEqual(self.read_response(Response(b"x" * 33))["state"], "page_too_large")
            compressed = gzip.compress(b"x" * 100)
            self.assertEqual(self.read_response(Response(compressed, "gzip"))["state"], "page_too_large")
        self.assertEqual(self.read_response(Response(b"x", "br"))["state"], "unsupported_encoding")
        self.assertEqual(self.read_response(Response(b"x", final_url="https://example.invalid/"))["state"],
                         "unsupported_redirect")

    def test_network_error_reports_type_not_response_contents(self):
        with patch.object(wechat, "build_opener") as opener:
            opener.return_value.open.side_effect = wechat.URLError("private-marker")
            result = wechat.read_article(URL)
        self.assertEqual(result["state"], "fetch_error")
        self.assertEqual(result["error_type"], "URLError")
        self.assertNotIn("private-marker", str(result))
