<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  AlertCircle,
  ExternalLink,
  Flame,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Sparkles,
} from 'lucide-vue-next'
import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import PageHeader from '@/components/PageHeader.vue'
import type { TrendAnalysis, TrendAngle, TrendItem } from '@/types/business'

const router = useRouter()
const loading = ref(false)
const analyzing = ref(false)
const creating = ref(false)
const source = ref('ALL')
const query = ref('')
const items = ref<TrendItem[]>([])
const sources = ref<
  Array<{ source: string; name: string; status: string; count: number; error?: string }>
>([])
const notice = ref('')
const selected = ref<TrendItem>()
const analysis = ref<TrendAnalysis>()
const selectedAngle = ref(0)
const drawerOpen = ref(false)
const analysisError = ref('')
const analysisStartedAt = ref(0)
const clock = ref(Date.now())
let clockTimer: number | undefined

const analysisElapsed = computed(() =>
  analysisStartedAt.value ? Math.floor((clock.value - analysisStartedAt.value) / 1000) : 0,
)
const analysisStage = computed(() => {
  if (analysisElapsed.value < 5) return '正在读取热点标题、摘要和来源信息'
  if (analysisElapsed.value < 15) return '真实模型正在策划不同的内容切入角度'
  if (analysisElapsed.value < 30) return '正在整理目标读者、开场钩子和文章大纲'
  return '模型响应时间较长，系统仍在等待，请不要重复点击'
})

async function load(refresh = false) {
  loading.value = true
  try {
    const data = await workflowApi.trends({ source: source.value, query: query.value, refresh })
    items.value = data.items
    sources.value = data.sources
    notice.value = data.notice
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '热点加载失败'))
  } finally {
    loading.value = false
  }
}

async function analyze(item: TrendItem) {
  selected.value = item
  analysis.value = undefined
  analysisError.value = ''
  selectedAngle.value = 0
  drawerOpen.value = true
  analyzing.value = true
  analysisStartedAt.value = Date.now()
  try {
    analysis.value = await workflowApi.analyzeTrend({
      title: item.title,
      summary: item.summary,
      source: item.sourceName,
      url: item.url,
    })
    selectedAngle.value = analysis.value.recommended_angle_index
  } catch (error) {
    analysisError.value = getApiErrorMessage(error, 'AI 选题分析失败')
    ElMessage.error(analysisError.value)
  } finally {
    analyzing.value = false
  }
}

async function createFromAngle(angle: TrendAngle) {
  if (!selected.value) return
  creating.value = true
  try {
    const outline = angle.outline.map((item, index) => `${index + 1}. ${item}`).join('\n')
    const article = await workflowApi.createArticle({
      title: angle.title,
      source_text: `热点原始标题：${selected.value.title}\n来源：${selected.value.sourceName}\n原始链接：${selected.value.url}\n榜单摘要：${selected.value.summary || '未提供'}\n\n选定创作角度：${angle.hook}\n建议大纲：\n${outline}\n\n注意：以上榜单信息仅作为选题线索，发布前必须打开原始链接核验事实。`,
      summary: angle.hook,
      topic: selected.value.title.slice(0, 100),
      target_audience: angle.audience,
      tone: '专业自然',
      keywords: selected.value.tags,
    })
    drawerOpen.value = false
    await router.push({ name: 'studio', query: { article: article.id, mode: 'deep' } })
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '创建选题失败'))
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  clockTimer = window.setInterval(() => (clock.value = Date.now()), 1000)
  void load()
})
onBeforeUnmount(() => {
  if (clockTimer) window.clearInterval(clockTimer)
})
</script>

<template>
  <div class="hot-topics-page">
    <PageHeader
      title="热点选题"
      description="读取公开实时榜单，用真实模型把热点转成可执行的原创选题。"
    >
      <el-button :loading="loading" @click="load(true)"
        ><RefreshCw :size="15" class="mr-1" />刷新榜单</el-button
      >
    </PageHeader>
    <section class="trend-toolbar">
      <el-segmented
        v-model="source"
        :options="[
          { label: '全部', value: 'ALL' },
          { label: '百度热榜', value: 'BAIDU' },
          { label: 'Hacker News', value: 'HACKER_NEWS' },
        ]"
        @change="load()"
      />
      <el-input v-model="query" clearable placeholder="搜索热点标题" @keyup.enter="load()" />
      <el-button type="primary" @click="load()">搜索</el-button>
    </section>
    <div class="trend-source-states">
      <span v-for="item in sources" :key="item.source" :class="item.status.toLowerCase()">
        {{ item.name }} ·
        {{ item.status === 'SUCCESS' ? `${item.count} 条` : `读取失败：${item.error}` }}
      </span>
    </div>
    <p class="trend-notice">{{ notice }}</p>
    <section v-loading="loading" class="trend-grid">
      <article v-for="item in items" :key="item.id" class="trend-card">
        <div class="trend-rank">{{ item.rank }}</div>
        <img
          v-if="item.imageUrl"
          :src="item.imageUrl"
          :alt="item.title"
          referrerpolicy="no-referrer"
        />
        <div class="trend-card-content">
          <header>
            <span>{{ item.sourceName }}</span
            ><small>{{ item.heatLabel }}</small>
          </header>
          <h3>{{ item.title }}</h3>
          <p>{{ item.summary || '该榜单未提供摘要，请打开原始来源查看详情。' }}</p>
          <footer>
            <a :href="item.url" target="_blank" rel="noopener noreferrer"
              ><ExternalLink :size="14" />原始来源</a
            >
            <el-button type="primary" size="small" @click="analyze(item)"
              ><Sparkles :size="14" class="mr-1" />AI 分析选题</el-button
            >
          </footer>
        </div>
      </article>
      <el-empty v-if="!loading && !items.length" description="当前来源没有可显示的真实热点" />
    </section>

    <el-drawer v-model="drawerOpen" title="AI 选题分析" size="520px">
      <div class="trend-analysis">
        <div v-if="analyzing" class="analysis-loading-card" data-testid="trend-analysis-loading">
          <LoaderCircle :size="30" class="analysis-spinner" />
          <b>AI 正在分析选题</b>
          <p>{{ analysisStage }}</p>
          <small>已等待 {{ analysisElapsed }} 秒 · 使用已配置的真实模型</small>
          <el-progress
            :percentage="Math.min(92, 12 + analysisElapsed * 2)"
            :show-text="false"
            :stroke-width="6"
          />
        </div>
        <div
          v-else-if="analysisError"
          class="analysis-error-card"
          data-testid="trend-analysis-error"
        >
          <AlertCircle :size="28" />
          <b>这次分析没有完成</b>
          <p>{{ analysisError }}</p>
          <el-button type="primary" @click="selected && analyze(selected)">
            <RotateCcw :size="15" class="mr-1" />重新分析
          </el-button>
        </div>
        <template v-if="analysis">
          <p class="analysis-reason"><Flame :size="18" />{{ analysis.relevance_reason }}</p>
          <article
            v-for="(angle, index) in analysis.angles"
            :key="angle.title"
            :class="{ selected: selectedAngle === index }"
            @click="selectedAngle = index"
          >
            <header>
              <b>{{ angle.title }}</b
              ><span v-if="index === analysis.recommended_angle_index">AI 推荐</span>
            </header>
            <p>{{ angle.hook }}</p>
            <small>目标读者：{{ angle.audience }} · 目标：{{ angle.creative_goal }}</small>
            <ol>
              <li v-for="point in angle.outline" :key="point">{{ point }}</li>
            </ol>
            <el-button
              v-if="selectedAngle === index"
              type="primary"
              :loading="creating"
              @click.stop="createFromAngle(angle)"
              >用这个角度进入深度创作</el-button
            >
          </article>
          <div class="analysis-risks">
            <b>发布前核验</b>
            <ul>
              <li v-for="item in analysis.verification_questions" :key="item">{{ item }}</li>
            </ul>
            <p v-for="item in analysis.risk_notes" :key="item">{{ item }}</p>
          </div>
          <small
            >{{ analysis.provider }} / {{ analysis.modelName }} ·
            {{ analysis.tokenUsage }} Token</small
          >
        </template>
      </div>
    </el-drawer>
  </div>
</template>
