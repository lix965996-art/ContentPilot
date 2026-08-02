<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  AlertCircle,
  Archive,
  Bookmark,
  BookMarked,
  LibraryBig,
  ExternalLink,
  Flame,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Plus,
} from 'lucide-vue-next'
import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import type { ResearchItem, TrendAnalysis, TrendAngle, TrendItem } from '@/types/business'

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
const view = ref<'trends' | 'library'>('trends')
const researchItems = ref<ResearchItem[]>([])
const researchLoading = ref(false)
const researchQuery = ref('')
const researchStatus = ref('')
const researchDialog = ref(false)
const researchDraft = ref<Partial<ResearchItem> & { tags: string[] }>({ tags: [] })
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
const savedSourceIds = computed(
  () => new Set(researchItems.value.map((item) => item.sourceId).filter(Boolean)),
)

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

async function loadResearch() {
  researchLoading.value = true
  try {
    researchItems.value = await workflowApi.researchItems({
      query: researchQuery.value,
      status: researchStatus.value,
    })
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '灵感库加载失败'))
  } finally {
    researchLoading.value = false
  }
}

async function saveTrend(item: TrendItem) {
  try {
    await workflowApi.createResearchItem({
      title: item.title,
      summary: item.summary,
      url: item.url,
      image_url: item.imageUrl,
      source: item.source,
      source_name: item.sourceName,
      source_id: item.id,
      topic_cluster: item.tags[0] || '',
      tags: item.tags,
      status: 'INBOX',
    })
    await loadResearch()
    ElMessage.success('已保存到灵感库')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存失败'))
  }
}

function openResearch(item?: ResearchItem) {
  researchDraft.value = item
    ? { ...item, tags: [...item.tags] }
    : { title: '', summary: '', notes: '', topicCluster: '', status: 'INBOX', tags: [] }
  researchDialog.value = true
}

async function saveResearch() {
  if (!researchDraft.value.title?.trim()) return ElMessage.warning('请填写灵感标题')
  try {
    if (researchDraft.value.id) {
      await workflowApi.updateResearchItem(researchDraft.value.id, {
        title: researchDraft.value.title,
        summary: researchDraft.value.summary,
        notes: researchDraft.value.notes,
        topic_cluster: researchDraft.value.topicCluster,
        tags: researchDraft.value.tags,
        status: researchDraft.value.status,
      })
    } else {
      await workflowApi.createResearchItem({
        title: researchDraft.value.title,
        summary: researchDraft.value.summary,
        notes: researchDraft.value.notes,
        topic_cluster: researchDraft.value.topicCluster,
        tags: researchDraft.value.tags,
        source: 'MANUAL',
        source_name: '手动记录',
        status: researchDraft.value.status || 'INBOX',
      })
    }
    researchDialog.value = false
    await loadResearch()
    ElMessage.success('灵感条目已保存')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存失败'))
  }
}

async function archiveResearch(item: ResearchItem) {
  try {
    await workflowApi.archiveResearchItem(item.id)
    await loadResearch()
    ElMessage.success('已移入归档')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '归档失败'))
  }
}

async function createFromResearch(item: ResearchItem) {
  creating.value = true
  try {
    const article = await workflowApi.createArticle({
      title: item.title,
      source_text: [
        `研究主题：${item.title}`,
        `来源：${item.sourceName || item.source}`,
        item.url ? `原始链接：${item.url}` : '',
        item.summary ? `来源摘要：${item.summary}` : '',
        item.notes ? `研究笔记：${item.notes}` : '',
        '要求：发布前核验来源事实，不得将摘要中的不确定信息写成确定结论。',
      ]
        .filter(Boolean)
        .join('\n\n'),
      summary: item.summary,
      topic: item.topicCluster || item.title.slice(0, 100),
      tone: '专业自然',
      keywords: item.tags,
    })
    if (item.imageUrl) {
      await workflowApi.selectMedia({
        article_id: article.id,
        source: item.source,
        source_id: item.sourceId,
        image_url: item.imageUrl,
        thumbnail_url: item.imageUrl,
        photographer_name: item.sourceName,
        photographer_url: item.url,
        alt_text: `${item.title} · 来源参考图，发布前请确认版权`,
        title: item.title,
        license_type: '来源参考（需核验版权）',
        license_note: item.url,
        usage_type: 'COVER',
      })
    }
    await workflowApi.updateResearchItem(item.id, { status: 'USED' })
    await router.push({ name: 'studio', query: { article: article.id, mode: 'deep' } })
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '创建深度创作任务失败'))
  } finally {
    creating.value = false
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
    if (selected.value.imageUrl) {
      try {
        await workflowApi.selectMedia({
          article_id: article.id,
          source: 'HOT_TREND_REFERENCE',
          source_id: selected.value.id,
          image_url: selected.value.imageUrl,
          thumbnail_url: selected.value.imageUrl,
          photographer_name: selected.value.sourceName,
          photographer_url: selected.value.url,
          alt_text: `${selected.value.title} · 热点来源参考图，发布前请确认版权`,
          search_keyword: selected.value.title,
          title: selected.value.title,
          license_type: '来源参考（需核验版权）',
          license_note: selected.value.url,
          usage_type: 'COVER',
        })
      } catch (error) {
        ElMessage.warning(getApiErrorMessage(error, '热点文章已创建，但来源参考图保存失败'))
      }
    }
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
  void loadResearch()
})
onBeforeUnmount(() => {
  if (clockTimer) window.clearInterval(clockTimer)
})
</script>

<template>
  <div class="hot-topics-page">
    <PageHeader
      title="选题研究"
      description="从实时热点发现选题，把来源、笔记和验证线索沉淀为可复用的创作资料。"
    >
      <el-button v-if="view === 'trends'" :loading="loading" @click="load(true)"
        ><RefreshCw :size="15" class="mr-1" />刷新榜单</el-button
      >
      <el-button v-else type="primary" @click="openResearch()"
        ><Plus :size="15" class="mr-1" />新增灵感</el-button
      >
    </PageHeader>
    <div class="content-tabs research-tabs">
      <button :class="{ active: view === 'trends' }" @click="view = 'trends'">
        <Flame :size="14" />实时热点
      </button>
      <button :class="{ active: view === 'library' }" @click="view = 'library'">
        <LibraryBig :size="14" />灵感库 <span>{{ researchItems.length }}</span>
      </button>
    </div>
    <template v-if="view === 'trends'">
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
              <el-button
                size="small"
                :disabled="savedSourceIds.has(item.id)"
                @click="saveTrend(item)"
                ><BookMarked v-if="savedSourceIds.has(item.id)" :size="14" class="mr-1" /><Bookmark
                  v-else
                  :size="14"
                  class="mr-1"
                />{{ savedSourceIds.has(item.id) ? '已收藏' : '收藏' }}</el-button
              >
              <el-button type="primary" size="small" @click="analyze(item)"
                ><Sparkles :size="14" class="mr-1" />AI 分析选题</el-button
              >
            </footer>
          </div>
        </article>
        <el-empty v-if="!loading && !items.length" description="当前来源没有可显示的真实热点" />
      </section>
    </template>
    <template v-else>
      <section class="research-toolbar">
        <el-input
          v-model="researchQuery"
          clearable
          placeholder="搜索标题、笔记或话题"
          @keyup.enter="loadResearch"
          @clear="loadResearch"
        />
        <el-select v-model="researchStatus" clearable placeholder="全部阶段" @change="loadResearch">
          <el-option label="收件箱" value="INBOX" />
          <el-option label="研究中" value="RESEARCHING" />
          <el-option label="可创作" value="READY" />
          <el-option label="已使用" value="USED" />
        </el-select>
        <el-button @click="loadResearch">筛选</el-button>
      </section>
      <section v-loading="researchLoading" class="research-library">
        <article v-for="item in researchItems" :key="item.id" class="research-card">
          <img
            v-if="item.imageUrl"
            :src="item.imageUrl"
            :alt="item.title"
            referrerpolicy="no-referrer"
          />
          <div>
            <header>
              <span>{{ item.sourceName || '手动记录' }}</span>
              <StatusBadge :status="item.status" />
            </header>
            <h3>{{ item.title }}</h3>
            <p>{{ item.summary || item.notes || '尚未补充摘要和研究笔记。' }}</p>
            <div class="research-tags">
              <span v-if="item.topicCluster">{{ item.topicCluster }}</span>
              <span v-for="tag in item.tags.slice(0, 4)" :key="tag">{{ tag }}</span>
            </div>
            <footer>
              <el-button size="small" @click="openResearch(item)">整理</el-button>
              <el-button
                type="primary"
                size="small"
                :loading="creating"
                @click="createFromResearch(item)"
                >进入深度创作</el-button
              >
              <button class="archive-button" title="归档" @click="archiveResearch(item)">
                <Archive :size="14" />
              </button>
            </footer>
          </div>
        </article>
        <el-empty
          v-if="!researchLoading && !researchItems.length"
          description="还没有保存研究资料"
        />
      </section>
    </template>

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
    <el-dialog
      v-model="researchDialog"
      :title="researchDraft.id ? '整理灵感' : '新增灵感'"
      width="560px"
    >
      <el-form label-position="top">
        <el-form-item label="标题" required>
          <el-input v-model="researchDraft.title" maxlength="255" />
        </el-form-item>
        <div class="grid grid-cols-2 gap-3">
          <el-form-item label="阶段">
            <el-select v-model="researchDraft.status" class="w-full">
              <el-option label="收件箱" value="INBOX" />
              <el-option label="研究中" value="RESEARCHING" />
              <el-option label="可创作" value="READY" />
              <el-option label="已使用" value="USED" />
            </el-select>
          </el-form-item>
          <el-form-item label="话题组">
            <el-input v-model="researchDraft.topicCluster" placeholder="例如：AI 产品" />
          </el-form-item>
        </div>
        <el-form-item label="摘要">
          <el-input v-model="researchDraft.summary" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="研究笔记">
          <el-input
            v-model="researchDraft.notes"
            type="textarea"
            :rows="5"
            placeholder="记录证据、争议点、待核验问题和可用角度"
          />
        </el-form-item>
        <el-form-item label="标签">
          <el-select
            v-model="researchDraft.tags"
            multiple
            filterable
            allow-create
            default-first-option
            class="w-full"
            placeholder="输入后回车添加"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="researchDialog = false">取消</el-button>
        <el-button type="primary" @click="saveResearch">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
