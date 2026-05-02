"""文章深度解析:URL -> {title, summary, keywords}。"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import httpx
import jieba
import jieba.analyse
import trafilatura

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 句子切分:中英文标点
_SENT_SPLIT = re.compile(r"(?<=[。！？!?\.])\s+|(?<=[。！？!?])(?=[^\"'」』])")
_HAN = re.compile(r"[一-鿿]")


class ArticleError(RuntimeError):
    pass


@dataclass(slots=True)
class Article:
    url: str
    title: str
    summary: str
    text: str
    keywords: list[str]
    text_length: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "text": self.text,
            "keywords": self.keywords,
            "text_length": self.text_length,
        }


async def analyze_url(
    url: str,
    *,
    timeout: float = 12.0,
    summary_sentences: int = 3,
    summary_max_chars: int = 240,
    keyword_top_k: int = 8,
) -> Article:
    """抓取 URL 并返回标题/摘要/关键词。"""
    if not url or not url.startswith(("http://", "https://")):
        raise ArticleError(f"非法 URL: {url!r}")

    try:
        async with httpx.AsyncClient(
            timeout=timeout, headers=_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(url)
    except httpx.HTTPError as e:
        raise ArticleError(f"请求失败: {e}") from e

    if resp.status_code != 200:
        raise ArticleError(f"HTTP {resp.status_code}")

    html = resp.text
    return _extract(url, html, summary_sentences, summary_max_chars, keyword_top_k)


def _extract(
    url: str,
    html: str,
    summary_sentences: int,
    summary_max_chars: int,
    keyword_top_k: int,
) -> Article:
    extracted = trafilatura.bare_extraction(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        with_metadata=True,
    )
    if not extracted:
        raise ArticleError("无法提取正文")

    title = (extracted.get("title") if isinstance(extracted, dict) else getattr(extracted, "title", "")) or ""
    text = (extracted.get("text") if isinstance(extracted, dict) else getattr(extracted, "text", "")) or ""
    title = title.strip()
    text = text.strip()

    if not text:
        raise ArticleError("正文为空")

    if not _looks_meaningful(text):
        raise ArticleError("非有效正文 (页面骨架/导航/加载占位)")

    summary = _summarize(text, summary_sentences, summary_max_chars)
    keywords = _keywords(title + "。" + text, keyword_top_k)
    return Article(
        url=url,
        title=title,
        summary=summary,
        text=text,
        keywords=keywords,
        text_length=len(text),
    )


def _looks_meaningful(text: str) -> bool:
    """过滤伪正文 (SPA 骨架 / 导航条 / "加载中" 占位)。"""
    s = text.strip()
    if len(s) < 100:
        return False
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    short_lines = sum(1 for ln in lines if len(ln) <= 3)
    if short_lines / len(lines) > 0.4:
        return False
    avg_len = sum(len(ln) for ln in lines) / len(lines)
    if avg_len < 8:
        return False
    return True


def _summarize(text: str, n: int, max_chars: int) -> str:
    sents = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    if not sents:
        return text[:max_chars]
    out = ""
    for s in sents[:n]:
        if len(out) + len(s) > max_chars:
            remain = max_chars - len(out)
            if remain > 10:
                out += s[:remain].rstrip() + "…"
            break
        out += s
        if not out.endswith(("。", "！", "？", ".", "!", "?")):
            out += "。"
    return out or text[:max_chars]


def _keywords(text: str, top_k: int) -> list[str]:
    if not text:
        return []
    # 中文为主用 jieba TF-IDF;英文文本用频率法
    if _HAN.search(text):
        tags = jieba.analyse.extract_tags(text, topK=top_k, withWeight=False)
        return [t for t in tags if t.strip()]
    # 简易英文关键词:小写 + 去停用词 + 频率
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text.lower())
    stop = _EN_STOPWORDS
    freq: dict[str, int] = {}
    for w in words:
        if w in stop:
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:top_k]]


_EN_STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "with", "this", "that",
    "from", "have", "has", "was", "were", "they", "their", "would", "could",
    "should", "what", "when", "where", "which", "while", "your", "our", "all",
    "any", "can", "will", "more", "than", "into", "out", "about", "over",
    "also", "been", "being", "its", "it's",
}


async def analyze_many(
    urls: list[str], *, concurrency: int = 5, **kwargs: Any
) -> list[Article | ArticleError]:
    """并发分析多个 URL,失败用 ArticleError 占位,顺序与输入一致。"""
    sem = asyncio.Semaphore(concurrency)

    async def one(u: str) -> Article | ArticleError:
        async with sem:
            try:
                return await analyze_url(u, **kwargs)
            except ArticleError as e:
                return e
            except Exception as e:  # noqa: BLE001
                return ArticleError(str(e))

    return await asyncio.gather(*(one(u) for u in urls))


async def analyze_many_iter(
    urls: list[str], *, concurrency: int = 5, **kwargs: Any
):
    """并发分析,按完成顺序逐个 yield (url, Article | ArticleError)。"""
    sem = asyncio.Semaphore(concurrency)
    queue: asyncio.Queue[tuple[str, Article | ArticleError]] = asyncio.Queue()

    async def worker(u: str) -> None:
        async with sem:
            try:
                res: Article | ArticleError = await analyze_url(u, **kwargs)
            except ArticleError as e:
                res = e
            except Exception as e:  # noqa: BLE001
                res = ArticleError(str(e))
        await queue.put((u, res))

    tasks = [asyncio.create_task(worker(u)) for u in urls]
    try:
        for _ in range(len(urls)):
            yield await queue.get()
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
