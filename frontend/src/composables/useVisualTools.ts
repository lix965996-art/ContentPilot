import { ref, watch, type ComputedRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import type { Article, MediaAsset } from '@/types/business'

type VisualMode = 'SEARCH' | 'GENERATE' | 'TRANSFORM'
type VisualOperationState = 'IDLE' | 'RUNNING' | 'SUCCESS' | 'FAILED'

interface VisualToolsOptions {
  selectedArticleId: Ref<number | undefined>
  currentVariantId: () => number | undefined
  media: Ref<MediaAsset[]>
  previewMedia: ComputedRef<MediaAsset[]>
}

export function useVisualTools({
  selectedArticleId,
  currentVariantId,
  media,
  previewMedia,
}: VisualToolsOptions) {
  const visualMode = ref<VisualMode>('SEARCH')
  const visualLoading = ref(false)
  const visualSearchLoading = ref(false)
  const visualOperationState = ref<VisualOperationState>('IDLE')
  const visualOperationProgress = ref(0)
  const visualOperationStage = ref('')
  const visualOperationElapsedMs = ref(0)
  const removingMediaId = ref<number>()
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

  let visualSearchSequence = 0
  let contextSequence = 0
  let actionSequence = 0
  let disposed = false
  let visualProgressTimer: number | undefined

  function invalidateContext() {
    contextSequence += 1
    actionSequence += 1
    visualSearchSequence += 1
    if (visualProgressTimer) window.clearInterval(visualProgressTimer)
    visualProgressTimer = undefined
    visualLoading.value = false
    visualSearchLoading.value = false
    removingMediaId.value = undefined
    visualOperationState.value = 'IDLE'
    visualOperationProgress.value = 0
    visualOperationStage.value = ''
    visualOperationElapsedMs.value = 0
    imageSearchResults.value = []
    visualNotice.value = ''
  }

  // Article identity alone is insufficient for A -> B -> A and unmounts.
  watch(selectedArticleId, invalidateContext, { flush: 'sync' })

  function beginAction() {
    const articleId = selectedArticleId.value
    if (!articleId || disposed || visualLoading.value) return
    const context = contextSequence
    const sequence = ++actionSequence
    visualLoading.value = true
    return {
      articleId,
      variantId: currentVariantId(),
      active: () =>
        !disposed &&
        context === contextSequence &&
        sequence === actionSequence &&
        articleId === selectedArticleId.value,
    }
  }

  async function loadImageModels() {
    if (disposed) return
    if (textImageModels.value.length || editImageModels.value.length) return
    const context = contextSequence
    try {
      const data = await workflowApi.imageModels()
      if (disposed || context !== contextSequence) return
      textImageModels.value = data.textToImage
      editImageModels.value = data.imageToImage
      if (!data.textToImage.includes(textImageModel.value) && data.textToImage[0])
        textImageModel.value = data.textToImage[0]
      if (!data.imageToImage.includes(editImageModel.value) && data.imageToImage[0])
        editImageModel.value = data.imageToImage[0]
    } catch (error) {
      if (!disposed && context === contextSequence)
        visualNotice.value = getApiErrorMessage(error, '读取图片模型失败')
    }
  }

  async function searchVisuals() {
    if (disposed) return
    const sequence = ++visualSearchSequence
    const articleId = selectedArticleId.value
    const keyword = visualKeyword.value.trim()
    const active = () =>
      !disposed && sequence === visualSearchSequence && articleId === selectedArticleId.value
    imageSearchResults.value = []
    visualNotice.value = ''
    visualSearchLoading.value = Boolean(keyword)
    if (!keyword) return
    try {
      const data = await workflowApi.searchMedia(keyword)
      if (!active()) return
      imageSearchResults.value = data.items.slice(0, 6).map((item) => ({
        ...item,
        searchKeyword: keyword,
      }))
      visualNotice.value = data.notice
    } catch (error) {
      if (active()) visualNotice.value = getApiErrorMessage(error, '图片搜索失败')
    } finally {
      if (active()) visualSearchLoading.value = false
    }
  }

  async function selectVisual(item: Record<string, unknown>, usageType: 'COVER' | 'BODY') {
    const ticket = beginAction()
    if (!ticket) return
    try {
      await workflowApi.selectMedia({
        article_id: ticket.articleId,
        variant_id: ticket.variantId,
        source: item.source,
        source_id: item.id,
        image_url: item.imageUrl,
        thumbnail_url: item.thumbnailUrl,
        photographer_name: item.photographerName,
        photographer_url: item.photographerUrl,
        alt_text: item.altText,
        search_keyword: item.searchKeyword ?? visualKeyword.value.trim(),
        usage_type: usageType,
      })
      if (!ticket.active()) return
      const assets = await workflowApi.articleMedia(ticket.articleId)
      if (!ticket.active()) return
      media.value = assets
      transformAssetId.value = media.value[0]?.id
      ElMessage.success(usageType === 'COVER' ? '已设为封面' : '已加入正文')
    } catch (error) {
      if (ticket.active()) ElMessage.error(getApiErrorMessage(error, '选择图片失败'))
    } finally {
      if (ticket.active()) visualLoading.value = false
    }
  }

  async function removePreviewMedia(item: MediaAsset) {
    const ticket = beginAction()
    if (!ticket || !media.value.some((asset) => asset.id === item.id)) {
      if (ticket?.active()) visualLoading.value = false
      return
    }
    removingMediaId.value = item.id
    try {
      const updated = await workflowApi.detachMedia(item.id)
      if (!ticket.active()) return
      media.value = media.value.map((asset) => (asset.id === updated.id ? updated : asset))
      if (transformAssetId.value === item.id) {
        transformAssetId.value = previewMedia.value[0]?.id
      }
      ElMessage.success('图片已移除，可以重新选择')
    } catch (error) {
      if (ticket.active()) ElMessage.error(getApiErrorMessage(error, '移除图片失败'))
    } finally {
      if (ticket.active()) {
        removingMediaId.value = undefined
        visualLoading.value = false
      }
    }
  }

  async function setPreviewCover(item: MediaAsset) {
    if (item.usageType === 'COVER') return
    const ticket = beginAction()
    if (!ticket || !media.value.some((asset) => asset.id === item.id)) {
      if (ticket?.active()) visualLoading.value = false
      return
    }
    try {
      await workflowApi.setMediaCover(item.id)
      if (!ticket.active()) return
      const assets = await workflowApi.articleMedia(ticket.articleId)
      if (!ticket.active()) return
      media.value = assets
      transformAssetId.value = item.id
      ElMessage.success('已更换封面，原封面保留在正文图片中')
    } catch (error) {
      if (ticket.active()) ElMessage.error(getApiErrorMessage(error, '更换封面失败'))
    } finally {
      if (ticket.active()) visualLoading.value = false
    }
  }

  async function generateVisual() {
    if (!selectedArticleId.value || !visualPrompt.value.trim()) {
      ElMessage.warning('请先填写图片创作要求')
      return
    }
    const ticket = beginAction()
    if (!ticket) return
    startVisualOperation('GENERATE')
    try {
      await workflowApi.generateImage({
        article_id: ticket.articleId,
        prompt: visualPrompt.value.trim(),
        model: textImageModel.value,
        image_size: imageSize.value,
        usage_type: 'COVER',
      })
      if (!ticket.active()) return
      const assets = await workflowApi.articleMedia(ticket.articleId)
      if (!ticket.active()) return
      media.value = assets
      transformAssetId.value = media.value[0]?.id
      finishVisualOperation(true, '图片已生成并保存为封面')
      ElMessage.success('AI 配图已生成并设为封面')
    } catch (error) {
      if (!ticket.active()) return
      finishVisualOperation(false, '生成失败，可以修改提示词后重试')
      ElMessage.error(getApiErrorMessage(error, 'AI 图片生成失败'))
    } finally {
      if (ticket.active()) visualLoading.value = false
    }
  }

  async function transformVisual() {
    if (!selectedArticleId.value) {
      ElMessage.warning('请先选择一篇文章')
      return
    }
    if (!transformAssetId.value) {
      ElMessage.warning('请先选择要改造的图片')
      return
    }
    if (!visualPrompt.value.trim()) {
      ElMessage.warning('请先填写图片改造要求')
      return
    }
    const ticket = beginAction()
    if (!ticket) return
    startVisualOperation('TRANSFORM')
    try {
      await workflowApi.transformImage({
        article_id: ticket.articleId,
        asset_id: transformAssetId.value,
        prompt: visualPrompt.value.trim(),
        model: editImageModel.value,
        usage_type: 'COVER',
      })
      if (!ticket.active()) return
      const assets = await workflowApi.articleMedia(ticket.articleId)
      if (!ticket.active()) return
      media.value = assets
      transformAssetId.value = media.value[0]?.id
      finishVisualOperation(true, '改造版本已生成并保存为封面')
      ElMessage.success('AI 图片改造完成并设为封面')
    } catch (error) {
      if (!ticket.active()) return
      finishVisualOperation(false, '改造失败，原图未受影响，可以重试')
      ElMessage.error(getApiErrorMessage(error, 'AI 图片改造失败'))
    } finally {
      if (ticket.active()) visualLoading.value = false
    }
  }

  function startVisualOperation(mode: 'GENERATE' | 'TRANSFORM') {
    if (visualProgressTimer) window.clearInterval(visualProgressTimer)
    const startedAt = Date.now()
    visualLoading.value = true
    visualOperationState.value = 'RUNNING'
    visualOperationProgress.value = 0
    visualOperationElapsedMs.value = 0
    visualOperationStage.value =
      mode === 'TRANSFORM' ? '已提交图片改造请求，等待模型响应' : '已提交图片生成请求，等待模型响应'
    visualProgressTimer = window.setInterval(() => {
      visualOperationElapsedMs.value = Date.now() - startedAt
    }, 500)
  }

  function finishVisualOperation(success: boolean, message: string) {
    if (visualProgressTimer) window.clearInterval(visualProgressTimer)
    visualProgressTimer = undefined
    visualOperationState.value = success ? 'SUCCESS' : 'FAILED'
    visualOperationProgress.value = success ? 100 : visualOperationProgress.value
    visualOperationStage.value = message
  }

  function resetForArticle(article: Article, assets: MediaAsset[]) {
    invalidateContext()
    disposed = false
    transformAssetId.value = assets[0]?.id
    visualKeyword.value = article.topic || article.title
    visualPrompt.value = `为文章《${article.title}》创作一张专业、真实、具有编辑感的配图，无文字、无水印、无品牌 Logo。${article.summary || article.topic || ''}`
    void searchVisuals()
  }

  function dispose() {
    disposed = true
    invalidateContext()
  }

  watch(visualMode, (mode) => {
    if (!visualLoading.value) {
      visualOperationState.value = 'IDLE'
      visualOperationProgress.value = 0
      visualOperationStage.value = ''
      visualOperationElapsedMs.value = 0
    }
    if (mode === 'SEARCH' && !imageSearchResults.value.length) void searchVisuals()
    if (mode !== 'SEARCH') void loadImageModels()
  })

  return {
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
    loadImageModels,
    searchVisuals,
    selectVisual,
    removePreviewMedia,
    setPreviewCover,
    generateVisual,
    transformVisual,
    resetForArticle,
    dispose,
  }
}

export type VisualTools = ReturnType<typeof useVisualTools>
