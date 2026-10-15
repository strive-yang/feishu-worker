"""Read WeChat articles in memory; emit JSON to stdout without writing files."""

from __future__ import annotations

import argparse
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import gzip
import html
from html.parser import HTMLParser
import io
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zlib


MAX_BYTES = 20 * 1024 * 1024
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BREAK_TAGS = {"p", "section", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "pre", "blockquote"}
IGNORED_TAGS = {"script", "style", "noscript"}
TARGETS = {"js_content", "activity-name", "js_name", "publish_time"}


def clean_text(value: str) -> str:
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in value.replace("\xa0", " ").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


class ArticleParser(HTMLParser):
    def __init__(self, url: str):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.stack: list[str] = []
        self.active: dict[str, int] = {}
        self.parts = {key: [] for key in TARGETS}
        self.meta: dict[str, str] = {}
        self.images: list[dict] = []
        self.links: list[str] = []
        self.has_content = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in VOID_TAGS:
            self.stack.append(tag)
        if attrs.get("id") in TARGETS:
            key = attrs["id"]
            self.active[key] = len(self.stack)
            self.has_content |= key == "js_content"
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            if key and attrs.get("content"):
                self.meta[key] = attrs["content"]
        if "js_content" in self.active:
            if tag in BREAK_TAGS or tag == "br":
                self.parts["js_content"].append("\n")
            if tag == "img":
                source = attrs.get("data-src") or attrs.get("src")
                if source and urlparse(urljoin(self.url, source)).scheme in {"http", "https"}:
                    self.images.append({
                        "index": len(self.images) + 1,
                        "url": urljoin(self.url, source),
                        "alt": attrs.get("alt", ""),
                        "preceding_text": clean_text("".join(self.parts["js_content"])[-250:]),
                    })
            if tag == "a" and attrs.get("href"):
                target = urljoin(self.url, attrs["href"])
                if urlparse(target).scheme in {"http", "https"} and target not in self.links:
                    self.links.append(target)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if "js_content" in self.active and tag in BREAK_TAGS:
            self.parts["js_content"].append("\n")
        if tag in self.stack:
            position = len(self.stack) - 1 - self.stack[::-1].index(tag)
            self.active = {key: depth for key, depth in self.active.items() if depth <= position}
            del self.stack[position:]

    def handle_data(self, data):
        if not any(tag in IGNORED_TAGS for tag in self.stack):
            for key in self.active:
                self.parts[key].append(data)


def decode_js_literal(value: str) -> str:
    def replace(match):
        token = match.group(0)
        if token.startswith(("\\x", "\\u")):
            return chr(int(token[2:], 16))
        return {"\\n": "\n", "\\r": "\r", "\\t": "\t"}.get(token, token[1:])
    return html.unescape(re.sub(r"\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}|\\[nrt\\\"'/]", replace, value))


def decode_page(raw: bytes, declared_charset: str | None = None) -> tuple[str, str]:
    match = re.search(br"<meta[^>]+charset\s*=\s*[\"']?([\w-]+)", raw[:16384], re.I)
    candidates = [declared_charset, match.group(1).decode("ascii") if match else None, "utf-8", "gb18030"]
    for charset in candidates:
        if charset:
            try:
                return raw.decode(charset), charset
            except (UnicodeDecodeError, LookupError):
                pass
    return raw.decode("utf-8", errors="replace"), "utf-8-replacement"


def parse_article(page: str, url: str) -> dict:
    parser = ArticleParser(url)
    parser.feed(page)
    title = clean_text("".join(parser.parts["activity-name"])) or parser.meta.get("og:title")
    meta_title = parser.meta.get("og:title")
    publisher = clean_text("".join(parser.parts["js_name"]))
    if not publisher:
        match = re.search(r"\bvar\s+nickname\s*=\s*htmlDecode\(\s*(['\"])(.*?)\1\s*\)", page, re.S)
        publisher = decode_js_literal(match.group(2)) if match else None
    body = clean_text("".join(parser.parts["js_content"]))
    timestamp = None
    for field in ("ct", "create_time"):
        match = re.search(r"\bvar\s+" + field + r"\s*=\s*(['\"]?)(\d{10})\1(?:\s*\*\s*1)?\s*;", page)
        if match:
            timestamp = int(match.group(2))
            break
    published_at = datetime.fromtimestamp(timestamp, timezone(timedelta(hours=8))).isoformat() if timestamp else None
    title_matches = bool(title and meta_title and clean_text(title) == clean_text(meta_title))
    if not parser.has_content:
        state = "access_verification_required" if re.search(r"captcha|环境异常|去验证", page, re.I) else "body_not_found"
    elif not title or not body:
        state = "incomplete_article"
    elif meta_title and not title_matches:
        state = "title_mismatch"
    else:
        state = "parsed"
    return {
        "original_url": url,
        "state": state,
        "has_js_content": parser.has_content,
        "title": title,
        "meta_title": meta_title,
        "title_matches_meta": title_matches,
        "publisher": publisher,
        "author": parser.meta.get("author") or parser.meta.get("og:article:author"),
        "published_at": published_at,
        "published_at_source": "page_ct_or_create_time_unix_seconds" if timestamp else None,
        "body": body,
        "body_characters": len(body),
        "images": parser.images,
        "links": parser.links,
    }


def allowed_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (parsed.scheme == 'https' and parsed.hostname == 'mp.weixin.qq.com'
                and parsed.username is None and parsed.password is None
                and parsed.port in (None, 443)
                and (parsed.path == '/s' or parsed.path.startswith('/s/')))
    except ValueError:
        return False


class WeChatRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise ValueError('unsupported_redirect')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def read_article(url: str) -> dict:
    if not allowed_url(url):
        return {'original_url': url, 'state': 'unsupported_url'}
    try:
        request = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'identity',
        })
        with build_opener(WeChatRedirects()).open(request, timeout=25) as response:
            raw = response.read(MAX_BYTES + 1)
            charset = response.headers.get_content_charset()
            status = response.status
            compression = response.headers.get('Content-Encoding', '').lower()
            if not allowed_url(response.geturl()):
                return {'original_url': url, 'state': 'unsupported_redirect'}
        if len(raw) > MAX_BYTES:
            return {'original_url': url, 'state': 'page_too_large'}
        if compression == 'gzip':
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                raw = compressed.read(MAX_BYTES + 1)
        elif compression == 'deflate':
            inflater = zlib.decompressobj()
            raw = inflater.decompress(raw, MAX_BYTES + 1)
            if len(raw) <= MAX_BYTES and not inflater.eof:
                return {'original_url': url, 'state': 'incomplete_response'}
        elif compression not in ('', 'identity'):
            return {'original_url': url, 'state': 'unsupported_encoding'}
        if len(raw) > MAX_BYTES:
            return {'original_url': url, 'state': 'page_too_large'}
        page, charset = decode_page(raw, charset)
        result = parse_article(page, url)
        result.update(http_status=status, charset=charset)
        return result
    except HTTPError as error:
        return {'original_url': url, 'state': 'fetch_error', 'http_status': error.code, 'error_type': 'HTTPError'}
    except (URLError, OSError, TimeoutError, socket.timeout, ValueError, EOFError, zlib.error) as error:
        return {'original_url': url, 'state': 'fetch_error', 'error_type': type(error).__name__}


def main() -> int:
    parser = argparse.ArgumentParser(description='Read WeChat article URLs in memory and print JSON; no local cache.')
    parser.add_argument('urls', nargs='+', help='One or more original WeChat article URLs.')
    args = parser.parse_args()
    urls = list(dict.fromkeys(args.urls))
    with ThreadPoolExecutor(max_workers=min(4, len(urls))) as pool:
        results = list(pool.map(read_article, urls))
    print(json.dumps({'articles': results}, ensure_ascii=False))
    return 0 if all(article['state'] == 'parsed' for article in results) else 1


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
