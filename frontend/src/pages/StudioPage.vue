<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import DOMPurify from 'dompurify'
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
import { useAuthStore } from '@/stores/auth'
import { useVariantDrafts, type VariantDraftPayload } from '@/composables/useVariantDrafts'
import { useGenerationPolling, type GenerationTicket } from '@/composables/useGenerationPolling'
import { useVisualTools } from '@/composables/useVisualTools'
import { generationOutcome } from '@/utils/task-outcome'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import PlatformIcon from '@/components/PlatformIcon.vue'
import ScheduleAdvisor from '@/components/ScheduleAdvisor.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import Toast from '@/components/Toast.vue'
import WechatFormatterDialog from '@/components/WechatFormatterDialog.vue'
import WeiboPreview from '@/components/platform-preview/WeiboPreview.vue'
import XiaohongshuPreview from '@/components/platform-preview/XiaohongshuPreview.vue'
import WechatPreview from '@/components/platform-preview/WechatPreview.vue'
import XPreview from '@/components/platform-preview/XPreview.vue'
import BlueskyPreview from '@/components/platform-preview/BlueskyPreview.vue'
import MastodonPreview from '@/components/platform-preview/MastodonPreview.vue'
import { buildMastodonText, mastodonLimits, mastodonTextLength } from '@/utils/mastodon'
import { blueskyTextLength, buildBlueskyText } from '@/utils/bluesky'
import ToutiaoPreview from '@/components/platform-preview/ToutiaoPreview.vue'
import type {
  Article,
  GenerationTask,
  MediaAsset,
  Platform,
  PlatformAccount,
  Variant,
  WechatFormatProfile,
} from '@/types/business'
import { platformNames } from '@/types/business'
import { presentOperationError } from '@/utils/operation-error'
import { xWeightedLength } from '@/utils/text'

const previewPlatformNames: Record<Platform, string> = {
  ...platformNames,
  WECHAT_OFFICIAL: '公众号',
  TOUTIAO: '头条',
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
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
const generationProgressExpanded = ref(false)
const deepWorkbenchExpanded = ref(false)
const workspaceLayout = ref<'PREVIEW' | 'EDIT'>('PREVIEW')
const composerWorkspace = ref<globalThis.HTMLElement>()
const deepWorkbenchPlatform = ref<Platform>('WEIBO')
const selectingCandidate = ref<number>()
const regeneratingDeepPlatform = ref(false)
const reviewing = ref(false)
const savingWechatDraft = ref(false)
const wechatDraftStartedAt = ref<number>()
const savingToutiaoDraft = ref(false)
const toutiaoDraftStartedAt = ref<number>()
const reviewResult = ref<Record<string, unknown>>()
const savedToast = ref(false)
const showWechatFormatter = ref(false)
const wechatPreviewHtml = ref('')
const wechatPreviewLoading = ref(false)
const clock = ref(Date.now())
const operationStartedAt = ref<number>()
let articleLoadSequence = 0
let loadedArticleId: number | undefined
let clockTimer: number | undefined
let wechatPreviewTimer: number | undefined
let wechatPreviewSequence = 0
const autoFittedWeiboVariantIds = new Set<number>()

const options = reactive({
  platforms: [
    'WEIBO',
    'XIAOHONGSHU',
    'WECHAT_OFFICIAL',
    'TOUTIAO',
    'X',
    'BLUESKY',
    'MASTODON',
  ] as Platform[],
  style: '专业自然',
  length: 'MEDIUM' as 'SHORT' | 'MEDIUM' | 'LONG',
  target_audience: '',
  include_emoji: true,
  include_hashtags: true,
  preserve_meaning: 90,
  generation_mode: 'QUICK' as 'QUICK' | 'DEEP',
  creative_goal: '知识分享',
  creative_requirements: '',
})
const editing = reactive({ title: '', content_text: '', hashtags: [] as string[] })
const defaultWechatProfile: WechatFormatProfile = {
  theme: 'clean',
  accent_color: '#1677ff',
  font_size: 16,
  line_height: 1.8,
  paragraph_spacing: 16,
  first_line_indent: false,
  link_footnotes: true,
}
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
const drafts = useVariantDrafts({
  current,
  editing,
  fromVariant: (variant) => ({
    title: cleanVisibleMarkdown(variant.title || ''),
    content_text: cleanVisibleMarkdown(variant.contentText || ''),
    hashtags: [...(variant.hashtagsJson || [])],
  }),
  update: (id, payload) => workflowApi.updateVariant(id, { ...payload }),
  onSaved: (value) => {
    variants.value = variants.value.map((item) => (item.id === value.id ? value : item))
  },
  errorMessage: (error) => getApiErrorMessage(error, '保存失败，草稿已保留在本机'),
})
const { saved, autosaveState, autosaveError, lastSavedAt, recoveryDraft } = drafts
const generationPolling = useGenerationPolling({
  articleId: () => selectedArticleId.value,
  fetchTask: (id) => workflowApi.task(id),
  fetchVariants: (id) => workflowApi.variants(id),
  onTask: (result) => {
    generationTask.value = result
    if (
      result.optionsJson?.generation_mode === 'DEEP' &&
      result.platformsJson[0] &&
      !result.platformsJson.includes(deepWorkbenchPlatform.value)
    ) {
      deepWorkbenchPlatform.value = result.platformsJson[0]
    }
    if (result.variants?.length) {
      const byId = new Map(variants.value.map((item) => [item.id, item]))
      result.variants.forEach((item) => byId.set(item.id, item))
      variants.value = [...byId.values()]
    }
  },
  onComplete: (_task, rows) => {
    variants.value = rows
    selectedVersionId.value = undefined
    syncEditor()
  },
})
const comparisonVersion = computed(() =>
  activeVersions.value.find((item) => item.id === comparisonVersionId.value),
)
const saveStateLabel = computed(() => {
  if (autosaveState.value === 'SAVING') return '正在自动保存…'
  if (autosaveState.value === 'ERROR') return '自动保存失败，草稿已留在本机'
  if (autosaveState.value === 'DIRTY') return '修改已暂存，等待自动保存'
  if (lastSavedAt.value) return '已自动保存'
  return saved.value ? '已保存' : '有未保存修改'
})
const wechatDraftElapsedSeconds = computed(() =>
  savingWechatDraft.value && wechatDraftStartedAt.value
    ? Math.max(0, Math.floor((clock.value - wechatDraftStartedAt.value) / 1000))
    : 0,
)
const wechatDraftProgressLabel = computed(() => {
  const seconds = wechatDraftElapsedSeconds.value
  if (seconds < 3) return '正在准备草稿'
  if (seconds < 15) return '正在打开公众号编辑器'
  if (seconds < 40) return '正在写入内容并保存'
  return '微信响应较慢，仍在等待'
})
const toutiaoDraftElapsedSeconds = computed(() =>
  savingToutiaoDraft.value && toutiaoDraftStartedAt.value
    ? Math.max(0, Math.floor((clock.value - toutiaoDraftStartedAt.value) / 1000))
    : 0,
)
const toutiaoDraftProgressLabel = computed(() => {
  const seconds = toutiaoDraftElapsedSeconds.value
  if (seconds < 3) return '正在准备草稿'
  if (seconds < 15) return '正在打开头条编辑器'
  if (seconds < 45) return '正在写入图文并等待云端保存'
  return '头条响应较慢，仍在确认草稿状态'
})

function snapshotEditing(): VariantDraftPayload {
  return {
    title: editing.title,
    content_text: editing.content_text,
    hashtags: [...editing.hashtags],
  }
}

function cleanVisibleMarkdown(value: string) {
  return value
    .replace(/#/g, '')
    .replace(/^[ \t]+/gm, '')
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
    .replace(/^(?:[一二三四五六七八九十]+、|\d+[、.])\s*(.+)$/gm, '<h4>$&</h4>')
    .replace(/^•\s+(.+)$/gm, '<div class="preview-list-item">• $1</div>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>')
})
const weiboPreviewTitle = computed(() => {
  const title = editing.title.trim()
  return title && !editing.content_text.trim().startsWith(title) ? title : ''
})
function buildWeiboPreviewText(title: string, content: string, hashtags: string[]) {
  const cleanTitle = title.trim()
  const cleanContent = content.trim()
  const hook = cleanTitle && !cleanContent.startsWith(cleanTitle) ? cleanTitle : ''
  const body = [hook, cleanContent].filter(Boolean).join('\n\n')
  const topics = hashtags
    .map((tag) => tag.replace(/#/g, '').trim())
    .filter(Boolean)
    .map((topic) => `#${topic}#`)
    .join(' ')
  return [body, topics].filter(Boolean).join('\n\n')
}
const weiboStatusLength = computed(() => {
  return buildWeiboPreviewText(editing.title, editing.content_text, editing.hashtags).length
})
const xStatusLength = computed(() => {
  const topics = editing.hashtags
    .map((tag) => tag.replace(/#/g, '').trim())
    .filter(Boolean)
    .map((topic) => `#${topic}`)
    .join(' ')
  return xWeightedLength([editing.content_text.trim(), topics].filter(Boolean).join('\n\n'))
})
const blueskyStatusLength = computed(() =>
  blueskyTextLength(buildBlueskyText(editing.title, editing.content_text, editing.hashtags)),
)

const mastodonStatusLength = computed(() =>
  mastodonTextLength(
    buildMastodonText(editing.title, editing.content_text, editing.hashtags),
    currentMastodonLimits.value.charactersReservedPerUrl,
  ),
)

function topicName(value: string) {
  return value.replace(/#/g, '').trim()
}

function fitWeiboDraftForImage() {
  if (
    activePlatform.value !== 'WEIBO' ||
    !previewMedia.value.length ||
    weiboStatusLength.value <= 140
  ) {
    return false
  }
  const title = editing.title.trim().slice(0, 32)
  const hashtags = editing.hashtags.map(topicName).filter(Boolean).slice(0, 2)
  let content = editing.content_text.trim()

  while (hashtags.length && buildWeiboPreviewText(title, content, hashtags).length > 140) {
    hashtags.pop()
  }
  if (buildWeiboPreviewText(title, content, hashtags).length > 140) {
    let low = 1
    let high = content.length
    let best = ''
    while (low <= high) {
      const middle = Math.floor((low + high) / 2)
      let candidate = content.slice(0, middle).replace(/[，、；：,. ]+$/u, '')
      if (middle < content.length) candidate += '…'
      if (buildWeiboPreviewText(title, candidate, hashtags).length <= 140) {
        best = candidate
        low = middle + 1
      } else {
        high = middle - 1
      }
    }
    content = best || content.slice(0, 1)
  }

  drafts.replaceEditing({ title, content_text: content, hashtags })
  drafts.stage()
  return true
}

function platformCopyText() {
  if (activePlatform.value === 'MASTODON') {
    return buildMastodonText(editing.title, editing.content_text, editing.hashtags)
  }
  if (activePlatform.value === 'BLUESKY') {
    return buildBlueskyText(editing.title, editing.content_text, editing.hashtags)
  }
  const topics = editing.hashtags.map(topicName).filter(Boolean)
  if (activePlatform.value === 'WEIBO') {
    const body = [weiboPreviewTitle.value, editing.content_text.trim()].filter(Boolean).join('\n\n')
    const topicText = topics.map((topic) => `#${topic}#`).join(' ')
    return [body, topicText].filter(Boolean).join('\n\n')
  }
  if (activePlatform.value === 'XIAOHONGSHU') {
    const topicText = topics.map((topic) => `#${topic}`).join(' ')
    return [editing.title.trim(), editing.content_text.trim(), topicText]
      .filter(Boolean)
      .join('\n\n')
  }
  if (activePlatform.value === 'X') {
    const topicText = topics.map((topic) => `#${topic}`).join(' ')
    return [editing.content_text.trim(), topicText].filter(Boolean).join('\n\n')
  }
  return [editing.title.trim(), editing.content_text.trim()].filter(Boolean).join('\n\n')
}

async function refreshWechatPreview() {
  const content = editing.content_text.trim()
  if (activePlatform.value !== 'WECHAT_OFFICIAL' || !content) {
    wechatPreviewHtml.value = ''
    wechatPreviewLoading.value = false
    return
  }
  const sequence = ++wechatPreviewSequence
  wechatPreviewLoading.value = true
  try {
    const profile = current.value?.formatProfileJson || defaultWechatProfile
    const result = await workflowApi.previewWechatFormat(content, profile)
    if (sequence !== wechatPreviewSequence) return
    wechatPreviewHtml.value = DOMPurify.sanitize(result.contentHtml, {
      USE_PROFILES: { html: true },
    })
  } catch (error) {
    if (sequence !== wechatPreviewSequence) return
    wechatPreviewHtml.value = previewHtml.value
    visualNotice.value = getApiErrorMessage(error, '公众号排版预览同步失败')
  } finally {
    if (sequence === wechatPreviewSequence) wechatPreviewLoading.value = false
  }
}

function scheduleWechatPreview() {
  if (wechatPreviewTimer) window.clearTimeout(wechatPreviewTimer)
  wechatPreviewTimer = window.setTimeout(() => {
    wechatPreviewTimer = undefined
    void refreshWechatPreview()
  }, 220)
}

const currentAccount = computed(() =>
  accounts.value.find((item) => item.platform === activePlatform.value),
)
const currentMastodonLimits = computed(() => mastodonLimits(currentAccount.value?.config))
const editorPlatformConfig = computed(
  () =>
    ({
      WEIBO: {
        titleLabel: '首句钩子',
        titlePlaceholder: '作为微博正文第一句发布',
        titleMax: 60,
        contentMax: 2000,
        contentHint: '无图超过 140 字时使用官方长文字参数；带图时总字符数不能超过 140',
        tagPlaceholder: '添加微博话题',
        tagHint: '发布时自动转换为 #话题#，正文无需输入井号',
      },
      XIAOHONGSHU: {
        titleLabel: '笔记标题',
        titlePlaceholder: '最多 20 个字',
        titleMax: 20,
        contentMax: 1000,
        contentHint: '正文最多 1000 字，发布时至少需要 1 张图片',
        tagPlaceholder: '添加小红书话题',
        tagHint: '话题与正文分开保存，发布时由平台适配器填写',
      },
      WECHAT_OFFICIAL: {
        titleLabel: '文章标题',
        titlePlaceholder: '最多 64 个字',
        titleMax: 64,
        contentMax: 30000,
        contentHint: '正文会转换为公众号安全富文本，并同步到草稿箱',
        tagPlaceholder: '添加后台关键词',
        tagHint: '关键词仅用于内容管理，不会显示在公众号正文中',
      },
      X: {
        titleLabel: '内部标题',
        titlePlaceholder: '仅用于 ContentPilot 内容管理',
        titleMax: 100,
        contentMax: 280,
        contentHint: `正文与标签当前合计约 ${xStatusLength.value}/280 字符，最终以 X 官方校验为准`,
        tagPlaceholder: '添加 X 话题',
        tagHint: '发布时自动转换为 #话题，内部标题不会单独发送',
      },
      BLUESKY: {
        titleLabel: '首句标题',
        titlePlaceholder: '标题会与正文合并发送',
        titleMax: 100,
        contentMax: 2000,
        contentHint: `标题、正文与话题当前合计 ${blueskyStatusLength.value}/300 字符（按完整 emoji 计数），支持最多 4 张图片`,
        tagPlaceholder: '添加 Bluesky 话题',
        tagHint: '发布时自动转换为 #话题，计入 300 字符上限',
      },
      MASTODON: {
        titleLabel: '首句标题',
        titlePlaceholder: '标题会与正文合并发送',
        titleMax: 100,
        contentMax: Math.max(2000, currentMastodonLimits.value.maxCharacters * 2),
        contentHint: `标题、正文与话题当前合计 ${mastodonStatusLength.value}/${currentMastodonLimits.value.maxCharacters} 字符，链接按 ${currentMastodonLimits.value.charactersReservedPerUrl} 字符计，最多 ${currentMastodonLimits.value.maxMediaAttachments} 张图片`,
        tagPlaceholder: '添加 Mastodon 话题',
        tagHint: '话题计入总长度；服务器会在发布时再次校验文字和图片限制',
      },
      TOUTIAO: {
        titleLabel: '头条文章标题',
        titlePlaceholder: '2～30 个字，准确具体',
        titleMax: 30,
        contentMax: 30000,
        contentHint: '正文将转换为安全富文本并填写到头条号文章编辑器',
        tagPlaceholder: '添加头条关键词',
        tagHint: '关键词用于内容管理和平台话题，不会插入正文',
      },
    })[activePlatform.value],
)
const previewMedia = computed(() => [
  ...media.value.filter((item) => item.selected !== false && item.usageType === 'COVER'),
  ...media.value.filter((item) => item.selected !== false && item.usageType === 'BODY'),
])
const visual = useVisualTools({
  selectedArticleId,
  currentVariantId: () => current.value?.id,
  media,
  previewMedia,
})
const {
  visualMode,
  visualLoading,
  visualSearchLoading,
  visualOperationState,
  visualOperationProgress,
  visualOperationStage,
  visualOperationElapsedMs,
  removingMediaId,
  visualNotice,
  visualKeyword,
  visualPrompt,
  imageSearchResults,
  textImageModels,
  editImageModels,
  textImageModel,
  editImageModel,
  imageSize,
  transformAssetId,
  searchVisuals,
  selectVisual,
  removePreviewMedia,
  setPreviewCover,
  generateVisual,
  transformVisual,
} = visual
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
const overallProgress = computed(() => {
  if (!progressEntries.value.length) return 0
  return Math.round(
    progressEntries.value.reduce((total, item) => total + item.state.progress, 0) /
      progressEntries.value.length,
  )
})
const generationActionDisabled = computed(
  () => !selectedArticleId.value || !options.platforms.length,
)
const generationActionLabel = computed(() => {
  if (generating.value) return options.generation_mode === 'DEEP' ? '创作进行中' : '生成进行中'
  const isSameMode = generationTask.value?.optionsJson?.generation_mode === options.generation_mode
  if (generationTask.value && terminalTask.value && isSameMode) {
    return options.generation_mode === 'DEEP' ? '重新深度创作' : '重新生成版本'
  }
  return options.generation_mode === 'DEEP' ? '开始深度创作' : '生成平台版本'
})
const generationActionHint = computed(() => {
  if (generating.value) {
    return `${completedPlatformCount.value}/${progressEntries.value.length} 个平台 · ${overallProgress.value}%`
  }
  if (!selectedArticleId.value) return '请先选择原文'
  if (!options.platforms.length) return '请至少选择一个平台'
  return '参数会应用到全部所选平台'
})
const deepTask = computed(() =>
  generationTask.value?.optionsJson?.generation_mode === 'DEEP' ? generationTask.value : undefined,
)
const deepAvailablePlatforms = computed(() => deepTask.value?.platformsJson || options.platforms)
const deepPlatformState = computed(
  () => deepTask.value?.platformStatusJson?.[deepWorkbenchPlatform.value],
)
const deepBrief = computed<Record<string, unknown> | undefined>(() => {
  for (const platform of deepAvailablePlatforms.value) {
    const brief = deepTask.value?.platformStatusJson?.[platform]?.brief
    if (brief) return brief
  }
  return undefined
})
const deepCandidates = computed(() => deepPlatformState.value?.candidates || [])
const deepReview = computed(() => deepPlatformState.value?.review)
const deepStageIndex = computed(() => {
  if (!deepTask.value) return -1
  if (deepPlatformState.value?.status === 'SUCCESS') return 4
  if (deepReview.value) return 3
  if (deepCandidates.value.length) return 2
  if (deepPlatformState.value?.strategy) return 1
  if (deepBrief.value) return 0
  return -1
})
const deepStages = [
  { title: '素材简报', description: '事实、边界与信息缺口' },
  { title: '创作策略', description: '角度、钩子与内容结构' },
  { title: '候选工作坊', description: '比较两份完整草稿' },
  { title: '主编审校', description: '六维评分与修订建议' },
  { title: '最终版本', description: '人工选择后继续编辑' },
]
const deepWorkbenchSummary = computed(() => {
  if (!deepTask.value) return '生成后可按需查看研究、策略、候选稿与审校记录'
  if (deepTask.value.status === 'SUCCESS') return '创作过程已完成，成品已进入发布预览与微调'
  const currentStage = deepStages[Math.max(0, deepStageIndex.value)]
  return currentStage ? `正在处理：${currentStage.title}` : '正在准备深度创作流程'
})
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

function stringList(source: Record<string, unknown> | undefined, key: string) {
  const value = source?.[key]
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

function textValue(source: Record<string, unknown> | undefined, key: string) {
  const value = source?.[key]
  return typeof value === 'string' || typeof value === 'number' ? String(value) : ''
}

function reviewValue(key: string) {
  const value = deepReview.value?.[key]
  return typeof value === 'number' || typeof value === 'string' ? value : '-'
}

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

function platformErrorMessage(error: string, platform: Platform) {
  const issue = presentOperationError(error, {
    type: 'GENERATION',
    platform,
  })
  return issue ? `${issue.title}：${issue.description}` : '该平台生成未完成，请稍后重试。'
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

async function loadArticles() {
  const data = await workflowApi.articles({ page_size: 100 })
  articles.value = data.items
  const queryId = Number(route.query.article)
  selectedArticleId.value = data.items.some((item) => item.id === queryId)
    ? queryId
    : data.items[0]?.id
  if (selectedArticleId.value) await loadArticle()
}

async function fetchArticleBundle(articleId: number) {
  const [articleData, accountData, mediaData, latestDeepTask] = await Promise.all([
    workflowApi.article(articleId),
    workflowApi.platformAccounts(),
    workflowApi.articleMedia(articleId),
    workflowApi.latestDeepTask(articleId),
  ])
  const articleVariants = articleData.variants || (await workflowApi.variants(articleId))
  return { articleData, accountData, mediaData, latestDeepTask, articleVariants }
}

async function loadArticle() {
  if (!selectedArticleId.value) return
  const articleId = selectedArticleId.value
  const sequence = ++articleLoadSequence
  visual.dispose()
  generationPolling.cancel()
  generating.value = false
  regeneratingDeepPlatform.value = false
  let bundle
  try {
    bundle = await fetchArticleBundle(articleId)
  } catch (error) {
    if (sequence === articleLoadSequence && articleId === selectedArticleId.value) {
      if (loadedArticleId !== undefined) selectedArticleId.value = loadedArticleId
      ElMessage.error(getApiErrorMessage(error, '文章加载失败，已保留当前内容'))
    }
    return
  }
  const { articleData, accountData, mediaData, latestDeepTask, articleVariants } = bundle
  if (sequence !== articleLoadSequence || articleId !== selectedArticleId.value) return
  loadedArticleId = articleId
  article.value = articleData
  variants.value = articleVariants
  accounts.value = accountData
  media.value = mediaData
  visual.resetForArticle(articleData, mediaData)
  options.target_audience = articleData.targetAudience || ''
  restorePreferences(articleData.id)
  if (route.query.mode === 'deep') options.generation_mode = 'DEEP'
  generationTask.value = latestDeepTask || undefined
  if (latestDeepTask?.platformsJson[0]) {
    deepWorkbenchPlatform.value = latestDeepTask.platformsJson[0]
  }
  selectedVersionId.value = undefined
  syncEditor()
  if (latestDeepTask && !['SUCCESS', 'PARTIAL_SUCCESS', 'FAILED'].includes(latestDeepTask.status)) {
    generating.value = true
    operationStartedAt.value = latestDeepTask.createdAt
      ? Date.parse(latestDeepTask.createdAt)
      : Date.now()
    const ticket = generationPolling.begin(articleId)
    void generationPolling
      .poll(latestDeepTask.id, ticket)
      .catch((error) => {
        if (ticket.active()) ElMessage.error(getApiErrorMessage(error, '恢复生成任务失败'))
      })
      .finally(() => {
        if (ticket.active()) generating.value = false
      })
  }
}

function syncEditor() {
  drafts.syncCurrent()
  reviewResult.value = current.value?.reviewDetailJson
  if (!comparisonVersionId.value || comparisonVersionId.value === current.value?.id) {
    comparisonVersionId.value = activeVersions.value.find(
      (item) => item.id !== current.value?.id,
    )?.id
  }
  if (current.value && !recoveryDraft.value && !autoFittedWeiboVariantIds.has(current.value.id)) {
    autoFittedWeiboVariantIds.add(current.value.id)
    if (fitWeiboDraftForImage()) {
      scheduleAutosave()
      ElMessage.info('微博内容已自动压缩为可带图发布版本')
    }
  }
}

function notifyGeneration(result: GenerationTask, message: string, platform?: Platform) {
  ElMessage(generationOutcome(result, message, platform))
}

async function generate() {
  if (!selectedArticleId.value || !options.platforms.length) {
    ElMessage.warning('请选择原文和目标平台')
    return
  }
  generating.value = true
  generationProgressExpanded.value = false
  generationTask.value = undefined
  deepWorkbenchPlatform.value = options.platforms[0]
  operationStartedAt.value = Date.now()
  const ticket = generationPolling.begin(selectedArticleId.value)
  const request = {
    article_id: selectedArticleId.value,
    ...options,
    platforms: [...options.platforms],
  }
  try {
    const task = await workflowApi.generate(request)
    if (!ticket.active()) return
    const result = await generationPolling.poll(task.taskId, ticket)
    if (!result || !ticket.active()) return
    activePlatform.value = request.platforms[0]
    notifyGeneration(result, '平台版本已生成')
    if (request.generation_mode === 'DEEP' && result.status !== 'FAILED') openFineTuneWorkspace()
  } catch (error) {
    if (ticket.active()) ElMessage.error(getApiErrorMessage(error, '生成失败'))
  } finally {
    if (ticket.active()) generating.value = false
  }
}

function handleGenerationShortcut(event: globalThis.KeyboardEvent) {
  if (
    event.defaultPrevented ||
    event.repeat ||
    generating.value ||
    generationActionDisabled.value ||
    !(event.ctrlKey || event.metaKey) ||
    event.key !== 'Enter'
  ) {
    return
  }
  event.preventDefault()
  void generate()
}

function openFineTuneWorkspace() {
  deepWorkbenchExpanded.value = false
  workspaceLayout.value = 'PREVIEW'
  window.requestAnimationFrame(() => {
    composerWorkspace.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

async function selectCandidate(index: number) {
  if (!deepTask.value) return
  const taskId = deepTask.value.id
  const platform = deepWorkbenchPlatform.value
  const articleId = selectedArticleId.value
  selectingCandidate.value = index
  try {
    const result = await workflowApi.selectDeepCandidate(taskId, platform, index)
    if (selectedArticleId.value !== articleId) return
    generationTask.value = result.task
    const byId = new Map(variants.value.map((item) => [item.id, item]))
    byId.set(result.variant.id, result.variant)
    variants.value = [...byId.values()]
    activePlatform.value = platform
    selectedVersionId.value = result.variant.id
    syncEditor()
    ElMessage.success(`已采用候选稿 ${index + 1}，并保存为新的可编辑版本`)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '采用候选稿失败'))
  } finally {
    selectingCandidate.value = undefined
  }
}

async function regenerateDeep() {
  if (!deepTask.value || !selectedArticleId.value) return
  const taskId = deepTask.value.id
  const platform = deepWorkbenchPlatform.value
  const articleId = selectedArticleId.value
  let ticket: GenerationTicket | undefined
  try {
    const { value } = await ElMessageBox.prompt(
      '说明希望保留什么、修改什么。系统只会重做当前平台，并保存新的研究过程。',
      `重做${platformNames[platform]}候选稿`,
      {
        confirmButtonText: '按意见重做',
        cancelButtonText: '取消',
        inputType: 'textarea',
        inputPlaceholder: '例如：保留事实框架，开头更克制，减少口号式表达',
        inputValidator: (input) => Boolean(input.trim()) || '请输入修改意见',
      },
    )
    if (selectedArticleId.value !== articleId) return
    regeneratingDeepPlatform.value = true
    operationStartedAt.value = Date.now()
    ticket = generationPolling.begin(articleId)
    const task = await workflowApi.regenerateDeepPlatform(taskId, platform, value.trim())
    if (!ticket.active()) return
    const result = await generationPolling.poll(task.taskId, ticket)
    if (result && ticket.active())
      notifyGeneration(result, '已按修改意见生成新的候选方案', platform)
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    if (!ticket || ticket.active()) ElMessage.error(getApiErrorMessage(error, '重新生成失败'))
  } finally {
    if (ticket?.active()) regeneratingDeepPlatform.value = false
  }
}

async function retryFailed(platform: Platform) {
  if (!generationTask.value || !selectedArticleId.value) return
  const taskId = generationTask.value.id
  const ticket = generationPolling.begin(selectedArticleId.value)
  generating.value = true
  operationStartedAt.value = Date.now()
  try {
    const task = await workflowApi.retryTaskPlatform(taskId, platform)
    if (!ticket.active()) return
    options.platforms = [platform]
    const result = await generationPolling.poll(task.taskId, ticket)
    if (!result || !ticket.active()) return
    activePlatform.value = platform
    notifyGeneration(result, `${platformNames[platform]}已重新生成`, platform)
  } catch (error) {
    if (ticket.active()) ElMessage.error(getApiErrorMessage(error, '平台重试失败'))
  } finally {
    if (ticket.active()) generating.value = false
  }
}

async function persistVariant(variantId: number, _payload: VariantDraftPayload, manual = false) {
  const success = await drafts.save(variantId)
  if (manual && success) {
    savedToast.value = true
    window.setTimeout(() => (savedToast.value = false), 1800)
  } else if (manual && !success) ElMessage.error('保存失败，草稿已保留在本机')
  return success
}

function scheduleAutosave() {
  drafts.stage()
}

async function save() {
  if (!current.value) return false
  return persistVariant(current.value.id, snapshotEditing(), true)
}

async function saveWechatDraft() {
  if (!current.value || current.value.platform !== 'WECHAT_OFFICIAL') return
  const variantId = current.value.id
  const account = accounts.value.find((item) => item.platform === 'WECHAT_OFFICIAL')
  if (!account?.id || account.status !== 'CONNECTED') {
    try {
      await ElMessageBox.confirm(
        '请先在“平台账号”完成微信公众号扫码登录或 API 配置。',
        '公众号尚未连接',
        { confirmButtonText: '去连接', cancelButtonText: '取消', type: 'warning' },
      )
      if (auth.canManageSystem) {
        await router.push({ name: 'platform-accounts', query: { platform: 'WECHAT_OFFICIAL' } })
      } else {
        ElMessage.info('请联系管理员在“平台账号”页面完成公众号连接')
      }
    } catch {
      // 用户选择留在当前编辑页。
    }
    return
  }

  try {
    await ElMessageBox.confirm(
      '将先保存当前修改，再将文章存入该公众号的草稿箱。此操作不会公开发布。',
      '保存到公众号草稿箱',
      { confirmButtonText: '保存草稿', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }

  savingWechatDraft.value = true
  wechatDraftStartedAt.value = Date.now()
  try {
    if (current.value?.id !== variantId) return
    if (!(await persistVariant(variantId, snapshotEditing(), true))) return
    const result = await workflowApi.saveWechatDraft(variantId)
    ElMessage.success(
      result.draftId ? `已保存到公众号草稿箱（${result.draftId}）` : '已保存到公众号草稿箱',
    )
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存到公众号草稿箱失败'))
  } finally {
    savingWechatDraft.value = false
    wechatDraftStartedAt.value = undefined
  }
}

async function saveToutiaoDraft() {
  if (!current.value || current.value.platform !== 'TOUTIAO') return
  const variantId = current.value.id
  const account = accounts.value.find((item) => item.platform === 'TOUTIAO')
  if (!account?.id || account.status !== 'CONNECTED') {
    try {
      await ElMessageBox.confirm('请先在“平台账号”完成今日头条扫码登录。', '今日头条尚未连接', {
        confirmButtonText: '去连接',
        cancelButtonText: '取消',
        type: 'warning',
      })
      if (auth.canManageSystem) {
        await router.push({ name: 'platform-accounts', query: { platform: 'TOUTIAO' } })
      } else {
        ElMessage.info('请联系管理员在“平台账号”页面完成今日头条连接')
      }
    } catch {
      // 用户选择留在当前编辑页。
    }
    return
  }

  try {
    await ElMessageBox.confirm(
      '将先保存当前修改，再短暂打开本机 Chrome，把标题、正文和已选择的图片写入今日头条草稿箱。请不要关闭该窗口；此操作不会公开发布。',
      '保存到今日头条草稿箱',
      { confirmButtonText: '保存草稿', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }

  savingToutiaoDraft.value = true
  toutiaoDraftStartedAt.value = Date.now()
  try {
    if (current.value?.id !== variantId) return
    if (!(await persistVariant(variantId, snapshotEditing(), true))) return
    const result = await workflowApi.saveToutiaoDraft(variantId)
    ElMessage.success(
      result.draftId ? `已保存到今日头条草稿箱（${result.draftId}）` : '已保存到今日头条草稿箱',
    )
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存到今日头条草稿箱失败'))
  } finally {
    savingToutiaoDraft.value = false
    toutiaoDraftStartedAt.value = undefined
  }
}

function restoreLocalDraft() {
  if (drafts.restore()) ElMessage.success('已恢复本机草稿，将自动保存到当前版本')
}

function discardLocalDraft() {
  if (!recoveryDraft.value) return
  drafts.discard()
  ElMessage.success('已丢弃本机草稿')
}

async function approve() {
  if (!current.value) return
  const variantId = current.value.id
  const articleId = selectedArticleId.value
  try {
    if (!(await drafts.save(variantId))) return ElMessage.error('请先保存正文后再审核')
    if (current.value?.id !== variantId || selectedArticleId.value !== articleId) return
    const fingerprint = current.value.contentFingerprint
    if (!fingerprint) return ElMessage.error('请刷新当前版本后重新审核')
    const value = await workflowApi.approveVariant(variantId, { expected_fingerprint: fingerprint })
    if (selectedArticleId.value !== articleId) return
    variants.value = variants.value.map((item) => (item.id === value.id ? value : item))
    ElMessage.success('已审核通过')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '审核通过失败'))
  }
}

async function reject() {
  if (!current.value) return
  const variantId = current.value.id
  const articleId = selectedArticleId.value
  try {
    if (!(await drafts.save(variantId))) return ElMessage.error('请先保存正文后再审核')
    if (current.value?.id !== variantId || selectedArticleId.value !== articleId) return
    const fingerprint = current.value.contentFingerprint
    if (!fingerprint) return ElMessage.error('请刷新当前版本后重新审核')
    const value = await workflowApi.rejectVariant(variantId, { expected_fingerprint: fingerprint })
    if (selectedArticleId.value !== articleId) return
    variants.value = variants.value.map((item) => (item.id === value.id ? value : item))
    ElMessage.success('版本已拒绝')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '拒绝版本失败'))
  }
}

async function deleteVersion() {
  if (!current.value) return
  const id = current.value.id
  try {
    await ElMessageBox.confirm(`确定删除版本 ${current.value.versionNo}？`, '删除历史版本', {
      type: 'warning',
    })
    await workflowApi.deleteVariant(id)
    drafts.forget(id)
    variants.value = variants.value.filter((item) => item.id !== id)
    selectedVersionId.value = undefined
    syncEditor()
    ElMessage.success('版本已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(getApiErrorMessage(error, '删除版本失败'))
    }
  }
}

async function regenerate() {
  if (!current.value || !selectedArticleId.value) return
  const variant = current.value
  const ticket = generationPolling.begin(selectedArticleId.value)
  generating.value = true
  operationStartedAt.value = Date.now()
  try {
    const task = await workflowApi.regenerate(variant.id)
    if (!ticket.active()) return
    options.platforms = [variant.platform]
    const result = await generationPolling.poll(task.taskId, ticket)
    if (result && ticket.active())
      notifyGeneration(result, '单平台版本已重新生成', variant.platform)
  } catch (error) {
    if (ticket.active()) ElMessage.error(getApiErrorMessage(error))
  } finally {
    if (ticket.active()) generating.value = false
  }
}

async function reviewQuality() {
  if (!current.value) return
  const variantId = current.value.id
  reviewing.value = true
  try {
    const result = await workflowApi.reviewVariant(variantId)
    if (current.value?.id !== variantId) return
    reviewResult.value = result
    ElMessage.success('质量评审完成')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '质量评审失败'))
  } finally {
    reviewing.value = false
  }
}

async function copy() {
  const text = platformCopyText()
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const area = document.createElement('textarea')
      area.value = text
      area.style.position = 'fixed'
      area.style.opacity = '0'
      try {
        document.body.appendChild(area)
        area.select()
        if (!document.execCommand('copy')) throw new Error('copy command failed')
      } finally {
        area.remove()
      }
    }
    ElMessage.success('已复制')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '复制失败，请手动选择文本复制'))
  }
}

async function openWechatFormatter() {
  if (!current.value || current.value.platform !== 'WECHAT_OFFICIAL') return
  const variantId = current.value.id
  try {
    if (!saved.value && !(await save())) return
    if (current.value?.id !== variantId) return
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

async function goToCalendar(scheduleId: number) {
  persistPreferences()
  await router.push({ name: 'calendar', query: { schedule: scheduleId } })
}

async function scheduleCurrent() {
  if (!article.value || !current.value) return
  const articleId = article.value.id
  const variantId = current.value.id
  const fitted = fitWeiboDraftForImage()
  // Flush any pending autosave before leaving the studio: the calendar reads
  // the server-side variant, so navigating with unflushed edits would schedule
  // stale content.
  if (!(await persistVariant(variantId, snapshotEditing()))) return
  if (fitted) ElMessage.success('微博内容已自动适配 140 字图文接口')
  persistPreferences()
  await router.push({
    name: 'calendar',
    query: { create: '1', article: articleId, variant: variantId },
  })
}

watch(current, syncEditor)
watch(activePlatform, () => {
  selectedVersionId.value = undefined
  syncEditor()
})
watch(
  () => options.generation_mode,
  (mode) => {
    deepWorkbenchExpanded.value = false
    if (mode === 'DEEP') workspaceLayout.value = 'PREVIEW'
  },
)
watch(
  [() => editing.content_text, () => activePlatform.value, () => current.value?.formatProfileJson],
  scheduleWechatPreview,
  { deep: true, immediate: true },
)
onBeforeUnmount(() => {
  articleLoadSequence += 1
  generationPolling.cancel()
  drafts.dispose()
  visual.dispose()
  if (clockTimer) window.clearInterval(clockTimer)
  if (wechatPreviewTimer) window.clearTimeout(wechatPreviewTimer)
  wechatPreviewSequence += 1
  window.removeEventListener('keydown', handleGenerationShortcut)
})
onMounted(() => {
  clockTimer = window.setInterval(() => (clock.value = Date.now()), 1000)
  window.addEventListener('keydown', handleGenerationShortcut)
  loadArticles().catch((error) => ElMessage.error(getApiErrorMessage(error)))
})
</script>

<template>
  <div class="studio-page">
    <Toast :visible="savedToast" message="内容已保存" @close="savedToast = false" />
    <PageHeader
      :title="options.generation_mode === 'DEEP' ? '深度创作工作台' : '内容工作室'"
      :description="
        options.generation_mode === 'DEEP'
          ? '先理解素材、确认策略、比较候选稿，再进入平台编辑与发布。'
          : '按平台并行改写、实时查看进度，并管理每个平台的历史版本。'
      "
    >
      <span
        class="save-state"
        :class="{ error: autosaveState === 'ERROR' }"
        :title="autosaveError"
        >{{ saveStateLabel }}</span
      >
      <el-button :disabled="!current || autosaveState === 'SAVING'" @click="save"
        ><Save :size="15" class="mr-1" />保存</el-button
      >
      <span v-if="savingWechatDraft" class="wechat-draft-progress" aria-live="polite">
        {{ wechatDraftProgressLabel }} · {{ wechatDraftElapsedSeconds }} 秒
      </span>
      <el-button
        v-if="current?.platform === 'WECHAT_OFFICIAL'"
        type="primary"
        :loading="savingWechatDraft"
        :disabled="autosaveState === 'SAVING'"
        data-testid="save-wechat-draft"
        @click="saveWechatDraft"
      >
        <Send :size="15" class="mr-1" />{{
          savingWechatDraft ? `处理中 ${wechatDraftElapsedSeconds} 秒` : '存入公众号草稿箱'
        }}
      </el-button>
      <span v-if="savingToutiaoDraft" class="wechat-draft-progress" aria-live="polite">
        {{ toutiaoDraftProgressLabel }} · {{ toutiaoDraftElapsedSeconds }} 秒
      </span>
      <el-button
        v-if="current?.platform === 'TOUTIAO'"
        type="primary"
        :loading="savingToutiaoDraft"
        :disabled="autosaveState === 'SAVING'"
        data-testid="save-toutiao-draft"
        @click="saveToutiaoDraft"
      >
        <Send :size="15" class="mr-1" />{{
          savingToutiaoDraft ? '处理中 ' + toutiaoDraftElapsedSeconds + ' 秒' : '存入头条草稿箱'
        }}
      </el-button>
    </PageHeader>

    <section
      v-if="
        generationTask &&
        (generating ||
          !generationTask.optionsJson?.generation_mode ||
          options.generation_mode === generationTask.optionsJson?.generation_mode)
      "
      class="generation-progress"
      :class="{
        'is-complete':
          generationTask.status === 'SUCCESS' && !generating && !generationProgressExpanded,
      }"
      data-testid="generation-progress"
    >
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
        <div class="generation-progress-actions">
          <button
            v-if="generationTask.status === 'SUCCESS' && !generating"
            type="button"
            @click="generationProgressExpanded = !generationProgressExpanded"
          >
            {{ generationProgressExpanded ? '收起详情' : '查看详情' }}
          </button>
          <strong class="generation-percentage">{{ generationTask.progress }}%</strong>
        </div>
      </header>
      <div class="generation-overall-track" aria-label="任务总进度">
        <span :style="{ width: `${generationTask.progress}%` }" />
      </div>
      <div
        v-show="generating || generationTask.status !== 'SUCCESS' || generationProgressExpanded"
        class="generation-wait-hint"
        data-testid="generation-wait-hint"
      >
        <span>{{ waitHint }}</span>
        <small>{{ formatLastUpdate(lastProgressAt) }} · 进度按真实处理阶段计算</small>
      </div>
      <div
        v-show="generating || generationTask.status !== 'SUCCESS' || generationProgressExpanded"
        class="generation-progress-grid"
      >
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
            <span class="platform-stage">
              {{
                item.state.status === 'FAILED'
                  ? '该平台未完成，请查看下方处理建议。'
                  : item.state.message || '等待开始处理'
              }}
            </span>
            <div class="platform-progress-track">
              <span :style="{ width: `${item.state.progress}%` }" />
            </div>
            <small v-if="item.state.attempt > 1">第 {{ item.state.attempt }} 次尝试</small>
            <small v-if="item.state.status === 'SUCCESS'">
              {{ formatDuration(item.state.durationMs) }} · {{ item.state.tokenUsage }} Token
            </small>
            <small v-if="item.state.error" class="platform-error">
              {{ platformErrorMessage(item.state.error, item.platform) }}
            </small>
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

    <section
      v-if="options.generation_mode === 'DEEP'"
      class="deep-workbench"
      data-testid="deep-creation-workbench"
    >
      <header class="deep-workbench-header">
        <div class="deep-workbench-heading">
          <span class="deep-eyebrow">深度创作过程</span>
          <div>
            <h2>研究、策略、候选与审校</h2>
            <p>{{ deepWorkbenchSummary }}</p>
          </div>
        </div>
        <div class="deep-workbench-actions">
          <div v-if="deepTask" class="deep-session-meta">
            <span>任务 {{ deepTask.id.slice(0, 8) }}</span>
            <b>{{ taskStatusLabel }}</b>
          </div>
          <el-button size="small" @click="deepWorkbenchExpanded = !deepWorkbenchExpanded">
            <FileText :size="14" />{{ deepWorkbenchExpanded ? '收起过程' : '查看过程' }}
          </el-button>
          <el-button
            v-if="deepTask && terminalTask"
            type="primary"
            plain
            size="small"
            @click="openFineTuneWorkspace"
          >
            <LayoutTemplate :size="14" />预览与微调
          </el-button>
        </div>
      </header>

      <div
        v-if="deepWorkbenchExpanded || generating"
        class="deep-stage-track"
        aria-label="深度创作阶段"
      >
        <article
          v-for="(stage, index) in deepStages"
          :key="stage.title"
          :class="{
            active: index === deepStageIndex,
            completed: index < deepStageIndex || (index === 4 && deepStageIndex === 4),
          }"
        >
          <span>{{
            index < deepStageIndex || (index === 4 && deepStageIndex === 4) ? '✓' : index + 1
          }}</span>
          <div>
            <b>{{ stage.title }}</b>
            <small>{{ stage.description }}</small>
          </div>
        </article>
      </div>

      <div v-if="deepWorkbenchExpanded" class="deep-workbench-detail">
        <div v-if="!deepTask" class="deep-empty-state">
          <div>
            <b>深度创作会保留每一步产物</b>
            <p>
              系统会核验事实、制定策略、生成两份候选稿并完成主编审校；这些过程仅在你需要时展开查看。
            </p>
          </div>
          <ol>
            <li><span>01</span>核验原文事实边界</li>
            <li><span>02</span>制定平台创作策略</li>
            <li><span>03</span>比较两份完整候选稿</li>
            <li><span>04</span>查看主编评分并人工定稿</li>
          </ol>
        </div>

        <template v-else>
          <section v-if="deepBrief" class="deep-artifact deep-brief">
            <header>
              <div>
                <span class="artifact-index">01</span>
                <div>
                  <h3>素材研究简报</h3>
                  <p>以下内容只来自原文，是后续所有创作不能越过的事实边界。</p>
                </div>
              </div>
              <span class="artifact-status">已保存</span>
            </header>
            <blockquote>{{ textValue(deepBrief, 'core_thesis') }}</blockquote>
            <div class="deep-brief-grid">
              <article>
                <b>不可改变的事实</b>
                <ul>
                  <li v-for="item in stringList(deepBrief, 'immutable_facts')" :key="item">
                    {{ item }}
                  </li>
                </ul>
              </article>
              <article>
                <b>读者真正需要</b>
                <ul>
                  <li v-for="item in stringList(deepBrief, 'audience_needs')" :key="item">
                    {{ item }}
                  </li>
                  <li v-if="!stringList(deepBrief, 'audience_needs').length">暂无额外判断</li>
                </ul>
              </article>
              <article class="attention">
                <b>信息缺口与禁止推断</b>
                <ul>
                  <li
                    v-for="item in [
                      ...stringList(deepBrief, 'content_gaps'),
                      ...stringList(deepBrief, 'forbidden_inferences'),
                    ]"
                    :key="item"
                  >
                    {{ item }}
                  </li>
                  <li
                    v-if="
                      !stringList(deepBrief, 'content_gaps').length &&
                      !stringList(deepBrief, 'forbidden_inferences').length
                    "
                  >
                    未发现明显信息缺口
                  </li>
                </ul>
              </article>
            </div>
          </section>

          <nav class="deep-platform-tabs" aria-label="选择查看平台创作过程">
            <button
              v-for="platform in deepAvailablePlatforms"
              :key="platform"
              :class="{ active: deepWorkbenchPlatform === platform }"
              @click="deepWorkbenchPlatform = platform"
            >
              <PlatformIcon :platform="platform" size="sm" />
              <span>{{ platformNames[platform] }}</span>
              <small>{{
                platformStatusLabel(deepTask.platformStatusJson[platform]?.status || 'PENDING')
              }}</small>
            </button>
          </nav>

          <section v-if="deepPlatformState?.strategy" class="deep-artifact deep-strategy">
            <header>
              <div>
                <span class="artifact-index">02</span>
                <div>
                  <h3>{{ platformNames[deepWorkbenchPlatform] }}创作策略</h3>
                  <p>先确定如何表达，再进入正文生成。</p>
                </div>
              </div>
              <span class="artifact-status">AI 策划完成</span>
            </header>
            <div class="strategy-hero">
              <span>切入角度</span>
              <strong>{{ deepPlatformState.strategy.angle }}</strong>
            </div>
            <div class="strategy-grid">
              <article>
                <span>开场钩子</span>
                <p>{{ deepPlatformState.strategy.hook }}</p>
              </article>
              <article>
                <span>读者价值</span>
                <p>{{ deepPlatformState.strategy.reader_value }}</p>
              </article>
              <article>
                <span>行动引导</span>
                <p>{{ deepPlatformState.strategy.cta || '自然收束' }}</p>
              </article>
            </div>
            <ol class="strategy-outline">
              <li v-for="(item, index) in deepPlatformState.strategy.structure" :key="item">
                <span>{{ index + 1 }}</span
                >{{ item }}
              </li>
            </ol>
          </section>

          <section
            v-if="deepCandidates.length || deepPlatformState?.candidateTitles?.length"
            class="deep-artifact candidate-workshop"
          >
            <header>
              <div>
                <span class="artifact-index">03</span>
                <div>
                  <h3>候选稿工作坊</h3>
                  <p>两份稿件采用不同表达路径。AI 的选择只是建议，你拥有最终决定权。</p>
                </div>
              </div>
              <el-button
                plain
                :loading="regeneratingDeepPlatform"
                data-testid="regenerate-deep-platform"
                @click="regenerateDeep"
              >
                <RefreshCw :size="14" />带意见重做
              </el-button>
            </header>
            <div v-if="deepCandidates.length" class="candidate-grid">
              <article
                v-for="(candidate, index) in deepCandidates"
                :key="`${candidate.title}-${index}`"
                :class="{
                  recommended: deepPlatformState?.selectedCandidate === index,
                  selected: deepPlatformState?.userSelectedCandidate === index,
                }"
                :data-testid="`deep-candidate-${index}`"
              >
                <header>
                  <span>方案 {{ index + 1 }}</span>
                  <b v-if="deepPlatformState?.userSelectedCandidate === index">你已采用</b>
                  <b v-else-if="deepPlatformState?.selectedCandidate === index">AI 推荐</b>
                </header>
                <h4>{{ candidate.title }}</h4>
                <pre>{{ candidate.content }}</pre>
                <div v-if="candidate.hashtags?.length" class="candidate-tags">
                  {{ candidate.hashtags.join(' ') }}
                </div>
                <ul v-if="candidate.warnings?.length" class="candidate-warnings">
                  <li v-for="warning in candidate.warnings" :key="warning">{{ warning }}</li>
                </ul>
                <el-button
                  :type="deepPlatformState?.userSelectedCandidate === index ? 'success' : 'primary'"
                  :plain="deepPlatformState?.userSelectedCandidate !== index"
                  :loading="selectingCandidate === index"
                  :disabled="
                    selectingCandidate !== undefined ||
                    deepPlatformState?.userSelectedCandidate === index
                  "
                  :data-testid="`select-deep-candidate-${index}`"
                  @click="selectCandidate(index)"
                >
                  {{
                    deepPlatformState?.userSelectedCandidate === index
                      ? '已保存为新版本'
                      : '采用此稿并继续编辑'
                  }}
                </el-button>
              </article>
            </div>
            <div v-else class="legacy-candidate-notice">
              <div>
                <b>这是一条升级前的深度创作记录</b>
                <p>
                  当时只保存了候选标题，没有保存完整正文。现在重新生成后，两份完整候选都会保留在这里。
                </p>
              </div>
              <ul>
                <li v-for="(title, index) in deepPlatformState?.candidateTitles || []" :key="title">
                  <span>方案 {{ index + 1 }}</span
                  >{{ title }}
                </li>
              </ul>
            </div>
          </section>

          <section v-if="deepReview" class="deep-artifact deep-review">
            <header>
              <div>
                <span class="artifact-index">04</span>
                <div>
                  <h3>AI 主编审校</h3>
                  <p>评分用于暴露风险与取舍，不会替你做最后决定。</p>
                </div>
              </div>
              <span class="artifact-status"
                >推荐方案 {{ Number(deepPlatformState?.selectedCandidate ?? 0) + 1 }}</span
              >
            </header>
            <div class="review-score-grid">
              <article>
                <b>{{ reviewValue('factual_consistency') }}</b
                ><span>事实一致</span>
              </article>
              <article>
                <b>{{ reviewValue('information_completeness') }}</b
                ><span>信息完整</span>
              </article>
              <article>
                <b>{{ reviewValue('platform_fit') }}</b
                ><span>平台适配</span>
              </article>
              <article>
                <b>{{ reviewValue('readability') }}</b
                ><span>可读性</span>
              </article>
              <article>
                <b>{{ reviewValue('format_compliance') }}</b
                ><span>格式合规</span>
              </article>
              <article>
                <b>{{ reviewValue('non_genericness') }}</b
                ><span>非模板化</span>
              </article>
            </div>
            <div class="review-notes">
              <article>
                <b>发现的问题</b>
                <ul>
                  <li v-for="item in stringList(deepReview, 'issues')" :key="item">{{ item }}</li>
                  <li v-if="!stringList(deepReview, 'issues').length">未发现需要阻断发布的问题</li>
                </ul>
              </article>
              <article>
                <b>主编修改建议</b>
                <ul>
                  <li v-for="item in stringList(deepReview, 'improvements')" :key="item">
                    {{ item }}
                  </li>
                  <li v-if="!stringList(deepReview, 'improvements').length">
                    当前版本无需额外修改
                  </li>
                </ul>
              </article>
            </div>
          </section>
        </template>
      </div>
    </section>

    <div v-if="articles.length" ref="composerWorkspace" class="composer-workspace">
      <header class="composer-workspace-bar">
        <div>
          <strong>发布预览与微调</strong>
          <span>修改标题、正文或标签后，平台预览会实时同步</span>
        </div>
        <el-segmented
          v-model="workspaceLayout"
          :options="[
            { label: '预览微调', value: 'PREVIEW' },
            { label: '专注编辑', value: 'EDIT' },
          ]"
          data-testid="workspace-layout-control"
        />
      </header>
      <div
        class="composer-shell"
        :class="{ 'preview-first': workspaceLayout === 'PREVIEW' }"
        data-testid="composer-shell"
      >
        <aside class="composer-settings">
          <div class="composer-settings-scroll">
            <div class="composer-section">
              <label>原文</label>
              <el-select
                v-model="selectedArticleId"
                filterable
                class="w-full"
                @change="loadArticle"
              >
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
              <label class="secondary-setting-label">额外创作要求</label>
              <el-input
                v-model="options.creative_requirements"
                type="textarea"
                :rows="4"
                maxlength="1000"
                show-word-limit
                placeholder="例如：避免营销腔；保留关键数据；结尾给出可执行清单"
                data-testid="creative-requirements"
              />
            </div>
            <div class="composer-section">
              <label>目标平台</label>
              <el-checkbox-group v-model="options.platforms" class="platform-checks">
                <label v-for="(name, key) in platformNames" :key="key">
                  <el-checkbox :value="key" />
                  <PlatformIcon :platform="key" size="sm" /><span>{{ name }}</span>
                </label>
              </el-checkbox-group>
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
          </div>
          <footer class="composer-settings-action" data-testid="sticky-generation-action">
            <div class="composer-action-summary">
              <span>{{ generationActionHint }}</span>
              <kbd>Ctrl/⌘ ↵</kbd>
            </div>
            <el-button
              type="primary"
              :loading="generating"
              :disabled="generationActionDisabled"
              @click="generate"
            >
              <Send :size="15" />{{ generationActionLabel }}
            </el-button>
          </footer>
        </aside>

        <main class="composer-editor">
          <div class="editor-toolbar">
            <button title="定位到正文" @click="focusEditor"><Type :size="16" /></button>
            <button title="选择图片" @click="openMedia"><ImagePlus :size="16" /></button>
            <span />
            <small v-if="autosaveState === 'ERROR'" class="editor-save-error" :title="autosaveError"
              >保存失败</small
            >
            <small
              >{{ editing.content_text.length }} / {{ editorPlatformConfig.contentMax }} 字</small
            >
          </div>
          <div v-if="recoveryDraft" class="draft-recovery" data-testid="draft-recovery">
            <span>发现 {{ new Date(recoveryDraft.savedAt).toLocaleString() }} 的未同步草稿</span>
            <button type="button" @click="restoreLocalDraft">恢复</button>
            <button type="button" class="muted" @click="discardLocalDraft">丢弃</button>
          </div>
          <div v-if="current" class="editor-body">
            <div class="editor-title-field">
              <label :for="`platform-title-${activePlatform}`">
                {{ editorPlatformConfig.titleLabel }}
              </label>
              <input
                :id="`platform-title-${activePlatform}`"
                v-model="editing.title"
                class="editor-title"
                :maxlength="editorPlatformConfig.titleMax"
                :placeholder="editorPlatformConfig.titlePlaceholder"
              />
              <small>{{ editing.title.length }} / {{ editorPlatformConfig.titleMax }}</small>
            </div>
            <textarea
              ref="editorContent"
              v-model="editing.content_text"
              class="editor-content"
              :maxlength="editorPlatformConfig.contentMax"
              placeholder="在这里编辑平台内容…"
            />
            <el-select
              v-model="editing.hashtags"
              multiple
              allow-create
              filterable
              class="editor-tags"
              :placeholder="editorPlatformConfig.tagPlaceholder"
            />
            <p class="editor-platform-hint">
              {{ editorPlatformConfig.contentHint }} · {{ editorPlatformConfig.tagHint }}
            </p>
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
              <span v-if="reviewResult.stale" class="stale-review"
                >内容已修改，原评审已失效，请重新评审</span
              >
              <template v-else>
                <span
                  v-if="
                    reviewResult.reviewSource === 'RULES' ||
                    reviewResult.provider === 'RULE_FALLBACK'
                  "
                  class="text-amber-700"
                  >当前为规则检查，事实尚未验证，需人工复核</span
                >
                <span v-else-if="reviewResult.needHumanReview" class="text-amber-700"
                  >检测到待核实问题，请先处理评审意见</span
                >
                <span v-for="item in qualityDimensions" :key="item[0]"
                  >{{ item[0] }} {{ item[1] }}</span
                >
              </template>
            </div>
            <ScheduleAdvisor
              :article-id="article?.id"
              :variant-id="current.id"
              :platform="current.platform"
              :accounts="accounts"
              :review-status="current.reviewStatus"
              @scheduled="goToCalendar"
            />
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
              :title="name"
              :class="{ active: activePlatform === key }"
              @click="activePlatform = key"
            >
              <PlatformIcon :platform="key" size="sm" />{{ previewPlatformNames[key] }}
            </button>
            <small>发布效果模拟</small>
          </div>
          <div class="preview-canvas">
            <WeiboPreview
              v-if="activePlatform === 'WEIBO'"
              :account-name="currentAccount?.accountName || '未配置微博账号'"
              :title="weiboPreviewTitle"
              :content-html="previewHtml"
              :tags="editing.hashtags"
              :media="previewMedia"
              :status-length="weiboStatusLength"
              :removing-id="removingMediaId"
              @remove="removePreviewMedia"
            />
            <XiaohongshuPreview
              v-else-if="activePlatform === 'XIAOHONGSHU'"
              :account-name="currentAccount?.accountName || '未配置小红书账号'"
              :title="editing.title"
              :content-html="previewHtml"
              :tags="editing.hashtags"
              :media="previewMedia"
              :removing-id="removingMediaId"
              @remove="removePreviewMedia"
              @set-cover="setPreviewCover"
            />
            <XPreview
              v-else-if="activePlatform === 'X'"
              :account-name="currentAccount?.accountName || '未配置 X 账号'"
              :content-html="previewHtml"
              :tags="editing.hashtags"
              :media="previewMedia"
              :status-length="xStatusLength"
              :removing-id="removingMediaId"
              @remove="removePreviewMedia"
            />
            <BlueskyPreview
              v-else-if="activePlatform === 'BLUESKY'"
              :account-name="currentAccount?.accountName || '未配置 Bluesky 账号'"
              :title="editing.title"
              :content="editing.content_text"
              :tags="editing.hashtags"
              :media="previewMedia"
              :removing-id="removingMediaId"
              @remove="removePreviewMedia"
            />
            <MastodonPreview
              v-else-if="activePlatform === 'MASTODON'"
              :account-name="currentAccount?.accountName || '未配置 Mastodon 账号'"
              :title="editing.title"
              :content="editing.content_text"
              :tags="editing.hashtags"
              :media="previewMedia"
              v-bind="currentMastodonLimits"
              :removing-id="removingMediaId"
              @remove="removePreviewMedia"
            />
            <WechatPreview
              v-else-if="activePlatform === 'WECHAT_OFFICIAL'"
              :account-name="currentAccount?.accountName || '未配置公众号'"
              :title="editing.title"
              :content-html="wechatPreviewHtml || previewHtml"
              :media="previewMedia"
              :loading="wechatPreviewLoading"
              :removing-id="removingMediaId"
              @remove="removePreviewMedia"
              @set-cover="setPreviewCover"
            />
            <ToutiaoPreview
              v-else-if="activePlatform === 'TOUTIAO'"
              :account-name="currentAccount?.accountName || '未配置今日头条账号'"
              :title="editing.title"
              :content-html="previewHtml"
              :tags="editing.hashtags"
              :media="previewMedia"
              :removing-id="removingMediaId"
              @remove="removePreviewMedia"
              @set-cover="setPreviewCover"
            />
            <EmptyState v-else title="暂不支持该平台预览" />
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
                <el-button :loading="visualSearchLoading" @click="searchVisuals">搜索</el-button>
              </div>
              <small v-if="visualNotice">{{ visualNotice }}</small>
              <div class="visual-result-grid">
                <article v-for="item in imageSearchResults" :key="String(item.id)">
                  <img
                    :src="String(item.thumbnailUrl)"
                    :alt="String(item.altText || '相关图片')"
                    :title="String(item.altText || '')"
                  />
                  <span class="visual-source">
                    联网 · {{ item.source === 'UNSPLASH' ? 'Unsplash' : 'Commons' }}
                  </span>
                  <div>
                    <button @click="selectVisual(item, 'COVER')">封面</button
                    ><button @click="selectVisual(item, 'BODY')">正文</button
                    ><a
                      v-if="item.photographerUrl"
                      :href="String(item.photographerUrl)"
                      target="_blank"
                      rel="noopener noreferrer"
                      >来源</a
                    >
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
                data-testid="visual-generate-button"
                type="primary"
                :loading="visualLoading"
                :disabled="!visualPrompt.trim()"
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
                data-testid="visual-transform-button"
                type="primary"
                :loading="visualLoading"
                :disabled="!transformAssetId || !visualPrompt.trim()"
                @click="transformVisual"
              >
                <WandSparkles :size="15" class="mr-1" />生成改造版本
              </el-button>
            </template>
            <div
              v-if="visualOperationState !== 'IDLE'"
              class="visual-operation-progress"
              data-testid="visual-operation-progress"
              :data-state="visualOperationState"
              aria-live="polite"
            >
              <div class="visual-operation-progress__summary">
                <strong>{{ visualOperationStage }}</strong>
                <span>
                  {{
                    visualOperationState === 'RUNNING'
                      ? `已等待 ${Math.max(1, Math.ceil(visualOperationElapsedMs / 1000))} 秒`
                      : visualOperationState === 'SUCCESS'
                        ? '100% · 处理完成'
                        : '处理未完成'
                  }}
                </span>
              </div>
              <el-progress
                v-if="visualOperationState !== 'RUNNING'"
                :percentage="visualOperationProgress"
                :status="
                  visualOperationState === 'SUCCESS'
                    ? 'success'
                    : visualOperationState === 'FAILED'
                      ? 'exception'
                      : undefined
                "
                :stroke-width="8"
                :show-text="false"
              />
              <small v-if="visualOperationState === 'RUNNING'">
                服务仍在处理，请继续等待；完成后图片会显示在预览中。
              </small>
            </div>
            <el-button text @click="openMedia">打开完整媒体库</el-button>
          </section>
        </aside>
      </div>
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
