"""舆情聚合后端入口。"""
from __future__ import annotations

import time
import json
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

from .article import ArticleError, analyze_many, analyze_many_iter
from .news import HotItem, NewsNowError, fetch_hot
from .sources import DEFAULT_SOURCE_IDS, SOURCE_NAME_BY_ID, SOURCES

app = FastAPI(title="InfoFish 舆情后端", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 简单内存缓存:source_set_key -> (timestamp, payload)
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 60.0  # 秒


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sources")
async def list_sources() -> dict[str, Any]:
    return {"sources": SOURCES}


@app.get("/api/hot")
async def hot(
    sources: list[str] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    fresh: bool = Query(default=False),
) -> dict[str, Any]:
    """聚合获取多平台热点。

    - sources: 指定源 id 列表;为空时拉取全部默认源
    - limit: 每个源返回的最大条目数
    - fresh: 跳过缓存,强制刷新
    """
    selected = sources or DEFAULT_SOURCE_IDS
    cache_key = f"{','.join(sorted(selected))}|{limit}"

    now = time.time()
    if not fresh:
        cached = _CACHE.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL:
            payload = dict(cached[1])
            payload["cached"] = True
            payload["cache_age"] = round(now - cached[0], 1)
            return payload

    started = time.time()
    try:
        raw = await fetch_hot(selected)
    except NewsNowError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    blocks: list[dict[str, Any]] = []
    total = 0
    for sid in selected:
        items = raw.get(sid, [])
        if not items:
            continue
        trimmed = items[:limit]
        total += len(trimmed)
        blocks.append(
            {
                "source_id": sid,
                "source_name": SOURCE_NAME_BY_ID.get(sid, sid),
                "count": len(trimmed),
                "items": [_item_dict(it, idx) for idx, it in enumerate(trimmed, 1)],
            }
        )

    payload = {
        "fetched_at": int(now),
        "duration_ms": int((time.time() - started) * 1000),
        "source_count": len(blocks),
        "total_items": total,
        "blocks": blocks,
        "cached": False,
        "cache_age": 0,
    }
    _CACHE[cache_key] = (now, payload)
    return payload


def _item_dict(it: HotItem, rank: int) -> dict[str, Any]:
    d = it.to_dict()
    d["rank"] = rank
    return d


# 行格式: (rank, title, url, heat)
Row = tuple[int, str, str, str | None]
# 块格式: (source_id, source_name, [Row, ...])
RenderedBlock = tuple[str, str, list[Row]]

# 深度导出黑名单:这些源链接是搜索/SPA 入口、商店页、或反爬严格,深度抓取无意义。
# 普通 TXT 导出仍然正常包含它们,只是不会再去逐条抓 URL。
# 其它"伪正文"页 (抖音/B站/豆瓣等 SPA) 由 article._looks_meaningful 兜底拦截。
DEEP_BLACKLIST: frozenset[str] = frozenset({
    "weibo", "zhihu", "producthunt",  # 链接是搜索/SPA 入口或反爬 403
    "steam",                           # Steam 商店页 (多语言菜单,无文章)
    "tieba",                           # 贴吧帖混入大量用户名导航,信噪比低
})


def _collect_rows(
    raw: dict[str, list[HotItem]],
    selected: list[str],
    limit: int,
    keyword: str,
) -> tuple[list[RenderedBlock], int]:
    kw = keyword.strip().lower()
    blocks: list[RenderedBlock] = []
    total = 0
    for sid in selected:
        items = raw.get(sid, [])[:limit]
        rows: list[Row] = []
        for idx, it in enumerate(items, 1):
            if kw and kw not in it.title.lower():
                continue
            rows.append((idx, it.title, it.url, it.heat))
        if rows:
            blocks.append((sid, SOURCE_NAME_BY_ID.get(sid, sid), rows))
            total += len(rows)
    return blocks, total


def _flatten_urls(blocks: list[RenderedBlock], cap: int) -> list[str]:
    """收集深度导出待抓 URL,跳过黑名单源。"""
    out: list[str] = []
    seen: set[str] = set()
    for sid, _, rows in blocks:
        if sid in DEEP_BLACKLIST:
            continue
        for _, _, url, _ in rows:
            if url and url not in seen:
                seen.add(url)
                out.append(url)
                if len(out) >= cap:
                    return out
    return out


def _render_text(
    blocks: list[RenderedBlock],
    deep_map: dict[str, dict[str, Any]],
    ts_human: str,
    keyword: str,
    with_heat: bool,
    deep: bool,
) -> str:
    lines: list[str] = []
    lines.append(f"🔥 全网舆情速览 · {ts_human}")
    total = sum(len(rows) for _, _, rows in blocks)
    parts: list[str] = []
    if keyword.strip():
        parts.append("已过滤")
    if deep:
        ok = len([v for v in deep_map.values() if "error" not in v])
        parts.append(f"深度 {ok}/{len(deep_map)} 成功")
    suffix = f" ({', '.join(parts)})" if parts else ""
    lines.append(f"共 {len(blocks)} 个源 / {total} 条热点{suffix}")
    lines.append("")
    for sid, name, rows in blocks:
        skipped = deep and sid in DEEP_BLACKLIST
        tag = "  (已跳过深度抓取)" if skipped else ""
        lines.append(f"【{name}】{tag}")
        for rank, title, url, heat in rows:
            tail = f"  · {heat}" if with_heat and heat else ""
            lines.append(f"{rank}. {title}{tail}")
            if deep and not skipped and url in deep_map:
                info = deep_map[url]
                lines.append(f"   🔗 {url}")
                if "error" in info:
                    lines.append(f"   ⚠️ 解析失败: {info['error']}")
                else:
                    if info.get("summary"):
                        lines.append(f"   📝 {info['summary']}")
                    if info.get("keywords"):
                        lines.append(f"   🏷️ {', '.join(info['keywords'])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _filename(deep: bool, ts: int) -> str:
    suffix_tag = "-deep" if deep else ""
    return (
        f"InfoFish-summary{suffix_tag}-"
        f"{datetime.fromtimestamp(ts).strftime('%Y%m%d%H%M%S')}.txt"
    )


@app.get("/api/export.txt", response_class=PlainTextResponse)
async def export_txt(
    sources: list[str] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    with_heat: bool = Query(default=False),
    keyword: str = Query(default=""),
    download: bool = Query(default=True),
    deep: bool = Query(default=False),
    deep_limit: int = Query(default=30, ge=1, le=100),
    deep_concurrency: int = Query(default=5, ge=1, le=16),
) -> PlainTextResponse:
    """导出当前热点汇总为纯文本 (text/plain)。

    深度导出推荐使用 /api/export.stream (SSE 进度);本端点深度模式会一次性等到
    全部完成后再返回,客户端没有进度反馈。
    """
    selected = sources or DEFAULT_SOURCE_IDS
    try:
        raw = await fetch_hot(selected)
    except NewsNowError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    blocks, _ = _collect_rows(raw, selected, limit, keyword)
    now = int(time.time())
    ts_human = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")

    deep_map: dict[str, dict[str, Any]] = {}
    if deep:
        urls = _flatten_urls(blocks, deep_limit)
        results = await analyze_many(urls, concurrency=deep_concurrency)
        for url, res in zip(urls, results):
            if isinstance(res, ArticleError):
                deep_map[url] = {"error": str(res)}
            else:
                deep_map[url] = res.to_dict()

    text = _render_text(blocks, deep_map, ts_human, keyword, with_heat, deep)

    headers: dict[str, str] = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{_filename(deep, now)}"'
    return PlainTextResponse(text, headers=headers, media_type="text/plain; charset=utf-8")


@app.get("/api/export.stream")
async def export_stream(
    sources: list[str] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    with_heat: bool = Query(default=False),
    keyword: str = Query(default=""),
    deep: bool = Query(default=True),
    deep_limit: int = Query(default=30, ge=1, le=100),
    deep_concurrency: int = Query(default=5, ge=1, le=16),
) -> StreamingResponse:
    """SSE 流式导出。事件类型:

    - `meta`     {total, urls: [{url,title,source}], filename}
    - `progress` {url, ok, title?, summary?, keywords?, error?, done, total}
    - `done`     {text, filename}
    - `error`    {detail}
    """
    selected = sources or DEFAULT_SOURCE_IDS

    async def gen():
        try:
            raw = await fetch_hot(selected)
        except NewsNowError as e:
            yield _sse("error", {"detail": str(e)})
            return

        blocks, _ = _collect_rows(raw, selected, limit, keyword)
        now = int(time.time())
        ts_human = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        urls = _flatten_urls(blocks, deep_limit) if deep else []

        # 给前端一份 url->title 映射,渲染进度列表
        url_meta: list[dict[str, str]] = []
        seen: set[str] = set()
        for _, src_name, rows in blocks:
            for _, title, url, _ in rows:
                if url and url in urls and url not in seen:
                    seen.add(url)
                    url_meta.append({"url": url, "title": title, "source": src_name})

        filename = _filename(deep, now)
        skipped_sources = [
            SOURCE_NAME_BY_ID.get(sid, sid)
            for sid, _, _ in blocks
            if deep and sid in DEEP_BLACKLIST
        ]
        yield _sse("meta", {
            "total": len(urls),
            "urls": url_meta,
            "filename": filename,
            "deep": deep,
            "skipped_sources": skipped_sources,
        })

        deep_map: dict[str, dict[str, Any]] = {}
        if deep and urls:
            done = 0
            async for url, res in analyze_many_iter(urls, concurrency=deep_concurrency):
                done += 1
                if isinstance(res, ArticleError):
                    deep_map[url] = {"error": str(res)}
                    yield _sse("progress", {
                        "url": url, "ok": False, "error": str(res),
                        "done": done, "total": len(urls),
                    })
                else:
                    deep_map[url] = res.to_dict()
                    yield _sse("progress", {
                        "url": url, "ok": True,
                        "title": res.title,
                        "summary": res.summary,
                        "keywords": res.keywords,
                        "done": done, "total": len(urls),
                    })

        text = _render_text(blocks, deep_map, ts_human, keyword, with_heat, deep)
        yield _sse("done", {"text": text, "filename": filename})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
