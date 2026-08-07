import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import { defaultPublishMode } from '@/composables/usePublishModes'
import type {
  Article,
  BatchRecommendationResponse,
  Platform,
  PlatformAccount,
  PublishTimeRecommendation,
  RecommendationPlanRow,
  TimeSource,
  TimeWindow,
  Variant,
} from '@/types/business'
import { platformNames } from '@/types/business'

export const RECOMMEND_PLATFORMS: Platform[] = [
  'WEIBO',
  'XIAOHONGSHU',
  'WECHAT_OFFICIAL',
  'TOUTIAO',
]

const confidenceLabels: Record<string, string> = { HIGH: '高', MEDIUM: '中', LOW: '低' }

function formatLocalInput(value: string) {
  return value.slice(0, 16).replace('T', ' ')
}

function toIso(value: string) {
  if (!value) return ''
  if (value.includes('T')) return value
  return value.replace(' ', 'T')
}

export function useBatchRecommendation() {
  const router = useRouter()
  const articles = ref<Article[]>([])
  const variants = ref<Variant[]>([])
  const accounts = ref<PlatformAccount[]>([])
  const contentTypes = ref<Array<{ value: string; label: string }>>([])
  const articleId = ref<number>()
  const selectedPlatforms = ref<Platform[]>(['WEIBO', 'XIAOHONGSHU', 'WECHAT_OFFICIAL', 'TOUTIAO'])
  const accountByPlatform = reactive<Partial<Record<Platform, number>>>({})
  const contentType = ref('')
  const recommendWindow = ref<TimeWindow>('90D')
  const recommendStartDate = ref('')
  const recommendEndDate = ref('')
  const loading = ref(false)
  const scheduling = ref(false)
  const batchResult = ref<BatchRecommendationResponse>()
  const planRows = ref<RecommendationPlanRow[]>([])
  const calcStep = ref(0)
  const calcPercent = ref(0)
  // Shown when the last calculateBatch() failed; keeps the guide from looking
  // like a silent "no results" success.
  const lastError = ref('')
  // Semantic pipeline switch. When off the backend keeps the hybrid-v2 result.
  const optimizeEnabled = ref(true)
  // Platform → operator-locked ISO time, replayed on every re-calculation.
  const lockedByPlatform = reactive<Partial<Record<Platform, string>>>({})
  let calcTimer: ReturnType<typeof setInterval> | undefined

  const CALC_STEPS = [
    '读取内容与平台版本',
    'LLM 生成内容排期画像',
    '检索语义相似历史内容',
    '计算相似内容用户活跃度',
    'OR-Tools 跨平台联合求解',
    'LLM 审查排期方案',
  ]

  function stopCalcProgress(final = false) {
    if (calcTimer) {
      clearInterval(calcTimer)
      calcTimer = undefined
    }
    if (final) {
      calcStep.value = CALC_STEPS.length
      calcPercent.value = 100
    }
  }

  function startCalcProgress() {
    stopCalcProgress()
    calcStep.value = 0
    calcPercent.value = 8
    calcTimer = setInterval(() => {
      if (calcStep.value < CALC_STEPS.length - 1) calcStep.value += 1
      calcPercent.value = Math.min(92, calcPercent.value + 7 + Math.floor(Math.random() * 5))
    }, 620)
  }

  const missingAccountPlatforms = computed(() =>
    selectedPlatforms.value.filter((platform) => !accountByPlatform[platform]),
  )

  const canCalculate = computed(
    () =>
      Boolean(articleId.value) &&
      selectedPlatforms.value.length > 0 &&
      missingAccountPlatforms.value.length === 0 &&
      (recommendWindow.value !== 'CUSTOM' ||
        Boolean(recommendStartDate.value && recommendEndDate.value)),
  )

  const calculateHint = computed(() => {
    if (!articleId.value) return '请先选择内容'
    if (!selectedPlatforms.value.length) return '请至少选择一个目标平台'
    if (missingAccountPlatforms.value.length)
      return `请为 ${missingAccountPlatforms.value.map((p) => platformNames[p]).join('、')} 选择账号`
    if (
      recommendWindow.value === 'CUSTOM' &&
      (!recommendStartDate.value || !recommendEndDate.value)
    )
      return '自定义范围需填写开始和结束日期'
    return ''
  })

  /** Semantic pipeline summary; undefined when the pipeline did not run. */
  const plan = computed(() => batchResult.value?.plan ?? undefined)

  const activePlanRows = computed(() =>
    planRows.value.filter((row) => !row.skipped && row.recommendation),
  )
  const canSchedule = computed(
    () => activePlanRows.value.length > 0 && activePlanRows.value.every((row) => row.selectedAt),
  )

  function accountsFor(platform: Platform) {
    return accounts.value.filter((item) => item.platform === platform && item.id)
  }

  function variantFor(platform: Platform) {
    return variants.value
      .filter((item) => item.platform === platform)
      .sort((a, b) => b.versionNo - a.versionNo)[0]
  }

  async function loadArticles() {
    const [data, accountRows, types] = await Promise.all([
      workflowApi.articles({ page_size: 100 }),
      workflowApi.platformAccounts(),
      workflowApi.activityContentTypes(),
    ])
    articles.value = data.items
    accounts.value = accountRows
    contentTypes.value = types
    articleId.value = data.items[0]?.id
    for (const platform of RECOMMEND_PLATFORMS) {
      const first = accountsFor(platform)[0]?.id
      if (first) accountByPlatform[platform] = first
    }
    await loadVariants()
  }

  async function loadVariants() {
    if (!articleId.value) return
    variants.value = await workflowApi.variants(articleId.value)
    batchResult.value = undefined
    planRows.value = []
  }

  function syncAccountDefaults() {
    for (const platform of selectedPlatforms.value) {
      if (!accountByPlatform[platform]) {
        const first = accountsFor(platform)[0]?.id
        if (first) accountByPlatform[platform] = first
      }
    }
  }

  function buildPlanRows(response: BatchRecommendationResponse) {
    planRows.value = response.items.map((item) => {
      const account = accounts.value.find((row) => row.id === accountByPlatform[item.platform])
      if (!item.success || !item.data) {
        return {
          platform: item.platform,
          accountId: accountByPlatform[item.platform] || 0,
          accountName: account?.accountName || '—',
          variantId: variantFor(item.platform)?.id || 0,
          errorMessage: item.message || '推荐失败',
          skipped: true,
          selectedAt: '',
          timeSource: 'CUSTOM' as TimeSource,
          recommendedAt: '',
          customAt: '',
          conflictLevel: 'NONE' as const,
          conflictMessage: '',
          locked: false,
        }
      }
      const recommendation = item.data
      return {
        platform: item.platform,
        accountId: accountByPlatform[item.platform] || recommendation.accountId || 0,
        accountName: account?.accountName || '—',
        variantId: recommendation.variantId || variantFor(item.platform)?.id || 0,
        recommendation,
        skipped: false,
        selectedAt: recommendation.recommendedAt,
        timeSource: 'RECOMMENDED' as TimeSource,
        recommendedAt: recommendation.recommendedAt,
        customAt: formatLocalInput(recommendation.recommendedAt),
        conflictLevel: summarizeConflict(recommendation),
        conflictMessage: summarizeConflictMessage(recommendation),
        locked: Boolean(lockedByPlatform[item.platform]),
      }
    })
    if (response.contentType && !contentType.value) {
      contentType.value = response.contentType
    }
  }

  function summarizeConflict(recommendation: PublishTimeRecommendation) {
    const levels = recommendation.conflicts.map((item) => item.level)
    if (levels.includes('CONFLICT')) return 'CONFLICT' as const
    if (levels.includes('DENSITY')) return 'DENSITY' as const
    return 'NONE' as const
  }

  function summarizeConflictMessage(recommendation: PublishTimeRecommendation) {
    if (!recommendation.conflicts.length) return '无冲突'
    return recommendation.conflicts[0]?.message || '存在发布频率提示'
  }

  async function refreshRowConflict(row: RecommendationPlanRow) {
    if (!row.selectedAt || row.skipped) return
    try {
      const result = await workflowApi.scheduleConflictCheck({
        platform: row.platform,
        scheduled_at: row.selectedAt,
        account_id: row.accountId,
      })
      row.conflictLevel = result.hasConflict
        ? 'CONFLICT'
        : result.hasDensityWarning
          ? 'DENSITY'
          : 'NONE'
      row.conflictMessage =
        result.conflicts[0]?.message || (result.hasDensityWarning ? '同账号发布较密' : '无冲突')
    } catch {
      row.conflictLevel = 'NONE'
      row.conflictMessage = '冲突检测失败'
    }
  }

  async function calculateBatch() {
    if (!canCalculate.value || !articleId.value) {
      return ElMessage.warning(calculateHint.value || '请完善输入条件')
    }
    loading.value = true
    lastError.value = ''
    batchResult.value = undefined
    planRows.value = []
    startCalcProgress()
    try {
      const response = await workflowApi.recommendBatch({
        article_id: articleId.value,
        content_type: contentType.value || undefined,
        targets: selectedPlatforms.value.map((platform) => ({
          platform,
          account_id: accountByPlatform[platform]!,
          variant_id: variantFor(platform)?.id,
          locked_at: lockedByPlatform[platform],
        })),
        optimize: optimizeEnabled.value,
        window: recommendWindow.value,
        window_start_date:
          recommendWindow.value === 'CUSTOM' ? recommendStartDate.value : undefined,
        window_end_date: recommendWindow.value === 'CUSTOM' ? recommendEndDate.value : undefined,
      })
      batchResult.value = response
      buildPlanRows(response)
      await Promise.all(planRows.value.map((row) => refreshRowConflict(row)))
      stopCalcProgress(true)
      if (!planRows.value.length) {
        lastError.value = '接口未返回任何平台结果，请检查该文章是否已生成对应平台版本。'
        ElMessage.warning(lastError.value)
        return
      }
      const solved = response.plan?.optimizationApplied
      ElMessage.success(
        solved
          ? `已生成 ${response.successCount} 个平台的联合排期方案（求解状态 ${response.plan?.solverStatus}）`
          : `已生成 ${response.successCount} 个平台的推荐方案`,
      )
      // Bring the result table into view; otherwise a long wait looks like "nothing happened".
      requestAnimationFrame(() => {
        document
          .querySelector('.result-table-wrap, .profile-panel')
          ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    } catch (error) {
      stopCalcProgress()
      calcPercent.value = 0
      calcStep.value = 0
      lastError.value = getApiErrorMessage(
        error,
        optimizeEnabled.value
          ? '联合排期计算失败。可关闭上方语义开关后重试，或确认后端服务仍在运行。'
          : '推荐计算失败，请稍后重试',
      )
      ElMessage.error(lastError.value)
    } finally {
      loading.value = false
    }
  }

  /** Keep an existing lock pinned to whatever time the operator just chose. */
  function syncLock(row: RecommendationPlanRow) {
    if (row.locked && row.selectedAt) lockedByPlatform[row.platform] = row.selectedAt
  }

  function toggleLock(row: RecommendationPlanRow) {
    if (row.locked) {
      delete lockedByPlatform[row.platform]
      row.locked = false
      return
    }
    if (!row.selectedAt) return
    lockedByPlatform[row.platform] = row.selectedAt
    row.locked = true
    ElMessage.success('已锁定该平台时间，重新计算时不会被优化调整')
  }

  function applyBestTime(row: RecommendationPlanRow) {
    if (!row.recommendation) return
    row.selectedAt = row.recommendation.recommendedAt
    row.timeSource = 'RECOMMENDED'
    row.customAt = formatLocalInput(row.recommendation.recommendedAt)
    syncLock(row)
    void refreshRowConflict(row)
  }

  function applyAlternative(row: RecommendationPlanRow, at: string) {
    row.selectedAt = at
    row.timeSource = 'ALTERNATIVE'
    row.customAt = formatLocalInput(at)
    syncLock(row)
    void refreshRowConflict(row)
  }

  function applyCustomTime(row: RecommendationPlanRow) {
    if (!row.customAt) return
    row.selectedAt = toIso(row.customAt)
    row.timeSource = 'CUSTOM'
    syncLock(row)
    void refreshRowConflict(row)
  }

  function toggleSkip(row: RecommendationPlanRow) {
    row.skipped = !row.skipped
  }

  async function staggerOverlaps(minutes = 15) {
    const groups = batchResult.value?.overlapGroups || []
    if (!groups.length) return
    const overlapSet = new Set(groups.flat())
    const affected = planRows.value
      .filter((row) => overlapSet.has(row.platform) && !row.skipped && row.recommendation)
      .sort((a, b) => a.selectedAt.localeCompare(b.selectedAt))
    if (affected.length < 2) return
    let cursor = new Date(affected[0].selectedAt)
    for (let index = 1; index < affected.length; index += 1) {
      cursor = new Date(cursor.getTime() + minutes * 60_000)
      affected[index].selectedAt = cursor.toISOString()
      affected[index].timeSource = 'CUSTOM'
      affected[index].customAt = formatLocalInput(affected[index].selectedAt)
      await refreshRowConflict(affected[index])
    }
    ElMessage.success(`已按 ${minutes} 分钟间隔错开重合时间`)
  }

  async function createBatchSchedules() {
    if (!canSchedule.value || !articleId.value) return
    scheduling.value = true
    try {
      const batchKey = `batch-${articleId.value}-${Date.now()}`
      const response = await workflowApi.createSchedulesBatch({
        article_id: articleId.value,
        content_type: contentType.value || undefined,
        idempotency_key: batchKey,
        items: activePlanRows.value.map((row) => {
          const account = accounts.value.find((item) => item.id === row.accountId)
          return {
            platform: row.platform,
            variant_id: row.variantId,
            account_id: row.accountId,
            scheduled_at: row.selectedAt,
            recommendation_id: row.recommendation!.id,
            time_source: row.timeSource,
            recommended_at: row.recommendedAt,
            publish_mode: defaultPublishMode(row.platform, account),
          }
        }),
      })
      const failed = response.items.filter((item) => !item.success)
      if (failed.length) {
        ElMessage.warning(
          `${response.successCount} 个平台已创建，${failed.length} 个失败：${failed.map((item) => `${platformNames[item.platform]}(${item.message})`).join('；')}`,
        )
      } else {
        ElMessage.success(`已创建 ${response.createdScheduleIds.length} 条排期`)
      }
      if (response.createdScheduleIds.length) {
        await router.push({
          name: 'calendar',
          query: { highlight: response.createdScheduleIds.join(',') },
        })
      }
      return response
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error))
    } finally {
      scheduling.value = false
    }
  }

  return {
    articles,
    variants,
    accounts,
    contentTypes,
    articleId,
    selectedPlatforms,
    accountByPlatform,
    contentType,
    recommendWindow,
    recommendStartDate,
    recommendEndDate,
    loading,
    scheduling,
    batchResult,
    plan,
    planRows,
    optimizeEnabled,
    calcStep,
    calcPercent,
    lastError,
    CALC_STEPS,
    confidenceLabels,
    canCalculate,
    calculateHint,
    canSchedule,
    activePlanRows,
    accountsFor,
    variantFor,
    loadArticles,
    loadVariants,
    syncAccountDefaults,
    calculateBatch,
    applyBestTime,
    applyAlternative,
    applyCustomTime,
    toggleSkip,
    toggleLock,
    staggerOverlaps,
    createBatchSchedules,
    refreshRowConflict,
    stopCalcProgress,
  }
}
