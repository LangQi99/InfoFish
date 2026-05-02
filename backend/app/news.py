"""NewsNow API 客户端 - 改写自 nl_robot/plugins/hot_news/news_client.py。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

API_URL = "https://newsnow.busiyi.world/api/s/entire"

_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
}


class NewsNowError(RuntimeError):
    pass


@dataclass(slots=True)
class HotItem:
    id: str
    title: str
    url: str
    source: str
    mobile_url: str | None = None
    extra: dict[str, Any] | None = field(default=None)

    @property
    def heat(self) -> str | None:
        if self.extra and isinstance(self.extra, dict):
            info = self.extra.get("info")
            if isinstance(info, str):
                return info
        return None

    @property
    def description(self) -> str | None:
        if self.extra and isinstance(self.extra, dict):
            hover = self.extra.get("hover")
            if isinstance(hover, str):
                return hover
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "mobile_url": self.mobile_url,
            "source": self.source,
            "heat": self.heat,
            "description": self.description,
        }


async def fetch_hot(
    sources: list[str],
    *,
    timeout: float = 15.0,
    retry: int = 2,
    retry_delay: float = 1.0,
) -> dict[str, list[HotItem]]:
    """请求 NewsNow,返回 source_id -> [HotItem]。"""
    if not sources:
        raise ValueError("sources 不能为空")

    body = {"sources": sources}
    last_err: Exception | None = None
    for attempt in range(retry + 1):
        try:
            return await _request(body, timeout)
        except Exception as e:
            last_err = e
            if attempt < retry:
                await asyncio.sleep(retry_delay * (2**attempt))
    raise NewsNowError(f"NewsNow API 请求失败: {last_err}")


async def _request(body: dict[str, Any], timeout: float) -> dict[str, list[HotItem]]:
    async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS) as client:
        resp = await client.post(API_URL, json=body)
    if resp.status_code != 200:
        raise NewsNowError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except Exception as e:
        raise NewsNowError(f"JSON 解析失败: {e}") from e
    return _parse(data)


def _parse(data: Any) -> dict[str, list[HotItem]]:
    if not isinstance(data, list):
        raise NewsNowError(f"响应格式错误,期望数组,收到 {type(data).__name__}")

    result: dict[str, list[HotItem]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("id")
        items = entry.get("items")
        if not sid or not isinstance(items, list):
            continue

        parsed: list[HotItem] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or "").strip()
            if not title:
                continue
            parsed.append(
                HotItem(
                    id=str(it.get("id") or ""),
                    title=title,
                    url=str(it.get("url") or ""),
                    mobile_url=str(it.get("mobileUrl")) if it.get("mobileUrl") else None,
                    source=str(sid),
                    extra=it.get("extra") if isinstance(it.get("extra"), dict) else None,
                )
            )
        if parsed:
            result[str(sid)] = parsed
    return result
