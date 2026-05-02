"""舆情聚合后端入口。"""
from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

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
