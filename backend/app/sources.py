"""可用热点源元数据。id 与 NewsNow API 对应,name 用于前端展示。"""
from __future__ import annotations

SOURCES: list[dict[str, str]] = [
    {"id": "weibo", "name": "微博热搜", "category": "社交"},
    {"id": "zhihu", "name": "知乎热榜", "category": "社交"},
    {"id": "baidu", "name": "百度热搜", "category": "综合"},
    {"id": "toutiao", "name": "今日头条", "category": "综合"},
    {"id": "douyin", "name": "抖音热点", "category": "社交"},
    {"id": "bilibili-hot-search", "name": "B站热搜", "category": "社交"},
    {"id": "tieba", "name": "百度贴吧", "category": "社交"},
    {"id": "tencent-hot", "name": "腾讯新闻", "category": "综合"},
    {"id": "ifeng", "name": "凤凰网", "category": "综合"},
    {"id": "thepaper", "name": "澎湃新闻", "category": "综合"},
    {"id": "douban", "name": "豆瓣讨论", "category": "社交"},
    {"id": "hupu", "name": "虎扑步行街", "category": "社交"},
    {"id": "coolapk", "name": "酷安", "category": "科技"},
    {"id": "36kr-renqi", "name": "36氪人气榜", "category": "科技"},
    {"id": "juejin", "name": "掘金", "category": "科技"},
    {"id": "sspai", "name": "少数派", "category": "科技"},
    {"id": "github-trending-today", "name": "GitHub Trending", "category": "科技"},
    {"id": "hackernews", "name": "Hacker News", "category": "科技"},
    {"id": "producthunt", "name": "Product Hunt", "category": "科技"},
    {"id": "freebuf", "name": "FreeBuf 安全", "category": "科技"},
    {"id": "nowcoder", "name": "牛客", "category": "科技"},
    {"id": "steam", "name": "Steam", "category": "娱乐"},
    {"id": "chongbuluo-hot", "name": "虫部落", "category": "社交"},
]

DEFAULT_SOURCE_IDS: list[str] = [s["id"] for s in SOURCES]
SOURCE_NAME_BY_ID: dict[str, str] = {s["id"]: s["name"] for s in SOURCES}
