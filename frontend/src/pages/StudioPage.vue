<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Check,
  CalendarClock,
  Clipboard,
  FilePlus2,
  FileText,
  ImagePlus,
  RefreshCw,
  Save,
  Send,
  Trash2,
  Type,
  X,
} from 'lucide-vue-next'
import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import PlatformIcon from '@/components/PlatformIcon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import Toast from '@/components/Toast.vue'
import type {
  Article,
  GenerationTask,
  MediaAsset,
  Platform,
  PlatformAccount,
  Variant,
} from '@/types/business'
import { platformNames } from '@/types/business'

const route = useRoute()
const router = useRouter()
const editorContent = ref<globalThis.HTMLTextAreaElement>()
const articles = ref<Article[]>([])
const selectedArticleId = ref<number>()
const article = ref<Article>()
const variants = ref<Variant[]>([])
const media = ref<MediaAsset[]>([])
const accounts = ref<PlatformAccount[]>([])
const activePlatform = ref<Platform>('WEIBO')
const selectedVersionId = ref<number>()
const comparisonVersionId = ref<number>()
const showComparison = ref(false)
const generationTask = ref<GenerationTask>()
const generating = ref(false)
const reviewing = ref(false)
const reviewResult = ref<Record<string, unknown>>()
const saved = ref(true)
const savedToast = ref(false)
let pollingSequence = 0

const options = reactive({
  platforms: ['WEIBO', 'XIAOHONGSHU', 'WECHAT_OFFICIAL'] as Platform[],
  style: '专业自然',
  length: 'MEDIUM' as 'SHORT' | 'MEDIUM' | 'LONG',
  target_audience: '',
  include_emoji: true,
  include_hashtags: true,
  preserve_meaning: 90,
})
const editing = reactive({ title: '', content_text: '', hashtags: [] as string[] })
const preferenceKey = (articleId: number) => `contentpilot_studio_preferences:${articleId}`

const activeVersions = computed(() =>
  variants.value
    .filter((item) => item.platform === activePlatform.value)
    .sort((a, b) => b.versionNo - a.versionNo),
)
const current = computed(
  () =>
    activeVersions.value.find((item) => item.id === selectedVersionId.value) ||
    activeVersions.value[0],
)
const comparisonVersion = computed(() =>
  activeVersions.value.find((item) => item.id === comparisonVersionId.value),
)
const previewText = computed(
  () => editing.content_text || '生成或编辑内容后，平台预览会显示在这里。',
)
const currentAccount = computed(() =>
  accounts.value.find((item) => item.platform === activePlatform.value),
)
const previewMedia = computed(() => [
  ...media.value.filter((item) => item.usageType === 'COVER'),
  ...media.value.filter((item) => item.usageType === 'BODY'),
])
const terminalTask = computed(() =>
  generationTask.value
    ? ['SUCCESS', 'PARTIAL_SUCCESS', 'FAILED'].includes(generationTask.value.status)
    : true,
)
const progressEntries = computed(() =>
  options.platforms.map((platform) => ({
    platform,
    state: generationTask.value?.platformStatusJson?.[platform] || {
      status: 'PENDING' as const,
      progress: 0,
      attempt: 0,
      durationMs: 0,
      tokenUsage: 0,
    },
  })),
)
const qualityDimensions = computed<Array<[string, string | number]>>(() => {
  const detail = reviewResult.value || {}
  const value = (camelCase: string, snakeCase: string): string | number => {
    const result = detail[camelCase] ?? detail[snakeCase]
    return typeof result === 'string' || typeof result === 'number' ? result : '-'
  }
  return [
    ['事实一致性', value('factualConsistency', 'factual_consistency')],
    ['信息完整度', value('informationCompleteness', 'information_completeness')],
    ['平台适配度', value('platformFit', 'platform_fit')],
    ['可读性', value('readability', 'readability')],
    ['格式合规性', value('formatCompliance', 'format_compliance')],
  ]
})

function formatDuration(milliseconds: number) {
  if (!milliseconds) return '计算中'
  return milliseconds >= 1000 ? `${(milliseconds / 1000).toFixed(1)} 秒` : `${milliseconds} 毫秒`
}

function persistPreferences() {
  if (!selectedArticleId.value) return
  window.sessionStorage.setItem(
    preferenceKey(selectedArticleId.value),
    JSON.stringify({
      options: { ...options, platforms: [...options.platforms] },
      activePlatform: activePlatform.value,
    }),
  )
}

function restorePreferences(articleId: number) {
  const raw = window.sessionStorage.getItem(preferenceKey(articleId))
  if (!raw) return
  try {
    const value = JSON.parse(raw)
    if (value.options) Object.assign(options, value.options)
    if (value.activePlatform) activePlatform.value = value.activePlatform
  } catch {
    window.sessionStorage.removeItem(preferenceKey(articleId))
  }
}

function sleep(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

async function loadArticles() {
  const data = await workflowApi.articles({ page_size: 100 })
  articles.value = data.items
  const queryId = Number(route.query.article)
  selectedArticleId.value = data.items.some((item) => item.id === queryId)
    ? queryId
    : data.items[0]?.id
  if (selectedArticleId.value) await loadArticle()
}

async function loadArticle() {
  if (!selectedArticleId.value) return
  const [articleData, accountData, mediaData] = await Promise.all([
    workflowApi.article(selectedArticleId.value),
    workflowApi.platformAccounts(),
    workflowApi.articleMedia(selectedArticleId.value),
  ])
  article.value = articleData
  variants.value = articleData.variants || (await workflowApi.variants(selectedArticleId.value))
  accounts.value = accountData
  media.value = mediaData
  options.target_audience = articleData.targetAudience || ''
  restorePreferences(articleData.id)
  selectedVersionId.value = undefined
  syncEditor()
}

function syncEditor() {
  editing.title = current.value?.title || ''
  editing.content_text = current.value?.contentText || ''
  editing.hashtags = [...(current.value?.hashtagsJson || [])]
  reviewResult.value = current.value?.reviewDetailJson
  if (!comparisonVersionId.value || comparisonVersionId.value === current.value?.id) {
    comparisonVersionId.value = activeVersions.value.find(
      (item) => item.id !== current.value?.id,
    )?.id
  }
  saved.value = true
}

async function pollTask(taskId: string) {
  const sequence = ++pollingSequence
  for (let attempt = 0; attempt < 240 && sequence === pollingSequence; attempt += 1) {
    const result = await workflowApi.task(taskId)
    generationTask.value = result
    if (result.variants?.length) {
      const byId = new Map(variants.value.map((item) => [item.id, item]))
      result.variants.forEach((item) => byId.set(item.id, item))
      variants.value = [...byId.values()]
    }
    if (['SUCCESS', 'PARTIAL_SUCCESS', 'FAILED'].includes(result.status)) {
      if (selectedArticleId.value)
        variants.value = await workflowApi.variants(selectedArticleId.value)
      selectedVersionId.value = undefined
      syncEditor()
      return result
    }
    await sleep(400)
  }
  throw new Error('生成任务轮询超时')
}

async function generate() {
  if (!selectedArticleId.value || !options.platforms.length) {
    ElMessage.warning('请选择原文和目标平台')
    return
  }
  generating.value = true
  generationTask.value = undefined
  try {
    const task = await workflowApi.generate({ article_id: selectedArticleId.value, ...options })
    const result = await pollTask(task.taskId)
    activePlatform.value = options.platforms[0]
    if (result.status === 'PARTIAL_SUCCESS')
      ElMessage.warning('部分平台生成成功，可单独重试失败平台')
    else if (result.status === 'FAILED') ElMessage.error('所有平台均生成失败')
    else ElMessage.success('平台版本已生成')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '生成失败'))
  } finally {
    generating.value = false
  }
}

async function retryFailed(platform: Platform) {
  if (!generationTask.value) return
  generating.value = true
  try {
    const task = await workflowApi.retryTaskPlatform(generationTask.value.id, platform)
    options.platforms = [platform]
    await pollTask(task.taskId)
    activePlatform.value = platform
    ElMessage.success(`${platformNames[platform]}已重新生成`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '平台重试失败'))
  } finally {
    generating.value = false
  }
}

async function save() {
  if (!current.value) return
  const value = await workflowApi.updateVariant(current.value.id, editing)
  variants.value = variants.value.map((item) => (item.id === value.id ? value : item))
  saved.value = true
  savedToast.value = true
  window.setTimeout(() => (savedToast.value = false), 1800)
}

async function approve() {
  if (!current.value) return
  const value = await workflowApi.approveVariant(current.value.id)
  variants.value = variants.value.map((item) => (item.id === value.id ? value : item))
  ElMessage.success('已审核通过')
}

async function reject() {
  if (!current.value) return
  const value = await workflowApi.rejectVariant(current.value.id)
  variants.value = variants.value.map((item) => (item.id === value.id ? value : item))
  ElMessage.success('版本已拒绝')
}

async function deleteVersion() {
  if (!current.value) return
  await ElMessageBox.confirm(`确定删除版本 ${current.value.versionNo}？`, '删除历史版本', {
    type: 'warning',
  })
  const id = current.value.id
  await workflowApi.deleteVariant(id)
  variants.value = variants.value.filter((item) => item.id !== id)
  selectedVersionId.value = undefined
  syncEditor()
  ElMessage.success('版本已删除')
}

async function regenerate() {
  if (!current.value) return
  generating.value = true
  try {
    const task = await workflowApi.regenerate(current.value.id)
    options.platforms = [current.value.platform]
    await pollTask(task.taskId)
    ElMessage.success('单平台版本已重新生成')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    generating.value = false
  }
}

async function reviewQuality() {
  if (!current.value) return
  reviewing.value = true
  try {
    reviewResult.value = await workflowApi.reviewVariant(current.value.id)
    ElMessage.success('质量评审完成')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '质量评审失败'))
  } finally {
    reviewing.value = false
  }
}

async function copy() {
  await navigator.clipboard.writeText(
    `${editing.title}\n\n${editing.content_text}\n\n${editing.hashtags.join(' ')}`,
  )
  ElMessage.success('已复制')
}

function focusEditor() {
  editorContent.value?.focus()
}

function openMedia() {
  if (!selectedArticleId.value) {
    ElMessage.warning('请先选择原文')
    return
  }
  persistPreferences()
  void router.push({
    name: 'media',
    query: { article: selectedArticleId.value, returnTo: 'studio' },
  })
}

function scheduleCurrent() {
  if (!article.value || !current.value) return
  persistPreferences()
  void router.push({
    name: 'calendar',
    query: { create: '1', article: article.value.id, variant: current.value.id },
  })
}

watch(current, syncEditor)
watch(activePlatform, () => {
  selectedVersionId.value = undefined
  syncEditor()
})
watch(
  editing,
  () => {
    saved.value = false
  },
  { deep: true, flush: 'sync' },
)
onBeforeUnmount(() => {
  pollingSequence += 1
})
onMounted(() => loadArticles().catch((error) => ElMessage.error(getApiErrorMessage(error))))
</script>

<template>
  <div class="studio-page">
    <Toast :visible="savedToast" message="内容已保存" @close="savedToast = false" />
    <PageHeader
      title="内容工作室"
      description="按平台并行改写、实时查看进度，并管理每个平台的历史版本。"
    >
      <span class="save-state">{{ saved ? '已保存' : '有未保存修改' }}</span>
      <el-button :disabled="!current" @click="save"><Save :size="15" class="mr-1" />保存</el-button>
      <el-button type="primary" :loading="generating" @click="generate">
        <Send :size="15" class="mr-1" />生成平台版本
      </el-button>
    </PageHeader>

    <section v-if="generationTask" class="generation-progress" data-testid="generation-progress">
      <header>
        <div>
          <strong>生成进度 · {{ generationTask.status }}</strong>
          <span>{{ generationTask.provider }} / {{ generationTask.modelName }}</span>
          <small v-if="terminalTask" class="generation-metrics">
            {{ generationTask.tokenUsage }} Token · {{ formatDuration(generationTask.durationMs) }}
          </small>
        </div>
        <span>{{ generationTask.progress }}%</span>
      </header>
      <div class="generation-progress-grid">
        <article
          v-for="item in progressEntries"
          :key="item.platform"
          :data-testid="`platform-progress-${item.platform}`"
        >
          <PlatformIcon :platform="item.platform" size="sm" />
          <div>
            <b>{{ platformNames[item.platform] }}</b>
            <span>{{ item.state.status }} · {{ item.state.progress }}%</span>
            <small v-if="item.state.error">{{ item.state.error }}</small>
          </div>
          <el-button
            v-if="item.state.status === 'FAILED' && terminalTask"
            size="small"
            @click="retryFailed(item.platform)"
            >重试</el-button
          >
        </article>
      </div>
    </section>

    <div v-if="articles.length" class="composer-shell">
      <aside class="composer-settings">
        <div class="composer-section">
          <label>原文</label>
          <el-select v-model="selectedArticleId" filterable class="w-full" @change="loadArticle">
            <el-option
              v-for="item in articles"
              :key="item.id"
              :label="item.title"
              :value="item.id"
            />
          </el-select>
          <p v-if="article" class="source-excerpt">{{ article.sourceText }}</p>
        </div>
        <div class="composer-section">
          <label>目标平台</label>
          <div class="platform-checks">
            <label v-for="(name, key) in platformNames" :key="key">
              <el-checkbox v-model="options.platforms" :value="key" />
              <PlatformIcon :platform="key" size="sm" /><span>{{ name }}</span>
            </label>
          </div>
        </div>
        <div class="composer-section">
          <label>表达风格</label>
          <el-select v-model="options.style" class="w-full" data-testid="style-control">
            <el-option label="专业自然" value="专业自然" />
            <el-option label="轻松亲切" value="轻松亲切" />
            <el-option label="简洁有力" value="简洁有力" />
            <el-option label="故事叙述" value="故事叙述" />
          </el-select>
        </div>
        <div class="composer-section">
          <label>内容长度</label>
          <el-segmented
            v-model="options.length"
            :options="[
              { label: '精简', value: 'SHORT' },
              { label: '标准', value: 'MEDIUM' },
              { label: '详细', value: 'LONG' },
            ]"
            data-testid="length-control"
          />
        </div>
        <div class="composer-section">
          <label>目标受众</label>
          <el-input v-model="options.target_audience" placeholder="例如：校园新媒体运营者" />
        </div>
        <div class="composer-section">
          <label>原意保留程度 · {{ options.preserve_meaning }}%</label>
          <el-slider
            v-model="options.preserve_meaning"
            :min="50"
            :max="100"
            :step="5"
            data-testid="preserve-control"
          />
        </div>
        <div class="composer-section">
          <label>生成选项</label>
          <el-switch v-model="options.include_emoji" active-text="适量 Emoji" /><br />
          <el-switch v-model="options.include_hashtags" active-text="平台标签" />
        </div>
      </aside>

      <main class="composer-editor">
        <div class="editor-toolbar">
          <button title="定位到正文" @click="focusEditor"><Type :size="16" /></button>
          <button title="选择图片" @click="openMedia"><ImagePlus :size="16" /></button>
          <span />
          <small>{{ editing.content_text.length }} 字</small>
        </div>
        <div v-if="current" class="editor-body">
          <input v-model="editing.title" class="editor-title" placeholder="标题" />
          <textarea
            ref="editorContent"
            v-model="editing.content_text"
            class="editor-content"
            placeholder="在这里编辑平台内容…"
          />
          <el-select
            v-model="editing.hashtags"
            multiple
            allow-create
            filterable
            class="editor-tags"
            placeholder="添加标签"
          />
          <div class="editor-footer">
            <div class="editor-meta">
              <StatusBadge :status="current.reviewStatus" />
              <span>版本 {{ current.versionNo }}</span
              ><span>质量 {{ current.qualityScore }}</span>
              <span>人工修改 {{ current.manualEditRatio }}%</span>
            </div>
            <div class="editor-actions">
              <button title="复制" @click="copy"><Clipboard :size="15" /></button>
              <button title="单平台重新生成" :disabled="generating" @click="regenerate">
                <RefreshCw :size="15" />
              </button>
              <el-button size="small" :loading="reviewing" @click="reviewQuality"
                >质量评审</el-button
              >
              <el-button size="small" @click="reject"><X :size="14" />拒绝</el-button>
              <el-button type="success" plain size="small" @click="approve">
                <Check :size="14" />审核通过
              </el-button>
              <el-button
                v-if="current.reviewStatus === 'APPROVED'"
                type="primary"
                size="small"
                data-testid="schedule-current"
                @click="scheduleCurrent"
              >
                <CalendarClock :size="14" />安排发布
              </el-button>
            </div>
          </div>
          <div v-if="reviewResult" class="quality-summary">
            <span v-for="item in qualityDimensions" :key="item[0]"
              >{{ item[0] }} {{ item[1] }}</span
            >
          </div>
          <div class="version-history" data-testid="version-history">
            <header>
              <strong>历史版本</strong>
              <button
                v-if="activeVersions.length > 1"
                data-testid="compare-versions"
                @click="showComparison = !showComparison"
              >
                {{ showComparison ? '收起对比' : '版本对比' }}
              </button>
              <span>{{ activeVersions.length }}</span>
            </header>
            <button
              v-for="item in activeVersions"
              :key="item.id"
              :class="{ active: item.id === current.id }"
              @click="selectedVersionId = item.id"
            >
              <span>V{{ item.versionNo }} · {{ item.modelName }}</span>
              <small>{{ item.reviewStatus }} · {{ item.generationDurationMs }}ms</small>
            </button>
            <el-button v-if="current" plain type="danger" size="small" @click="deleteVersion">
              <Trash2 :size="14" />删除当前版本
            </el-button>
            <div v-if="showComparison && comparisonVersion" class="version-comparison">
              <el-select v-model="comparisonVersionId" size="small" aria-label="选择对比版本">
                <el-option
                  v-for="item in activeVersions.filter((version) => version.id !== current?.id)"
                  :key="item.id"
                  :label="`V${item.versionNo}`"
                  :value="item.id"
                />
              </el-select>
              <div>
                <article>
                  <b>当前 V{{ current?.versionNo }}</b>
                  <p>{{ editing.content_text }}</p>
                </article>
                <article>
                  <b>对比 V{{ comparisonVersion.versionNo }}</b>
                  <p>{{ comparisonVersion.contentText }}</p>
                </article>
              </div>
            </div>
          </div>
        </div>
        <EmptyState v-else title="还没有平台版本"
          ><template #icon><FileText /></template
        ></EmptyState>
      </main>

      <aside class="composer-preview">
        <div class="preview-tabs">
          <button
            v-for="(name, key) in platformNames"
            :key="key"
            :class="{ active: activePlatform === key }"
            @click="activePlatform = key"
          >
            <PlatformIcon :platform="key" size="sm" />{{ name }}
          </button>
        </div>
        <div class="preview-canvas">
          <div class="platform-preview" :class="`preview-${activePlatform.toLowerCase()}`">
            <div class="preview-account">
              <PlatformIcon :platform="activePlatform" />
              <div>
                <b>{{ currentAccount?.accountName || '未配置平台账号' }}</b
                ><span>预览</span>
              </div>
            </div>
            <h3 v-if="editing.title">{{ editing.title }}</h3>
            <p>{{ previewText }}</p>
            <div v-if="editing.hashtags.length" class="preview-tags">
              {{ editing.hashtags.join(' ') }}
            </div>
            <div v-if="previewMedia.length" class="preview-images">
              <img
                v-for="item in previewMedia"
                :key="item.id"
                :src="item.thumbnailUrl || item.imageUrl"
                :alt="item.altText || '文章配图'"
              />
            </div>
            <div v-else class="preview-placeholder">尚未选择图片</div>
            <footer><span>喜欢</span><span>评论</span><span>分享</span></footer>
          </div>
        </div>
      </aside>
    </div>
    <EmptyState v-else title="先创建一篇原文"
      ><template #icon><FilePlus2 /></template
    ></EmptyState>
  </div>
</template>
