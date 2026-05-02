# BettaFish · 舆情面板

聚合多平台热点的轻量舆情速览。后端 FastAPI + 前端 Vue 3 (Vite)。

## 启动

需要 [uv](https://docs.astral.sh/uv/) (Python) 和 Node 18+。

### 后端 (端口 47821)

```bash
cd backend
uv sync                         # 首次 / 依赖变更后执行
uv run uvicorn app.main:app --host 127.0.0.1 --port 47821 --reload
```

健康检查:`curl http://127.0.0.1:47821/api/health`

### 前端 (端口 51327)

```bash
cd frontend
npm install                     # 首次执行
npm run dev
```

打开 http://localhost:51327。Vite 已配置 `/api` 代理到 `127.0.0.1:47821`,无需改代码即可联调。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 存活检查 |
| GET | `/api/sources` | 全部可用源元数据 |
| GET | `/api/hot` | 聚合获取热点 (JSON,带 60s 缓存) |
| GET | `/api/export.txt` | 导出热点汇总为纯文本 |

### `GET /api/export.txt`

返回 `text/plain; charset=utf-8`。默认带 `Content-Disposition: attachment`,浏览器会触发下载。

**Query 参数**

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `sources` | string (可重复) | 全部默认源 | 限定源 id,如 `?sources=weibo&sources=zhihu` |
| `limit` | int 1–100 | `20` | 每个源最多多少条 |
| `with_heat` | bool | `false` | 是否在每条后追加 `· 热度` |
| `keyword` | string | 空 | 标题关键词过滤,大小写不敏感 |
| `download` | bool | `true` | `false` 时不返回 `Content-Disposition`,直接在浏览器内显示 |

**示例**

```bash
# 全部默认源,每源 20 条,不带热度,触发下载
curl -OJ "http://127.0.0.1:47821/api/export.txt"

# 只看微博 + 知乎,每源 5 条,带热度,直接打印
curl "http://127.0.0.1:47821/api/export.txt?sources=weibo&sources=zhihu&limit=5&with_heat=true&download=false"

# 关键词过滤
curl "http://127.0.0.1:47821/api/export.txt?keyword=AI&download=false"
```

**返回示例**

```
🔥 全网舆情速览 · 2026-05-02 21:08:55
共 1 个源 / 3 条热点

【知乎热榜】
1. xxxxxx  · 736 万热度
2. xxxxxx  · 480 万热度
3. xxxxxx  · 352 万热度
```

前端"⬇️ 导出 TXT"按钮即调用此接口,会根据当前面板的"范围 (筛选/全部)"、"附带热度"开关、关键词搜索框拼接对应参数。
