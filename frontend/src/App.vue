<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

interface SourceMeta { id: string; name: string; category: string }
interface HotEntry {
  id: string
  title: string
  url: string
  mobile_url: string | null
  source: string
  heat: string | null
  description: string | null
  rank: number
}
interface Block {
  source_id: string
  source_name: string
  count: number
  items: HotEntry[]
}
interface HotPayload {
  fetched_at: number
  duration_ms: number
  source_count: number
  total_items: number
  blocks: Block[]
  cached: boolean
  cache_age: number
}

const sources = ref<SourceMeta[]>([])
const blocks = ref<Block[]>([])
const loading = ref(false)
const error = ref('')
const fetchedAt = ref(0)
const cached = ref(false)
const totalItems = ref(0)

const activeCategory = ref<string>('全部')
const keyword = ref('')
const autoRefresh = ref(false)
let timer: number | null = null

const summaryOpen = ref(true)
const summaryScope = ref<'filtered' | 'all'>('filtered')
const summaryWithHeat = ref(false)
const summaryDeep = ref(false)
const exportTip = ref('')

interface DeepProgressItem {
  url: string
  title: string
  source: string
  status: 'pending' | 'ok' | 'fail'
  summary?: string
  keywords?: string[]
  error?: string
}
const deepRunning = ref(false)
const deepDone = ref(0)
const deepTotal = ref(0)
const deepItems = ref<DeepProgressItem[]>([])
let deepES: EventSource | null = null

const categories = computed(() => {
  const set = new Set(sources.value.map(s => s.category))
  return ['全部', ...Array.from(set)]
})

const filteredBlocks = computed(() => {
  let list = blocks.value
  if (activeCategory.value !== '全部') {
    const allowed = new Set(
      sources.value.filter(s => s.category === activeCategory.value).map(s => s.id),
    )
    list = list.filter(b => allowed.has(b.source_id))
  }
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return list
  return list
    .map(b => ({
      ...b,
      items: b.items.filter(it => it.title.toLowerCase().includes(kw)),
    }))
    .filter(b => b.items.length > 0)
})

const matchedTotal = computed(() =>
  filteredBlocks.value.reduce((s, b) => s + b.items.length, 0),
)

const summaryBlocks = computed(() =>
  summaryScope.value === 'all' ? blocks.value : filteredBlocks.value,
)

const summaryItemCount = computed(() =>
  summaryBlocks.value.reduce((s, b) => s + b.items.length, 0),
)

const summaryText = computed(() => {
  const bs = summaryBlocks.value
  if (bs.length === 0) return ''
  const ts = fetchedAt.value ? fmtTime(fetchedAt.value) : '-'
  const lines: string[] = []
  lines.push(`🔥 全网舆情速览 · ${ts}`)
  lines.push(
    `共 ${bs.length} 个源 / ${summaryItemCount.value} 条热点` +
      (summaryScope.value === 'filtered' && (activeCategory.value !== '全部' || keyword.value.trim())
        ? ' (已过滤)'
        : ''),
  )
  lines.push('')
  for (const b of bs) {
    lines.push(`【${b.source_name}】`)
    for (const it of b.items) {
      const heat = summaryWithHeat.value && it.heat ? `  · ${it.heat}` : ''
      lines.push(`${it.rank}. ${it.title}${heat}`)
    }
    lines.push('')
  }
  return lines.join('\n').trimEnd()
})

function buildExportParams(): URLSearchParams {
  const params = new URLSearchParams()
  params.set('limit', '20')
  if (summaryWithHeat.value) params.set('with_heat', 'true')
  if (summaryScope.value === 'filtered') {
    const ids = summaryBlocks.value.map(b => b.source_id)
    for (const id of ids) params.append('sources', id)
    const kw = keyword.value.trim()
    if (kw) params.set('keyword', kw)
  }
  return params
}

function downloadText(text: string, filename: string) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function cancelDeep() {
  if (deepES) { deepES.close(); deepES = null }
  deepRunning.value = false
  exportTip.value = '已取消'
  setTimeout(() => (exportTip.value = ''), 2000)
}

async function exportSummary() {
  if (summaryItemCount.value === 0 || deepRunning.value) return
  const params = buildExportParams()

  if (!summaryDeep.value) {
    const a = document.createElement('a')
    a.href = `/api/export.txt?${params.toString()}`
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    exportTip.value = '✓ 已导出'
    setTimeout(() => (exportTip.value = ''), 2000)
    return
  }

  // 深度导出:SSE 流式 + 进度可视化
  params.set('deep', 'true')
  deepRunning.value = true
  deepDone.value = 0
  deepTotal.value = 0
  deepItems.value = []
  exportTip.value = ''

  const es = new EventSource(`/api/export.stream?${params.toString()}`)
  deepES = es
  const idx: Record<string, number> = {}

  es.addEventListener('meta', e => {
    const d = JSON.parse((e as MessageEvent).data)
    deepTotal.value = d.total
    deepItems.value = d.urls.map((u: any, i: number) => {
      idx[u.url] = i
      return { url: u.url, title: u.title, source: u.source, status: 'pending' as const }
    })
  })
  es.addEventListener('progress', e => {
    const d = JSON.parse((e as MessageEvent).data)
    deepDone.value = d.done
    const i = idx[d.url]
    if (i === undefined) return
    const item = deepItems.value[i]
    if (d.ok) {
      item.status = 'ok'
      item.summary = d.summary
      item.keywords = d.keywords
    } else {
      item.status = 'fail'
      item.error = d.error
    }
  })
  es.addEventListener('done', e => {
    const d = JSON.parse((e as MessageEvent).data)
    downloadText(d.text, d.filename)
    es.close(); deepES = null
    deepRunning.value = false
    exportTip.value = '✓ 已导出'
    setTimeout(() => (exportTip.value = ''), 2500)
  })
  es.addEventListener('error', () => {
    es.close(); deepES = null
    deepRunning.value = false
    exportTip.value = '导出失败 / 连接中断'
    setTimeout(() => (exportTip.value = ''), 4000)
  })
}

async function loadSources() {
  try {
    const r = await fetch('/api/sources')
    const d = await r.json()
    sources.value = d.sources
  } catch (e) {
    console.warn('加载源列表失败', e)
  }
}

async function loadHot(fresh = false) {
  loading.value = true
  error.value = ''
  try {
    const r = await fetch(`/api/hot?limit=20${fresh ? '&fresh=true' : ''}`)
    if (!r.ok) {
      const t = await r.text()
      throw new Error(`HTTP ${r.status}: ${t.slice(0, 120)}`)
    }
    const d: HotPayload = await r.json()
    blocks.value = d.blocks
    fetchedAt.value = d.fetched_at
    cached.value = d.cached
    totalItems.value = d.total_items
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

function fmtTime(ts: number) {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function toggleAuto() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    timer = window.setInterval(() => loadHot(true), 120_000)
  } else if (timer) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(async () => {
  await loadSources()
  await loadHot()
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (deepES) { deepES.close(); deepES = null }
})
</script>

<template>
  <div class="app">
    <header class="app-header">
      <h1><span class="dot"></span> InfoFish · 舆情面板</h1>
      <div class="meta">
        <span v-if="fetchedAt">更新于 {{ fmtTime(fetchedAt) }}</span>
        <span v-if="cached" style="margin-left:8px">· 缓存</span>
        <span v-if="totalItems" style="margin-left:8px">· 共 {{ totalItems }} 条</span>
      </div>
    </header>

    <section class="summary">
      <div class="summary-head" @click="summaryOpen = !summaryOpen">
        <span class="summary-title">📋 一键总结</span>
        <span class="summary-meta">
          {{ summaryBlocks.length }} 个源 · {{ summaryItemCount }} 条
        </span>
        <span class="summary-toggle">{{ summaryOpen ? '收起 ▲' : '展开 ▼' }}</span>
      </div>
      <div v-if="summaryOpen" class="summary-body">
        <div class="summary-tools">
          <label>
            范围:
            <select v-model="summaryScope">
              <option value="filtered">当前筛选 ({{ matchedTotal }})</option>
              <option value="all">全部 ({{ totalItems }})</option>
            </select>
          </label>
          <label>
            <input type="checkbox" v-model="summaryWithHeat" /> 附带热度
          </label>
          <label :title="'深度导出会抓取每条 URL 的正文,生成摘要 + 关键词,耗时较长'">
            <input type="checkbox" v-model="summaryDeep" /> 深度导出
          </label>
          <span style="flex:1"></span>
          <span v-if="exportTip" style="color:var(--accent-2);font-size:12px">{{ exportTip }}</span>
          <button
            class="btn-export"
            :disabled="summaryItemCount === 0 || deepRunning"
            @click="exportSummary"
          >
            <span v-if="deepRunning" class="spinner"></span>
            {{ deepRunning ? `深度导出中 ${deepDone}/${deepTotal}` : '⬇️ 导出 TXT' }}
          </button>
          <button
            v-if="deepRunning"
            class="btn-cancel"
            @click="cancelDeep"
          >取消</button>
        </div>

        <div v-if="deepRunning || deepItems.length > 0" class="deep-panel">
          <div class="deep-bar-wrap">
            <div
              class="deep-bar"
              :style="{ width: deepTotal ? (deepDone / deepTotal * 100) + '%' : '0%' }"
            ></div>
            <span class="deep-bar-label">
              {{ deepDone }} / {{ deepTotal }}
              · ✓ {{ deepItems.filter(i => i.status === 'ok').length }}
              · ✗ {{ deepItems.filter(i => i.status === 'fail').length }}
            </span>
          </div>
          <ul class="deep-list">
            <li v-for="it in deepItems" :key="it.url" class="deep-item" :class="it.status">
              <span class="deep-status">
                <template v-if="it.status === 'pending'">⏳</template>
                <template v-else-if="it.status === 'ok'">✅</template>
                <template v-else>⚠️</template>
              </span>
              <div class="deep-body">
                <div class="deep-title">
                  <span class="deep-source">[{{ it.source }}]</span>
                  <a :href="it.url" target="_blank" rel="noopener noreferrer">{{ it.title }}</a>
                </div>
                <div v-if="it.status === 'ok'" class="deep-summary">{{ it.summary }}</div>
                <div v-if="it.status === 'ok' && it.keywords && it.keywords.length" class="deep-keywords">
                  <span v-for="k in it.keywords" :key="k" class="deep-kw">{{ k }}</span>
                </div>
                <div v-else-if="it.status === 'fail'" class="deep-error">解析失败: {{ it.error }}</div>
              </div>
            </li>
          </ul>
        </div>
        <textarea class="summary-text" :value="summaryText" readonly spellcheck="false"></textarea>
      </div>
    </section>

    <div class="toolbar">
      <input
        type="search"
        v-model="keyword"
        placeholder="🔍 搜索标题关键词…"
        style="min-width:240px;flex:1;max-width:360px"
      />
      <span style="color:var(--muted);font-size:12px">命中 {{ matchedTotal }}</span>
      <span style="flex:1"></span>
      <label>
        <input type="checkbox" :checked="autoRefresh" @change="toggleAuto" />
        2 分钟自动刷新
      </label>
      <button :disabled="loading" @click="loadHot(true)">
        <span v-if="loading" class="spinner"></span>{{ loading ? '加载中' : '立即刷新' }}
      </button>
    </div>

    <div class="chips">
      <span
        v-for="c in categories"
        :key="c"
        class="chip"
        :class="{ active: activeCategory === c }"
        @click="activeCategory = c"
      >{{ c }}</span>
    </div>

    <div v-if="error" class="error">⚠️ {{ error }}</div>
    <div v-else-if="loading && blocks.length === 0" class="loading"><span class="spinner"></span>正在拉取多平台热点…</div>
    <div v-else-if="filteredBlocks.length === 0" class="empty">没有匹配的热点</div>

    <div v-else class="grid">
      <div v-for="b in filteredBlocks" :key="b.source_id" class="card">
        <div class="card-head">
          <span class="name">{{ b.source_name }}</span>
          <span class="count">{{ b.items.length }} 条</span>
        </div>
        <ul class="card-list">
          <li v-for="it in b.items" :key="it.source + it.id + it.rank" class="item">
            <span
              class="rank"
              :class="{ top: it.rank === 1, top2: it.rank === 2 || it.rank === 3 }"
            >{{ it.rank }}</span>
            <div class="body">
              <a class="title" :href="it.url" target="_blank" rel="noopener noreferrer" :title="it.description || it.title">
                {{ it.title }}
              </a>
              <div v-if="it.heat" class="heat">🔥 {{ it.heat }}</div>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
