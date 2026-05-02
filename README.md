# InfoFish · 舆情面板

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
| GET | `/api/export.stream` | 同上,SSE 流式返回深度导出进度 |

CORS 已开放 `*`,可在任意前端 / 脚本中直接调用。返回均为 UTF-8。

### `GET /api/health`

```json
{ "status": "ok" }
```

### `GET /api/sources`

列出当前后端支持的所有源,可用作下拉框 / 分类筛选数据源。

```json
{
  "sources": [
    { "id": "weibo",  "name": "微博热搜", "category": "社交" },
    { "id": "zhihu",  "name": "知乎热榜", "category": "社交" },
    { "id": "baidu",  "name": "百度热搜", "category": "综合" }
  ]
}
```

字段:

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 源 id,用于 `/api/hot` 和 `/api/export.txt` 的 `sources` 参数 |
| `name` | string | 中文展示名 |
| `category` | string | 大类 (社交 / 综合 / 科技 / 娱乐 …) |

### `GET /api/hot`

核心接口。聚合多个源的热点列表,适合自定义前端展示。后端有 **60 秒**内存缓存,同样的 `sources+limit` 组合在窗口内复用结果;`fresh=true` 强制穿透缓存。

**Query 参数**

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `sources` | string (可重复) | 全部默认源 | 限定源 id,如 `?sources=weibo&sources=zhihu` |
| `limit` | int 1–100 | `20` | 每个源最多返回多少条 |
| `fresh` | bool | `false` | 跳过缓存,强制重新拉取 |

**响应结构**

```json
{
  "fetched_at": 1746189000,
  "duration_ms": 842,
  "source_count": 2,
  "total_items": 6,
  "cached": false,
  "cache_age": 0,
  "blocks": [
    {
      "source_id": "weibo",
      "source_name": "微博热搜",
      "count": 3,
      "items": [
        {
          "rank": 1,
          "id": "xxxxxx",
          "title": "标题文本",
          "url": "https://...",
          "mobile_url": "https://...",
          "source": "weibo",
          "heat": "1234万",
          "description": "悬浮提示/简介,可能为 null"
        }
      ]
    }
  ]
}
```

字段说明:

- 顶层
  - `fetched_at`:Unix 秒时间戳 (拉取/缓存生成时间)
  - `duration_ms`:本次后端聚合耗时;`cached=true` 时通常为 0
  - `source_count`:实际返回数据的源数量 (失败/空源不计)
  - `total_items`:所有源条目数之和
  - `cached` / `cache_age`:是否命中缓存,缓存年龄 (秒)
  - `blocks`:每个源一个块
- `blocks[]`
  - `source_id` / `source_name`:对应 `/api/sources`
  - `count`:本块内 `items` 数量
  - `items`:热点条目数组 (按热度顺序,`rank` 从 1 开始)
- `blocks[].items[]`
  - `rank`:在该源内的排名
  - `id` / `title` / `url`:基本信息
  - `mobile_url`:移动端 URL,可能为 `null`
  - `source`:源 id (与所在 block 一致)
  - `heat`:热度文本,可能为 `null` (不同平台口径不同,不要按数字解析)
  - `description`:鼠标悬浮提示文本,可能为 `null`

**示例**

```bash
# 只取微博 + 知乎 各 5 条
curl "http://127.0.0.1:47821/api/hot?sources=weibo&sources=zhihu&limit=5"

# 强制刷新
curl "http://127.0.0.1:47821/api/hot?fresh=true"
```

**前端调用示例 (fetch)**

```js
const params = new URLSearchParams({ limit: '10' })
for (const id of ['weibo', 'zhihu']) params.append('sources', id)
const res = await fetch(`http://127.0.0.1:47821/api/hot?${params}`)
const data = await res.json()
for (const block of data.blocks) {
  console.log(block.source_name, block.items.map(i => i.title))
}
```

**错误响应**

上游 NewsNow 失败时返回 `502`:

```json
{ "detail": "NewsNow API 请求失败: ..." }
```

参数越界 (如 `limit=0`) 由 FastAPI 返回 `422` validation 错误。

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
| `deep` | bool | `false` | **深度导出**:抓取每条 URL 正文并附 summary + keywords |
| `deep_limit` | int 1–100 | `30` | 深度模式下最多解析的条目总数 (按筛选后顺序截断,防止全量抓取过慢) |
| `deep_concurrency` | int 1–16 | `5` | 深度模式并发抓取数 |

**示例**

```bash
# 全部默认源,每源 20 条,不带热度,触发下载
curl -OJ "http://127.0.0.1:47821/api/export.txt"

# 只看微博 + 知乎,每源 5 条,带热度,直接打印
curl "http://127.0.0.1:47821/api/export.txt?sources=weibo&sources=zhihu&limit=5&with_heat=true&download=false"

# 关键词过滤
curl "http://127.0.0.1:47821/api/export.txt?keyword=AI&download=false"

# 深度导出:36 氪前 5 条,抓正文 + 摘要 + 关键词
curl "http://127.0.0.1:47821/api/export.txt?sources=36kr-renqi&limit=5&deep=true&download=false"
```

**普通导出返回示例**

```
🔥 全网舆情速览 · 2026-05-02 21:08:55
共 1 个源 / 3 条热点

【知乎热榜】
1. xxxxxx  · 736 万热度
2. xxxxxx  · 480 万热度
3. xxxxxx  · 352 万热度
```

**深度导出 (`deep=true`)**

每条热点下追加三行:`🔗 URL` / `📝 摘要` / `🏷️ 关键词`。失败 (反爬 403、超时、无正文等) 会标 `⚠️ 解析失败`,不影响其它条目。

实现:`httpx` 抓 HTML → `trafilatura` 抽正文/标题 → 中文用 `jieba` TF-IDF 取 8 个关键词,英文用频率法;摘要为正文前 3 句,封顶 240 字。

```
���36氪人气榜】
1. 8 点 1 氪丨MCN 机构回应女孩挪用上千万打赏主播…
   🔗 https://36kr.com/p/3777227930224900
   📝 8 点 1 氪丨MCN 机构回应女孩挪用上千万打赏主播；苹果更换 CEO 原因曝光…
   🏷️ 36, 2026, 苹果, 微信, 面板
```

注意事项:
- 深度导出会真去逐条抓 URL,**比普通导出慢得多**;`deep_limit` 是兜底,默认 30 条
- 部分平台 (微博 / 知乎 / 抖音 / 头条 等) 反爬严格,大概率 403 / JS 渲染拿不到正文,这是正常现象
- 内存中没有为深度结果做缓存,重复请求会重复抓取
- 标题第二行的 `📝` 段是源站正文起始几句,不是 LLM 生成的语义摘要

前端"⬇️ 导出 TXT"按钮即调用此接口,会根据当前面板的"范围 (筛选/全部)"、"附带热度"、"深度导出"开关、关键词搜索框拼接对应参数。**深度导出会自动改走 `/api/export.stream`**,边解析边显示进度。

### `GET /api/export.stream`

`/api/export.txt?deep=true` 的流式版本,使用 [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)。参数同 `export.txt` (`deep` 默认 `true`)。返回 `text/event-stream`,共 4 类事件:

| event | data 字段 | 触发时机 |
| --- | --- | --- |
| `meta` | `{ total, urls: [{url,title,source}], filename, deep }` | 请求开始,告知前端有几个 URL 要解析 |
| `progress` | `{ url, ok, done, total, title?, summary?, keywords?, error? }` | 每完成一条 (按完成顺序,不一定按输入顺序) |
| `done` | `{ text, filename }` | 全部完成,返回最终拼好的 TXT 文本与建议文件名 |
| `error` | `{ detail }` | 上游错误,流终止 |

并发由 `deep_concurrency` 控制 (默认 5,最大 16),后端用 `asyncio.Semaphore` 限流。

**前端使用示例**

```js
const es = new EventSource(`/api/export.stream?sources=36kr-renqi&limit=5`)
es.addEventListener('meta',     e => console.log('total', JSON.parse(e.data).total))
es.addEventListener('progress', e => {
  const d = JSON.parse(e.data)
  console.log(`${d.done}/${d.total}`, d.ok ? d.title : `FAIL ${d.error}`)
})
es.addEventListener('done', e => {
  const { text, filename } = JSON.parse(e.data)
  // 触发下载
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
  a.download = filename; a.click()
  es.close()
})
es.addEventListener('error', () => es.close())
```

**curl 调试**

```bash
curl -N "http://127.0.0.1:47821/api/export.stream?sources=36kr-renqi&limit=3"
```

`-N` 关掉缓冲,可以看到事件按完成顺序逐行打印。
