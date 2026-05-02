"""舆情聚合后端入口。"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from .news import HotItem, NewsNowError, fetch_hot
from .sources import DEFAULT_SOURCE_IDS, SOURCE_NAME_BY_ID, SOURCES

app = FastAPI(title="BettaFish 舆情后端", version="0.1.0")

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


@app.get("/api/export.txt", response_class=PlainTextResponse)
async def export_txt(
    sources: list[str] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    with_heat: bool = Query(default=False),
    keyword: str = Query(default=""),
    download: bool = Query(default=True),
) -> PlainTextResponse:
    """导出当前热点汇总为纯文本 (text/plain)。

    - sources: 限定源 id;为空时使用全部默认源
    - limit:   每个源最多多少条
    - with_heat: 是否在每条后面附带热度
    - keyword: 标题关键词过滤 (大小写不敏感,不区分空白)
    - download: true 时附带 Content-Disposition 触发浏览器下载
    """
    selected = sources or DEFAULT_SOURCE_IDS
    try:
        raw = await fetch_hot(selected)
    except NewsNowError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    kw = keyword.strip().lower()
    now = int(time.time())
    ts_human = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")

    rendered_blocks: list[tuple[str, list[tuple[int, str, str | None]]]] = []
    total = 0
    for sid in selected:
        items = raw.get(sid, [])[:limit]
        rows: list[tuple[int, str, str | None]] = []
        for idx, it in enumerate(items, 1):
            if kw and kw not in it.title.lower():
                continue
            rows.append((idx, it.title, it.heat))
        if rows:
            rendered_blocks.append((SOURCE_NAME_BY_ID.get(sid, sid), rows))
            total += len(rows)

    lines: list[str] = []
    lines.append(f"🔥 全网舆情速览 · {ts_human}")
    suffix = " (已过滤)" if kw else ""
    lines.append(f"共 {len(rendered_blocks)} 个源 / {total} 条热点{suffix}")
    lines.append("")
    for name, rows in rendered_blocks:
        lines.append(f"【{name}】")
        for rank, title, heat in rows:
            tail = f"  · {heat}" if with_heat and heat else ""
            lines.append(f"{rank}. {title}{tail}")
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"

    headers: dict[str, str] = {}
    if download:
        fname = f"bettafish-summary-{datetime.fromtimestamp(now).strftime('%Y%m%d%H%M%S')}.txt"
        headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return PlainTextResponse(text, headers=headers, media_type="text/plain; charset=utf-8")
