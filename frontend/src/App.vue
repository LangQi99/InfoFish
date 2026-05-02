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
const copyTip = ref('')

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

async function copySummary() {
  if (!summaryText.value) return
  try {
    await navigator.clipboard.writeText(summaryText.value)
    copyTip.value = '✓ 已复制'
  } catch {
    copyTip.value = '复制失败,请手动选择'
  }
  setTimeout(() => (copyTip.value = ''), 2000)
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
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <div class="app">
    <header class="app-header">
      <h1><span class="dot"></span> BettaFish · 舆情面板</h1>
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
          <span style="flex:1"></span>
          <span v-if="copyTip" style="color:var(--accent-2);font-size:12px">{{ copyTip }}</span>
          <button :disabled="!summaryText" @click="copySummary">📋 复制</button>
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
