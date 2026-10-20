import { computed, getCurrentScope, onScopeDispose, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import { defaultPublishMode } from '@/composables/usePublishModes'
import { createIdempotencyIntent, normalizeSchedulePayload } from '@/utils/idempotency'
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
  'BLUESKY',
  'MASTODON',
]

const confidenceLabels: Record<string, string> = { HIGH: '高', MEDIUM: '中', LOW: '低' }

function formatLocalInput(value: string) {
  const date = new Date(value.replace(' ', 'T'))
  if (!Number.isFinite(date.getTime())) return ''
  const pad = (number: number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function toIso(value: string) {
  if (!value) return ''
  const date = new Date(value.replace(' ', 'T'))
  return Number.isFinite(date.getTime()) ? date.toISOString() : ''
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
  const batchCreateIntent = createIdempotencyIntent('batch')
  const batchResult = ref<BatchRecommendationResponse>()
  const planRows = ref<RecommendationPlanRow[]>([])
  const calcStep = ref(0)
  const calcPercent = ref(0)
  // Shown when the last calculateBatch() failed; keeps the guide from looking
  // like a silent "no results" success.
  const lastError = ref('')
  // Semantic pipeline switch. When off the backend keeps the hybrid-v2 result.
  const optimizeEnabled = ref(true)
  // Locks belong to the current article/account selection, not to a global platform.
  const lockedByPlatform = reactive<Partial<Record<Platform, string>>>({})
  let requestSequence = 0
  let variantSequence = 0
  const variantsLoading = ref(false)
  let applyingContentType = false
  const conflictSequences = new WeakMap<RecommendationPlanRow, number>()

  const CALC_STEPS = ['等待推荐服务返回（服务端未提供实时进度）', '校验推荐时间与现有排期冲突']

  function stopCalcProgress(final = false) {
    if (final) {
      calcStep.value = CALC_STEPS.length
      calcPercent.value = 100
    }
  }

  function startCalcProgress() {
    stopCalcProgress()
    calcStep.value = 0
    calcPercent.value = 0
  }

  function invalidate(clearLocks = false) {
    requestSequence += 1
    loading.value = false
    batchResult.value = undefined
    planRows.value = []
    calcStep.value = 0
    calcPercent.value = 0
    lastError.value = ''
    if (clearLocks) for (const platform of RECOMMEND_PLATFORMS) delete lockedByPlatform[platform]
  }

  watch(
    articleId,
    () => {
      variantSequence += 1
      variantsLoading.value = false
      variants.value = []
      invalidate(true)
    },
    { flush: 'sync' },
  )
  watch(
    () => JSON.stringify(accountByPlatform),
    () => invalidate(true),
    { flush: 'sync' },
  )
  watch(
    [
      selectedPlatforms,
      contentType,
      recommendWindow,
      recommendStartDate,
      recommendEndDate,
      optimizeEnabled,
    ],
    () => {
      if (!applyingContentType) invalidate()
    },
    { deep: true, flush: 'sync' },
  )
  if (getCurrentScope())
    onScopeDispose(() => {
      requestSequence += 1
      variantSequence += 1
    })

  const missingAccountPlatforms = computed(() =>
    selectedPlatforms.value.filter((platform) => !accountByPlatform[platform]),
  )

  const canCalculate = computed(
    () =>
      Boolean(articleId.value) &&
      !variantsLoading.value &&
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
    () =>
      !loading.value &&
      !scheduling.value &&
      activePlanRows.value.length > 0 &&
      activePlanRows.value.every(
        (row) => row.selectedAt && !['冲突检测失败', '正在检查冲突'].includes(row.conflictMessage),
      ),
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
    const id = articleId.value
    const sequence = ++variantSequence
    variantsLoading.value = true
    invalidate()
    try {
      const rows = await workflowApi.variants(id)
      if (sequence === variantSequence && id === articleId.value) variants.value = rows
    } finally {
      if (sequence === variantSequence) variantsLoading.value = false
    }
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
        selectedAt: lockedByPlatform[item.platform] || recommendation.recommendedAt,
        timeSource: lockedByPlatform[item.platform]
          ? ('CUSTOM' as TimeSource)
          : ('RECOMMENDED' as TimeSource),
        recommendedAt: recommendation.recommendedAt,
        customAt: formatLocalInput(lockedByPlatform[item.platform] || recommendation.recommendedAt),
        conflictLevel: summarizeConflict(recommendation),
        conflictMessage: summarizeConflictMessage(recommendation),
        locked: Boolean(lockedByPlatform[item.platform]),
      }
    })
    if (response.contentType && !contentType.value) {
      applyingContentType = true
      contentType.value = response.contentType
      applyingContentType = false
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
    const sequence = (conflictSequences.get(row) || 0) + 1
    conflictSequences.set(row, sequence)
    const at = row.selectedAt
    const accountId = row.accountId
    const context = requestSequence
    const active = () =>
      context === requestSequence &&
      conflictSequences.get(row) === sequence &&
      row.selectedAt === at &&
      row.accountId === accountId &&
      planRows.value.includes(row)
    row.conflictMessage = '正在检查冲突'
    try {
      const result = await workflowApi.scheduleConflictCheck({
        platform: row.platform,
        scheduled_at: at,
        account_id: accountId,
      })
      if (!active()) return
      row.conflictLevel = result.hasConflict
        ? 'CONFLICT'
        : result.hasDensityWarning
          ? 'DENSITY'
          : 'NONE'
      row.conflictMessage =
        result.conflicts[0]?.message || (result.hasDensityWarning ? '同账号发布较密' : '无冲突')
    } catch {
      if (!active()) return
      row.conflictMessage = '冲突检测失败'
    }
  }

  async function calculateBatch() {
    if (!canCalculate.value || !articleId.value) {
      return ElMessage.warning(calculateHint.value || '请完善输入条件')
    }
    loading.value = true
    const sequence = ++requestSequence
    const active = () => sequence === requestSequence
    const request = {
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
      window_start_date: recommendWindow.value === 'CUSTOM' ? recommendStartDate.value : undefined,
      window_end_date: recommendWindow.value === 'CUSTOM' ? recommendEndDate.value : undefined,
    }
    lastError.value = ''
    batchResult.value = undefined
    planRows.value = []
    startCalcProgress()
    try {
      const response = await workflowApi.recommendBatch(request)
      if (!active()) return
      batchResult.value = response
      buildPlanRows(response)
      calcStep.value = 1
      await Promise.all(planRows.value.map((row) => refreshRowConflict(row)))
      if (!active()) return
      stopCalcProgress(true)
      if (!planRows.value.length) {
        lastError.value = '接口未返回任何平台结果，请检查该文章是否已生成对应平台版本。'
        ElMessage.warning(lastError.value)
        return
      }
      if (!activePlanRows.value.length) {
        lastError.value = '所有平台推荐均失败，请查看各平台错误后重试。'
        ElMessage.error(lastError.value)
        return
      }
      const solved = response.plan?.optimizationApplied
      const message = solved
        ? `已生成 ${response.successCount} 个平台的联合排期方案（求解状态 ${response.plan?.solverStatus}）`
        : `已生成 ${response.successCount} 个平台的推荐方案`
      if (
        response.failureCount ||
        planRows.value.some((row) => row.conflictMessage === '冲突检测失败')
      )
        ElMessage.warning(`${message}，部分推荐或冲突校验失败，请检查结果`)
      else ElMessage.success(message)
      // Bring the result table into view; otherwise a long wait looks like "nothing happened".
      requestAnimationFrame(() => {
        if (!active()) return
        document
          .querySelector('.result-table-wrap, .profile-panel')
          ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
    } catch (error) {
      if (!active()) return
      stopCalcProgress()
      calcPercent.value = 0
      calcStep.value = 0
      lastError.value = getApiErrorMessage(
        error,
        request.optimize
          ? '联合排期计算失败。可关闭上方语义开关后重试，或确认后端服务仍在运行。'
          : '推荐计算失败，请稍后重试',
      )
      ElMessage.error(lastError.value)
    } finally {
      if (active()) loading.value = false
    }
  }

  /** Keep an existing lock pinned to whatever time the operator just chose. */
  function syncLock(row: RecommendationPlanRow) {
    if (row.locked && row.selectedAt) lockedByPlatform[row.platform] = row.selectedAt
    else delete lockedByPlatform[row.platform]
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
    if (!row.customAt) {
      row.selectedAt = ''
      row.timeSource = 'CUSTOM'
      syncLock(row)
      return
    }
    row.selectedAt = toIso(row.customAt)
    row.timeSource = 'CUSTOM'
    syncLock(row)
    void refreshRowConflict(row)
  }

  function toggleSkip(row: RecommendationPlanRow) {
    row.skipped = !row.skipped
  }

  async function staggerOverlaps(minutes = 15) {
    if (minutes <= 0) return
    const groups = batchResult.value?.overlapGroups || []
    if (!groups.length) return
    const overlapSet = new Set(groups.flat())
    const affected = planRows.value
      .filter((row) => overlapSet.has(row.platform) && !row.skipped && row.recommendation)
      .sort((a, b) => new Date(a.selectedAt).getTime() - new Date(b.selectedAt).getTime())
    if (affected.length < 2) return
    const context = requestSequence
    const spacing = minutes * 60_000
    const occupied = affected
      .filter((row) => row.locked)
      .map((row) => new Date(row.selectedAt).getTime())
    let changed = 0
    for (const row of affected) {
      if (context !== requestSequence) return
      if (row.locked) continue
      const original = new Date(row.selectedAt).getTime()
      if (!Number.isFinite(original)) continue
      let at = original
      while (occupied.some((time) => Math.abs(time - at) < spacing)) {
        at = Math.max(...occupied.filter((time) => Math.abs(time - at) < spacing)) + spacing
      }
      occupied.push(at)
      if (at === original) continue
      row.selectedAt = new Date(at).toISOString()
      row.timeSource = 'CUSTOM'
      row.customAt = formatLocalInput(row.selectedAt)
      changed += 1
      await refreshRowConflict(row)
    }
    if (context === requestSequence)
      ElMessage.info(
        changed
          ? `已错开 ${changed} 个未锁定平台，锁定时间保持不变`
          : '当前时间已错开，锁定时间保持不变',
      )
  }

  async function createBatchSchedules() {
    if (!canSchedule.value || !articleId.value) return
    scheduling.value = true
    try {
      const payload = {
        article_id: articleId.value,
        content_type: contentType.value || undefined,
        items: activePlanRows.value
          .map((row) => {
            const account = accounts.value.find((item) => item.id === row.accountId)
            return normalizeSchedulePayload({
              platform: row.platform,
              variant_id: row.variantId,
              account_id: row.accountId,
              scheduled_at: row.selectedAt,
              recommendation_id: row.recommendation!.id,
              time_source: row.timeSource,
              recommended_at: row.recommendedAt,
              publish_mode: defaultPublishMode(row.platform, account),
            })
          })
          .sort(
            (a, b) =>
              a.platform.localeCompare(b.platform) ||
              a.account_id - b.account_id ||
              a.variant_id - b.variant_id,
          ),
      }
      const response = await workflowApi.createSchedulesBatch({
        ...payload,
        idempotency_key: batchCreateIntent.keyFor(payload),
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
