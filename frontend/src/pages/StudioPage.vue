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
  Images,
  LayoutTemplate,
  RefreshCw,
  Save,
  Send,
  Sparkles,
  Trash2,
  Type,
  X,
  WandSparkles,
} from 'lucide-vue-next'
import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import PlatformIcon from '@/components/PlatformIcon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import Toast from '@/components/Toast.vue'
import WechatFormatterDialog from '@/components/WechatFormatterDialog.vue'
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
const showWechatFormatter = ref(false)
const visualMode = ref<'SEARCH' | 'GENERATE' | 'TRANSFORM'>('SEARCH')
const visualLoading = ref(false)
const visualNotice = ref('')
const visualKeyword = ref('')
const visualPrompt = ref('')
const imageSearchResults = ref<Array<Record<string, unknown>>>([])
const textImageModels = ref<string[]>([])
const editImageModels = ref<string[]>([])
const textImageModel = ref('Qwen/Qwen-Image')
const editImageModel = ref('Qwen/Qwen-Image-Edit-2509')
const imageSize = ref('1328x1328')
const transformAssetId = ref<number>()
const clock = ref(Date.now())
const operationStartedAt = ref<number>()
let pollingSequence = 0
let clockTimer: number | undefined

const options = reactive({
  platforms: ['WEIBO', 'XIAOHONGSHU', 'WECHAT_OFFICIAL'] as Platform[],
  style: '专业自然',
  length: 'MEDIUM' as 'SHORT' | 'MEDIUM' | 'LONG',
  target_audience: '',
  include_emoji: true,
  include_hashtags: true,
  preserve_meaning: 90,
  generation_mode: 'QUICK' as 'QUICK' | 'DEEP',
  creative_goal: '知识分享',
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
function cleanVisibleMarkdown(value: string) {
  return value
    .replace(/\*\*([^*\n]+)\*\*/g, '$1')
    .replace(/^\s*\*\s+/gm, '• ')
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1$2')
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

const previewHtml = computed(() => {
  const content = editing.content_text || '生成或编辑内容后，平台预览会显示在这里。'
  return escapeHtml(content)
    .replace(/^###\s+(.+)$/gm, '<h5>$1</h5>')
    .replace(/^##\s+(.+)$/gm, '<h4>$1</h4>')
    .replace(/^#\s+(.+)$/gm, '<h3>$1</h3>')
    .replace(/^•\s+(.+)$/gm, '<div class="preview-list-item">• $1</div>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>')
})
const currentAccount = computed(() =>
  accounts.value.find((item) => item.platform === activePlatform.value),
)
const previewMedia = computed(() => [
  ...media.value.filter((item) => item.selected !== false && item.usageType === 'COVER'),
  ...media.value.filter((item) => item.selected !== false && item.usageType === 'BODY'),
])
const terminalTask = computed(() =>
  generationTask.value
    ? ['SUCCESS', 'PARTIAL_SUCCESS', 'FAILED'].includes(generationTask.value.status)
    : true,
)
const taskPlatforms = computed(() => generationTask.value?.platformsJson || options.platforms)
const progressEntries = computed(() =>
  taskPlatforms.value.map((platform) => ({
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
const completedPlatformCount = computed(
  () =>
    progressEntries.value.filter((item) => ['SUCCESS', 'FAILED'].includes(item.state.status))
      .length,
)
const taskElapsedMs = computed(() => {
  if (terminalTask.value) return generationTask.value?.durationMs || 0
  const createdAt = generationTask.value?.createdAt
    ? Date.parse(generationTask.value.createdAt)
    : Number.NaN
  const startedAt = Number.isNaN(createdAt) ? operationStartedAt.value : createdAt
  return startedAt ? Math.max(0, clock.value - startedAt) : 0
})
const lastProgressAt = computed(() => {
  const timestamps = progressEntries.value
    .map((item) => item.state.updatedAt)
    .filter((value): value is string => Boolean(value))
    .map((value) => Date.parse(value))
    .filter((value) => !Number.isNaN(value))
  const taskUpdatedAt = generationTask.value?.updatedAt
    ? Date.parse(generationTask.value.updatedAt)
    : Number.NaN
  if (!Number.isNaN(taskUpdatedAt)) timestamps.push(taskUpdatedAt)
  return timestamps.length ? Math.max(...timestamps) : undefined
})
const taskStatusLabel = computed(() => {
  const labels: Record<GenerationTask['status'], string> = {
    PENDING: '等待开始',
    RUNNING: '正在生成',
    SUCCESS: '全部完成',
    PARTIAL_SUCCESS: '部分完成',
    FAILED: '生成失败',
  }
  return generationTask.value ? labels[generationTask.value.status] : '等待开始'
})
const waitHint = computed(() => {
  if (!generationTask.value) return ''
  if (generationTask.value.status === 'PARTIAL_SUCCESS')
    return '成功的平台结果已经保留；失败的平台可以单独重试。'
  if (generationTask.value.status === 'FAILED') return '任务已结束，请查看各平台失败原因后重试。'
  if (generationTask.value.status === 'SUCCESS') return '平台结果已自动刷新，可以继续编辑和审核。'
  if (progressEntries.value.some((item) => item.state.status === 'RETRYING'))
    return '有平台输出未通过校验，系统正在自动修正并重试。'
  if (taskElapsedMs.value >= 45_000)
    return '模型响应时间较长，系统仍在等待；无需重复提交，失败时会显示具体原因。'
  if (progressEntries.value.some((item) => item.state.stage === 'REQUESTING_MODEL'))
    return '模型正在生成内容，耗时会受文章长度和服务商负载影响。'
  return '任务会自动刷新每个平台的处理阶段，无需重复点击生成。'
})
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

function platformStatusLabel(status: string) {
  return (
    {
      PENDING: '排队中',
      RUNNING: '处理中',
      RETRYING: '自动重试',
      SUCCESS: '已完成',
      FAILED: '失败',
    }[status] || status
  )
}

function formatLastUpdate(timestamp?: number) {
  if (!timestamp) return '等待首次进度'
  const seconds = Math.max(0, Math.floor((clock.value - timestamp) / 1000))
  return seconds < 2 ? '刚刚更新' : `${seconds} 秒前更新`
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
  transformAssetId.value = mediaData[0]?.id
  visualKeyword.value = articleData.topic || articleData.title
  visualPrompt.value = `为文章《${articleData.title}》创作一张专业、真实、具有编辑感的配图，无文字、无水印、无品牌 Logo。${articleData.summary || articleData.topic || ''}`
  void searchVisuals()
  options.target_audience = articleData.targetAudience || ''
  restorePreferences(articleData.id)
  if (route.query.mode === 'deep') options.generation_mode = 'DEEP'
  selectedVersionId.value = undefined
  syncEditor()
}

function syncEditor() {
  editing.title = cleanVisibleMarkdown(current.value?.title || '')
  editing.content_text = cleanVisibleMarkdown(current.value?.contentText || '')
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
  for (let attempt = 0; attempt < 1200 && sequence === pollingSequence; attempt += 1) {
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
  operationStartedAt.value = Date.now()
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
  operationStartedAt.value = Date.now()
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
  operationStartedAt.value = Date.now()
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

async function openWechatFormatter() {
  if (!current.value || current.value.platform !== 'WECHAT_OFFICIAL') return
  try {
    if (!saved.value) await save()
    showWechatFormatter.value = true
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '请先保存正文后再进行排版'))
  }
}

function applyWechatFormatting(value: Variant) {
  variants.value = variants.value.map((item) => (item.id === value.id ? value : item))
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

async function loadImageModels() {
  if (textImageModels.value.length || editImageModels.value.length) return
  try {
    const data = await workflowApi.imageModels()
    textImageModels.value = data.textToImage
    editImageModels.value = data.imageToImage
    if (!data.textToImage.includes(textImageModel.value) && data.textToImage[0])
      textImageModel.value = data.textToImage[0]
    if (!data.imageToImage.includes(editImageModel.value) && data.imageToImage[0])
      editImageModel.value = data.imageToImage[0]
  } catch (error) {
    visualNotice.value = getApiErrorMessage(error, '读取图片模型失败')
  }
}

async function searchVisuals() {
  if (!visualKeyword.value.trim()) return
  visualLoading.value = true
  try {
    const data = await workflowApi.searchMedia(visualKeyword.value.trim())
    imageSearchResults.value = data.items.slice(0, 6)
    visualNotice.value = data.notice
  } catch (error) {
    visualNotice.value = getApiErrorMessage(error, '图片搜索失败')
  } finally {
    visualLoading.value = false
  }
}

async function selectVisual(item: Record<string, unknown>, usageType: 'COVER' | 'BODY') {
  if (!selectedArticleId.value) return
  visualLoading.value = true
  try {
    await workflowApi.selectMedia({
      article_id: selectedArticleId.value,
      variant_id: current.value?.id,
      source: item.source,
      source_id: item.id,
      image_url: item.imageUrl,
      thumbnail_url: item.thumbnailUrl,
      photographer_name: item.photographerName,
      photographer_url: item.photographerUrl,
      alt_text: item.altText,
      search_keyword: visualKeyword.value,
      usage_type: usageType,
    })
    media.value = await workflowApi.articleMedia(selectedArticleId.value)
    transformAssetId.value = media.value[0]?.id
    ElMessage.success(usageType === 'COVER' ? '已设为封面' : '已加入正文')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '选择图片失败'))
  } finally {
    visualLoading.value = false
  }
}

async function generateVisual() {
  if (!selectedArticleId.value || !visualPrompt.value.trim()) return
  visualLoading.value = true
  try {
    await workflowApi.generateImage({
      article_id: selectedArticleId.value,
      prompt: visualPrompt.value.trim(),
      model: textImageModel.value,
      image_size: imageSize.value,
      usage_type: 'COVER',
    })
    media.value = await workflowApi.articleMedia(selectedArticleId.value)
    transformAssetId.value = media.value[0]?.id
    ElMessage.success('AI 配图已生成并设为封面')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, 'AI 图片生成失败'))
  } finally {
    visualLoading.value = false
  }
}

async function transformVisual() {
  if (!selectedArticleId.value || !transformAssetId.value || !visualPrompt.value.trim()) return
  visualLoading.value = true
  try {
    await workflowApi.transformImage({
      article_id: selectedArticleId.value,
      asset_id: transformAssetId.value,
      prompt: visualPrompt.value.trim(),
      model: editImageModel.value,
      usage_type: 'COVER',
    })
    media.value = await workflowApi.articleMedia(selectedArticleId.value)
    transformAssetId.value = media.value[0]?.id
    ElMessage.success('AI 图片改造完成并设为封面')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, 'AI 图片改造失败'))
  } finally {
    visualLoading.value = false
  }
}

watch(visualMode, (mode) => {
  if (mode === 'SEARCH' && !imageSearchResults.value.length) void searchVisuals()
  if (mode !== 'SEARCH') void loadImageModels()
})

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
  if (clockTimer) window.clearInterval(clockTimer)
})
onMounted(() => {
  clockTimer = window.setInterval(() => (clock.value = Date.now()), 1000)
  loadArticles().catch((error) => ElMessage.error(getApiErrorMessage(error)))
})
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
        <Send :size="15" class="mr-1" />{{
          generating
            ? '正在生成…'
            : options.generation_mode === 'DEEP'
              ? '开始深度创作'
              : '生成平台版本'
        }}
      </el-button>
    </PageHeader>

    <section v-if="generationTask" class="generation-progress" data-testid="generation-progress">
      <header>
        <div>
          <strong>{{ taskStatusLabel }}</strong>
          <span>
            {{ completedPlatformCount }}/{{ progressEntries.length }} 个平台处理完成 · 已用时
            {{ formatDuration(taskElapsedMs) }}
          </span>
          <small v-if="terminalTask" class="generation-metrics">
            {{ generationTask.provider }} / {{ generationTask.modelName }} ·
            {{ generationTask.tokenUsage }} Token
          </small>
        </div>
        <strong class="generation-percentage">{{ generationTask.progress }}%</strong>
      </header>
      <div class="generation-overall-track" aria-label="任务总进度">
        <span :style="{ width: `${generationTask.progress}%` }" />
      </div>
      <div class="generation-wait-hint" data-testid="generation-wait-hint">
        <span>{{ waitHint }}</span>
        <small>{{ formatLastUpdate(lastProgressAt) }} · 进度按真实处理阶段计算</small>
      </div>
      <div class="generation-progress-grid">
        <article
          v-for="item in progressEntries"
          :key="item.platform"
          :data-testid="`platform-progress-${item.platform}`"
        >
          <PlatformIcon :platform="item.platform" size="sm" />
          <div class="platform-progress-content">
            <div class="platform-progress-heading">
              <b>{{ platformNames[item.platform] }}</b>
              <span :class="`status-${item.state.status.toLowerCase()}`">
                {{ platformStatusLabel(item.state.status) }} · {{ item.state.progress }}%
              </span>
            </div>
            <span class="platform-stage">{{ item.state.message || '等待开始处理' }}</span>
            <div class="platform-progress-track">
              <span :style="{ width: `${item.state.progress}%` }" />
            </div>
            <small v-if="item.state.attempt > 1">第 {{ item.state.attempt }} 次尝试</small>
            <small v-if="item.state.status === 'SUCCESS'">
              {{ formatDuration(item.state.durationMs) }} · {{ item.state.tokenUsage }} Token
            </small>
            <small v-if="item.state.error" class="platform-error">{{ item.state.error }}</small>
          </div>
          <el-button
            v-if="item.state.status === 'FAILED' && terminalTask"
            size="small"
            @click="retryFailed(item.platform)"
            >重试</el-button
          >
        </article>
      </div>
      <div
        v-if="
          options.generation_mode === 'DEEP' && progressEntries.some((item) => item.state.strategy)
        "
        class="deep-insight-grid"
        data-testid="deep-insights"
      >
        <article
          v-for="item in progressEntries.filter((entry) => entry.state.strategy)"
          :key="item.platform"
        >
          <header>
            <PlatformIcon :platform="item.platform" size="sm" /><b
              >{{ platformNames[item.platform] }} 创作策略</b
            >
          </header>
          <p><strong>切入角度：</strong>{{ item.state.strategy?.angle }}</p>
          <p><strong>开场钩子：</strong>{{ item.state.strategy?.hook }}</p>
          <p><strong>读者价值：</strong>{{ item.state.strategy?.reader_value }}</p>
          <small v-if="item.state.candidateTitles?.length">
            候选：{{ item.state.candidateTitles.join(' / ') }}
            <template v-if="item.state.selectedCandidate !== undefined">
              · AI 选择第 {{ item.state.selectedCandidate + 1 }} 稿</template
            >
          </small>
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
          <label>创作模式</label>
          <el-segmented
            v-model="options.generation_mode"
            :options="[
              { label: '快速改写', value: 'QUICK' },
              { label: '深度创作', value: 'DEEP' },
            ]"
            data-testid="generation-mode-control"
          />
          <p class="mode-description">
            {{
              options.generation_mode === 'DEEP'
                ? '分析事实边界，策划角度，生成两稿并由 AI 主编评审修订。'
                : '一次生成，适合已有成熟原稿的快速平台适配。'
            }}
          </p>
        </div>
        <div v-if="options.generation_mode === 'DEEP'" class="composer-section">
          <label>本次创作目标</label>
          <el-select v-model="options.creative_goal" class="w-full">
            <el-option label="知识分享" value="知识分享" />
            <el-option label="引发讨论" value="引发讨论" />
            <el-option label="提升收藏" value="提升收藏" />
            <el-option label="品牌表达" value="品牌表达" />
          </el-select>
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
              <el-button
                v-if="current.platform === 'WECHAT_OFFICIAL'"
                plain
                size="small"
                data-testid="open-wechat-formatter"
                @click="openWechatFormatter"
              >
                <LayoutTemplate :size="14" />公众号排版
              </el-button>
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
            <!-- 内容先经过 escapeHtml，再转换受限 Markdown；不接受原始 HTML。 -->
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div class="preview-content" v-html="previewHtml" />
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
        <section class="visual-assistant" data-testid="visual-assistant">
          <header><Images :size="17" /><b>智能配图</b></header>
          <el-segmented
            v-model="visualMode"
            :options="[
              { label: '相关图片', value: 'SEARCH' },
              { label: 'AI 生成', value: 'GENERATE' },
              { label: 'AI 改造', value: 'TRANSFORM' },
            ]"
          />
          <template v-if="visualMode === 'SEARCH'">
            <div class="visual-search-row">
              <el-input
                v-model="visualKeyword"
                placeholder="输入图片关键词"
                @keyup.enter="searchVisuals"
              />
              <el-button :loading="visualLoading" @click="searchVisuals">搜索</el-button>
            </div>
            <small v-if="visualNotice">{{ visualNotice }}</small>
            <div class="visual-result-grid">
              <article v-for="item in imageSearchResults" :key="String(item.id)">
                <img :src="String(item.thumbnailUrl)" :alt="String(item.altText || '相关图片')" />
                <div>
                  <button @click="selectVisual(item, 'COVER')">封面</button
                  ><button @click="selectVisual(item, 'BODY')">正文</button>
                </div>
              </article>
            </div>
          </template>
          <template v-else-if="visualMode === 'GENERATE'">
            <el-input
              v-model="visualPrompt"
              type="textarea"
              :rows="4"
              placeholder="描述希望生成的图片"
            />
            <el-select v-model="textImageModel" class="w-full" placeholder="选择真实生图模型">
              <el-option
                v-for="model in textImageModels"
                :key="model"
                :label="model"
                :value="model"
              />
            </el-select>
            <el-select v-model="imageSize" class="w-full">
              <el-option label="方形 1:1" value="1328x1328" />
              <el-option label="横版 16:9" value="1664x928" />
              <el-option label="竖版 9:16" value="928x1664" />
            </el-select>
            <el-button
              type="primary"
              :loading="visualLoading"
              :disabled="!textImageModels.length"
              @click="generateVisual"
            >
              <Sparkles :size="15" class="mr-1" />生成并设为封面
            </el-button>
          </template>
          <template v-else>
            <el-select v-model="transformAssetId" class="w-full" placeholder="选择要改造的图片">
              <el-option
                v-for="item in media"
                :key="item.id"
                :label="item.altText || `图片 ${item.id}`"
                :value="item.id"
              />
            </el-select>
            <el-input
              v-model="visualPrompt"
              type="textarea"
              :rows="4"
              placeholder="例如：改成清爽蓝色科技风，保留主体，不要文字"
            />
            <el-select v-model="editImageModel" class="w-full" placeholder="选择真实改图模型">
              <el-option
                v-for="model in editImageModels"
                :key="model"
                :label="model"
                :value="model"
              />
            </el-select>
            <el-button
              type="primary"
              :loading="visualLoading"
              :disabled="!transformAssetId || !editImageModels.length"
              @click="transformVisual"
            >
              <WandSparkles :size="15" class="mr-1" />生成改造版本
            </el-button>
          </template>
          <el-button text @click="openMedia">打开完整媒体库</el-button>
        </section>
      </aside>
    </div>
    <EmptyState v-else title="先创建一篇原文"
      ><template #icon><FilePlus2 /></template
    ></EmptyState>
    <WechatFormatterDialog
      v-model="showWechatFormatter"
      :variant="current"
      :content-text="editing.content_text"
      @applied="applyWechatFormatting"
    />
  </div>
</template>
