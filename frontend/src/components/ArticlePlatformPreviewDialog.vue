<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { ElMessage } from 'element-plus'
import PlatformIcon from '@/components/PlatformIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import EngagementMetricsBar from '@/components/EngagementMetricsBar.vue'
import WeiboPreview from '@/components/platform-preview/WeiboPreview.vue'
import XiaohongshuPreview from '@/components/platform-preview/XiaohongshuPreview.vue'
import WechatPreview from '@/components/platform-preview/WechatPreview.vue'
import ToutiaoPreview from '@/components/platform-preview/ToutiaoPreview.vue'
import XPreview from '@/components/platform-preview/XPreview.vue'
import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import type {
  Article,
  ArticleEngagementMetric,
  ArticleEngagementSummary,
  MediaAsset,
  Platform,
  PlatformAccount,
  Variant,
} from '@/types/business'
import { platformNames } from '@/types/business'
import {
  buildPreviewHtml,
  buildWeiboPreviewText,
  buildWeiboPreviewTitle,
  defaultWechatProfile,
} from '@/utils/previewContent'
import { xWeightedLength } from '@/utils/text'

const props = defineProps<{
  modelValue: boolean
  article?: Article
}>()

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const previewPlatformNames: Record<Platform, string> = {
  ...platformNames,
  WECHAT_OFFICIAL: '公众号',
  TOUTIAO: '头条',
}

const platforms: Platform[] = ['WEIBO', 'XIAOHONGSHU', 'WECHAT_OFFICIAL', 'TOUTIAO', 'X']

const loading = ref(false)
const variants = ref<Variant[]>([])
const media = ref<MediaAsset[]>([])
const accounts = ref<PlatformAccount[]>([])
const articleDetail = ref<Article>()
const engagement = ref<ArticleEngagementSummary>()
const activePlatform = ref<Platform>('WEIBO')
const wechatPreviewHtml = ref('')
const wechatPreviewLoading = ref(false)
let wechatPreviewSequence = 0

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const latestByPlatform = computed(() => {
  const map = new Map<Platform, Variant>()
  for (const variant of variants.value) {
    const existing = map.get(variant.platform)
    if (!existing || variant.versionNo > existing.versionNo) {
      map.set(variant.platform, variant)
    }
  }
  return map
})

const currentVariant = computed(() => latestByPlatform.value.get(activePlatform.value))

const usingSourceFallback = computed(
  () => Boolean(articleDetail.value?.sourceText.trim()) && !currentVariant.value,
)

const activePlatformEngagement = computed<ArticleEngagementMetric | undefined>(() =>
  engagement.value?.platforms?.find((item) => item.platform === activePlatform.value),
)

const previewMedia = computed(() => [
  ...media.value.filter((item) => item.selected !== false && item.usageType === 'COVER'),
  ...media.value.filter((item) => item.selected !== false && item.usageType === 'BODY'),
])

const draft = computed(() => {
  const variant = currentVariant.value
  if (variant) {
    return {
      title: variant.title,
      content_text: variant.contentText,
      hashtags: variant.hashtagsJson || [],
    }
  }
  const article = articleDetail.value
  if (article?.sourceText.trim()) {
    return {
      title: article.title,
      content_text: article.sourceText,
      hashtags: article.keywords || [],
    }
  }
  return { title: '', content_text: '', hashtags: [] as string[] }
})

const hasPreviewContent = computed(() => Boolean(draft.value.content_text.trim()))

const previewHtml = computed(() => buildPreviewHtml(draft.value.content_text))
const weiboPreviewTitle = computed(() =>
  buildWeiboPreviewTitle(draft.value.title, draft.value.content_text),
)
const weiboStatusLength = computed(() =>
  buildWeiboPreviewText(draft.value.title, draft.value.content_text, draft.value.hashtags).length,
)
const xStatusLength = computed(() => {
  const topics = draft.value.hashtags
    .map((tag) => tag.replace(/#/g, '').trim())
    .filter(Boolean)
    .map((topic) => `#${topic}`)
    .join(' ')
  return xWeightedLength(
    [draft.value.content_text.trim(), topics].filter(Boolean).join('\n\n'),
  )
})

function accountLabel(platform: Platform) {
  const name = accounts.value.find((item) => item.platform === platform)?.accountName
  if (name) return name
  return (
    {
      WEIBO: '未配置微博账号',
      XIAOHONGSHU: '未配置小红书账号',
      WECHAT_OFFICIAL: '未配置公众号',
      TOUTIAO: '未配置今日头条账号',
      X: '未配置 X 账号',
    } satisfies Record<Platform, string>
  )[platform]
}

async function refreshWechatPreview() {
  const content = draft.value.content_text.trim()
  if (activePlatform.value !== 'WECHAT_OFFICIAL' || !content) {
    wechatPreviewHtml.value = ''
    wechatPreviewLoading.value = false
    return
  }
  const variant = currentVariant.value
  if (variant?.contentHtml) {
    wechatPreviewHtml.value = DOMPurify.sanitize(variant.contentHtml, {
      USE_PROFILES: { html: true },
    })
    wechatPreviewLoading.value = false
    return
  }
  const sequence = ++wechatPreviewSequence
  wechatPreviewLoading.value = true
  try {
    const profile = variant?.formatProfileJson || defaultWechatProfile
    const result = await workflowApi.previewWechatFormat(content, profile)
    if (sequence !== wechatPreviewSequence) return
    wechatPreviewHtml.value = DOMPurify.sanitize(result.contentHtml, {
      USE_PROFILES: { html: true },
    })
  } catch {
    if (sequence !== wechatPreviewSequence) return
    wechatPreviewHtml.value = previewHtml.value
  } finally {
    if (sequence === wechatPreviewSequence) wechatPreviewLoading.value = false
  }
}

async function loadPreviewData() {
  if (!props.article?.id) return
  loading.value = true
  wechatPreviewHtml.value = ''
  variants.value = []
  media.value = []
  accounts.value = []
  articleDetail.value = undefined
  engagement.value = undefined
  try {
    const articleId = props.article.id
    const [variantList, mediaList, detail, engagementData] = await Promise.all([
      workflowApi.variants(articleId),
      workflowApi.articleMedia(articleId),
      workflowApi.article(articleId),
      workflowApi.articleEngagement(articleId),
    ])
    variants.value = variantList
    media.value = mediaList
    articleDetail.value = detail
    engagement.value = engagementData
    try {
      accounts.value = await workflowApi.platformAccounts()
    } catch {
      accounts.value = []
    }
    const firstWithVariant = platforms.find((platform) =>
      variantList.some((item) => item.platform === platform),
    )
    activePlatform.value = firstWithVariant || 'WEIBO'
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加载预览失败'))
  } finally {
    loading.value = false
  }
}

watch(
  () => [visible.value, props.article?.id] as const,
  ([open, articleId]) => {
    if (open && articleId) void loadPreviewData()
  },
)

watch(
  () => [activePlatform.value, currentVariant.value?.id, currentVariant.value?.contentText] as const,
  () => void refreshWechatPreview(),
)
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="article ? `平台预览 · ${article.title}` : '平台预览'"
    width="min(920px, 96vw)"
    destroy-on-close
    class="article-platform-preview-dialog"
  >
    <p v-if="article" class="preview-lead">
      模拟各平台发布效果，展示最新一版平台适配内容（只读）。
      <span v-if="usingSourceFallback" class="preview-fallback-hint">
        当前平台尚未生成版本，暂以原文内容模拟预览。
      </span>
    </p>
    <div v-loading="loading" class="preview-shell">
      <div class="preview-tabs">
        <button
          v-for="key in platforms"
          :key="key"
          type="button"
          :title="previewPlatformNames[key]"
          :class="{ active: activePlatform === key, muted: !latestByPlatform.has(key) }"
          @click="activePlatform = key"
        >
          <PlatformIcon :platform="key" size="sm" />{{ previewPlatformNames[key] }}
        </button>
        <small>发布效果模拟</small>
      </div>
      <EngagementMetricsBar
        v-if="activePlatformEngagement"
        label="发布后数据"
        :impressions="activePlatformEngagement.impressions"
        :likes="activePlatformEngagement.likes"
        :comments="activePlatformEngagement.comments"
        :collects="activePlatformEngagement.collects"
        :shares="activePlatformEngagement.shares"
        :engagement-rate="activePlatformEngagement.engagementRate"
        :simulated="activePlatformEngagement.dataSource === 'SIMULATED'"
      />
      <EngagementMetricsBar
        v-else-if="engagement?.hasData && engagement.totals"
        label="全平台汇总"
        :totals="engagement.totals"
        :simulated="engagement.simulated"
      />
      <div class="preview-canvas preview-readonly">
        <EmptyState
          v-if="!loading && !hasPreviewContent"
          title="暂无可预览内容"
          description="该文章尚未填写正文，也未生成任何平台版本。"
        />
        <WeiboPreview
          v-else-if="hasPreviewContent && activePlatform === 'WEIBO'"
          :account-name="accountLabel('WEIBO')"
          :title="weiboPreviewTitle"
          :content-html="previewHtml"
          :tags="draft.hashtags"
          :media="previewMedia"
          :status-length="weiboStatusLength"
        />
        <XiaohongshuPreview
          v-else-if="hasPreviewContent && activePlatform === 'XIAOHONGSHU'"
          :account-name="accountLabel('XIAOHONGSHU')"
          :title="draft.title"
          :content-html="previewHtml"
          :tags="draft.hashtags"
          :media="previewMedia"
        />
        <XPreview
          v-else-if="hasPreviewContent && activePlatform === 'X'"
          :account-name="accountLabel('X')"
          :content-html="previewHtml"
          :tags="draft.hashtags"
          :media="previewMedia"
          :status-length="xStatusLength"
        />
        <WechatPreview
          v-else-if="hasPreviewContent && activePlatform === 'WECHAT_OFFICIAL'"
          :account-name="accountLabel('WECHAT_OFFICIAL')"
          :title="draft.title"
          :content-html="wechatPreviewHtml || previewHtml"
          :media="previewMedia"
          :loading="wechatPreviewLoading"
        />
        <ToutiaoPreview
          v-else-if="hasPreviewContent && activePlatform === 'TOUTIAO'"
          :account-name="accountLabel('TOUTIAO')"
          :title="draft.title"
          :content-html="previewHtml"
          :tags="draft.hashtags"
          :media="previewMedia"
        />
      </div>
    </div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.preview-lead {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--color-muted, #667085);
}
.preview-fallback-hint {
  display: block;
  margin-top: 4px;
  color: #b54708;
}
.preview-shell {
  min-height: 420px;
}
.preview-shell > :deep(.engagement-metrics) {
  margin-bottom: 12px;
}
.preview-tabs button.muted {
  opacity: 0.55;
}
.preview-readonly :deep(figure button),
.preview-readonly :deep(.media-empty) {
  display: none;
}
</style>
