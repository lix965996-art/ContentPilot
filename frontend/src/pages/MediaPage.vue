<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Check, FolderOpen, Heart, Image, Info, Search, Upload } from 'lucide-vue-next'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import type { Article, MediaAsset } from '@/types/business'

const route = useRoute()
const router = useRouter()
const articles = ref<Article[]>([])
const articleId = ref<number>()
const view = ref<'library' | 'search'>('library')
const assets = ref<MediaAsset[]>([])
const selectedAsset = ref<MediaAsset>()
const collections = ref<string[]>([])
const collection = ref('')
const onlyFavorite = ref(false)
const assetQuery = ref('')
const keywords = ref<Array<{ zh: string; en: string; reason: string }>>([])
const activeKeyword = ref('')
const resultsKeyword = ref('')
const images = ref<Array<Record<string, unknown>>>([])
const selectedForArticle = ref<MediaAsset[]>([])
const loading = ref(false)
const uploading = ref(false)
const saving = ref(false)
const notice = ref('')
let articleContextSequence = 0
let extractSequence = 0
let searchSequence = 0
let loadedArticleId: number | undefined
const metadata = ref({
  title: '',
  collection: '',
  tags: [] as string[],
  altText: '',
  licenseType: '',
  licenseNote: '',
  favorite: false,
})

const visibleAssets = computed(() =>
  assets.value.filter(
    (item) =>
      (!collection.value || item.collection === collection.value) &&
      (!onlyFavorite.value || item.favorite),
  ),
)

async function init() {
  const data = await workflowApi.articles({ page_size: 100 })
  articles.value = data.items
  const queryId = Number(route.query.article)
  articleId.value = data.items.some((item) => item.id === queryId) ? queryId : undefined
  await loadAssets()
  if (articleId.value) await loadArticleContext()
}

async function loadAssets() {
  loading.value = true
  try {
    const data = await workflowApi.mediaAssets({ query: assetQuery.value })
    assets.value = data.items
    collections.value = data.collections
    if (selectedAsset.value) {
      const fresh = assets.value.find((item) => item.id === selectedAsset.value?.id)
      selectedAsset.value = fresh
      if (fresh) fillMetadata(fresh)
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '素材库加载失败'))
  } finally {
    loading.value = false
  }
}

async function loadArticleContext() {
  const target = articleId.value
  const sequence = ++articleContextSequence
  if (!target) {
    loadedArticleId = undefined
    selectedForArticle.value = []
    keywords.value = []
    activeKeyword.value = ''
    resultsKeyword.value = ''
    images.value = []
    notice.value = ''
    return
  }
  if (loadedArticleId !== target) {
    // Switching articles: clear state that belongs to the previous context.
    selectedForArticle.value = []
    keywords.value = []
    activeKeyword.value = ''
    resultsKeyword.value = ''
    images.value = []
    notice.value = ''
  }
  try {
    const data = await workflowApi.articleMedia(target)
    if (sequence !== articleContextSequence || target !== articleId.value) return
    selectedForArticle.value = data
    loadedArticleId = target
    if (view.value === 'search' && !keywords.value.length) {
      await extract(target, sequence)
    }
  } catch (error) {
    if (sequence === articleContextSequence && target === articleId.value) {
      ElMessage.error(getApiErrorMessage(error, '文章素材加载失败'))
    }
  }
}

function fillMetadata(asset: MediaAsset) {
  selectedAsset.value = asset
  metadata.value = {
    title: asset.title || asset.altText || '',
    collection: asset.collection || '',
    tags: [...(asset.tags || [])],
    altText: asset.altText || '',
    licenseType: asset.licenseType || '',
    licenseNote: asset.licenseNote || '',
    favorite: Boolean(asset.favorite),
  }
}

async function saveMetadata() {
  if (!selectedAsset.value) return
  saving.value = true
  try {
    const updated = await workflowApi.updateMedia(selectedAsset.value.id, {
      title: metadata.value.title,
      collection: metadata.value.collection,
      tags: metadata.value.tags,
      alt_text: metadata.value.altText,
      license_type: metadata.value.licenseType,
      license_note: metadata.value.licenseNote,
      favorite: metadata.value.favorite,
    })
    fillMetadata(updated)
    await loadAssets()
    ElMessage.success('素材信息已保存')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存失败'))
  } finally {
    saving.value = false
  }
}

async function toggleFavorite(asset: MediaAsset) {
  try {
    await workflowApi.updateMedia(asset.id, { favorite: !asset.favorite })
    await loadAssets()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '收藏状态更新失败'))
  }
}

async function upload(options: any) {
  const target = articleId.value
  const body = new FormData()
  if (target) body.append('article_id', String(target))
  body.append('usage_type', 'BODY')
  body.append('file', options.file)
  uploading.value = true
  try {
    await workflowApi.uploadMedia(body)
    await loadAssets()
    if (target === articleId.value) await loadArticleContext()
    ElMessage.success(target ? '素材已上传并关联内容' : '素材已上传到资产库')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '上传失败'))
  } finally {
    uploading.value = false
  }
}

async function attach(asset: MediaAsset, usageType: 'COVER' | 'BODY') {
  const target = articleId.value
  if (!target) return ElMessage.warning('请先选择要使用素材的内容')
  try {
    await workflowApi.attachMedia(asset.id, target, usageType)
    await loadAssets()
    if (target === articleId.value) {
      await loadArticleContext()
      ElMessage.success(usageType === 'COVER' ? '已设为封面' : '已加入正文')
    } else {
      ElMessage.success('已关联到之前选择的内容')
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '关联素材失败'))
  }
}

async function extract(target = articleId.value, contextSequence = articleContextSequence) {
  if (!target || target !== articleId.value) return
  const sequence = ++extractSequence
  loading.value = true
  try {
    const data = await workflowApi.keywords(target)
    if (
      sequence !== extractSequence ||
      contextSequence !== articleContextSequence ||
      target !== articleId.value
    ) {
      return
    }
    keywords.value = data.keywords
    activeKeyword.value = data.keywords[0]?.en || 'editorial'
    await searchOnline(target, sequence, contextSequence)
  } catch (error) {
    if (sequence === extractSequence && target === articleId.value) {
      ElMessage.error(getApiErrorMessage(error))
    }
  } finally {
    if (sequence === extractSequence) loading.value = false
  }
}

async function searchOnline(
  target = articleId.value,
  extractSeq = extractSequence,
  contextSeq = articleContextSequence,
  manual = false,
) {
  if (!target || target !== articleId.value) {
    return ElMessage.warning('在线选图前请先选择关联内容')
  }
  if (manual) {
    // An explicit keyword/search must not be overwritten by an older auto extraction.
    extractSequence += 1
    extractSeq = extractSequence
    loading.value = false
  }
  const keyword = activeKeyword.value
  if (!keyword) return
  const sequence = ++searchSequence
  try {
    const data = await workflowApi.searchMedia(keyword)
    if (
      sequence !== searchSequence ||
      extractSeq !== extractSequence ||
      contextSeq !== articleContextSequence ||
      target !== articleId.value ||
      keyword !== activeKeyword.value
    ) {
      return
    }
    images.value = data.items
    notice.value = data.notice
    resultsKeyword.value = keyword
  } catch (error) {
    if (
      sequence === searchSequence &&
      target === articleId.value &&
      keyword === activeKeyword.value
    ) {
      ElMessage.error(getApiErrorMessage(error, '图片搜索失败'))
    }
  }
}

function manualSearch() {
  void searchOnline(undefined, undefined, undefined, true)
}

async function selectOnline(image: Record<string, unknown>, usage: 'COVER' | 'BODY') {
  const target = articleId.value
  if (!target) return
  const keyword = activeKeyword.value
  try {
    await workflowApi.selectMedia({
      article_id: target,
      source: image.source,
      source_id: image.id,
      image_url: image.imageUrl,
      thumbnail_url: image.thumbnailUrl,
      photographer_name: image.photographerName,
      photographer_url: image.photographerUrl,
      alt_text: image.altText,
      search_keyword: resultsKeyword.value || keyword,
      title: image.altText,
      license_type: image.licenseName,
      license_note: image.licenseUrl,
      usage_type: usage,
    })
    await loadAssets()
    if (target === articleId.value) {
      await loadArticleContext()
      ElMessage.success(usage === 'COVER' ? '已设为封面' : '已加入正文')
    } else {
      ElMessage.success('已关联到之前选择的内容')
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '选择图片失败'))
  }
}

function changeView(value: 'library' | 'search') {
  view.value = value
  if (value === 'search' && articleId.value && !keywords.value.length) void extract()
}

function resetAssetFilter() {
  collection.value = ''
  onlyFavorite.value = false
}

function chooseCollection(value: string) {
  collection.value = value
  onlyFavorite.value = false
}

function chooseKeyword(value: string) {
  activeKeyword.value = value
  void searchOnline(undefined, undefined, undefined, true)
}

function returnToStudio() {
  if (articleId.value) void router.push({ name: 'studio', query: { article: articleId.value } })
}

onMounted(init)
</script>

<template>
  <div>
    <PageHeader title="媒体资产" description="集中管理、检索和复用图片，并记录来源与版权信息。">
      <el-button v-if="route.query.returnTo === 'studio'" @click="returnToStudio">
        <ArrowLeft :size="15" class="mr-1" />返回工作室
      </el-button>
      <el-upload
        :show-file-list="false"
        :http-request="upload"
        accept="image/jpeg,image/png,image/webp,image/gif"
      >
        <el-button type="primary" :loading="uploading">
          <Upload :size="15" class="mr-1" />上传图片
        </el-button>
      </el-upload>
    </PageHeader>

    <div class="content-tabs media-tabs">
      <button :class="{ active: view === 'library' }" @click="changeView('library')">
        <FolderOpen :size="14" />资产库 <span>{{ assets.length }}</span>
      </button>
      <button :class="{ active: view === 'search' }" @click="changeView('search')">
        <Search :size="14" />在线选图
      </button>
    </div>

    <section class="asset-context">
      <label>使用到内容</label>
      <el-select
        v-model="articleId"
        clearable
        filterable
        placeholder="可选；选择后可直接设为封面或正文图"
        @change="loadArticleContext"
      >
        <el-option v-for="item in articles" :key="item.id" :label="item.title" :value="item.id" />
      </el-select>
      <span v-if="articleId">{{ selectedForArticle.length }} 张已关联</span>
      <span v-else>当前上传将保存为全局素材</span>
    </section>

    <section v-if="view === 'library'" v-loading="loading" class="asset-workspace">
      <aside class="asset-sidebar">
        <span>集合</span>
        <button :class="{ active: !collection && !onlyFavorite }" @click="resetAssetFilter">
          全部素材 <small>{{ assets.length }}</small>
        </button>
        <button :class="{ active: onlyFavorite }" @click="onlyFavorite = !onlyFavorite">
          <Heart :size="13" />收藏
          <small>{{ assets.filter((item) => item.favorite).length }}</small>
        </button>
        <button
          v-for="item in collections"
          :key="item"
          :class="{ active: collection === item }"
          @click="chooseCollection(item)"
        >
          {{ item }}
        </button>
      </aside>

      <main class="asset-results">
        <header>
          <div class="media-search">
            <Search :size="15" />
            <input
              v-model="assetQuery"
              placeholder="搜索标题、Alt、作者或关键词"
              @keyup.enter="loadAssets"
            />
            <button @click="loadAssets">搜索</button>
          </div>
          <span>{{ visibleAssets.length }} 项</span>
        </header>
        <div v-if="visibleAssets.length" class="asset-grid">
          <article
            v-for="item in visibleAssets"
            :key="item.id"
            :class="{ selected: selectedAsset?.id === item.id }"
            @click="fillMetadata(item)"
          >
            <div class="asset-image">
              <img :src="item.thumbnailUrl" :alt="item.altText || item.title || '素材图片'" />
              <button :class="{ active: item.favorite }" @click.stop="toggleFavorite(item)">
                <Heart :size="14" :fill="item.favorite ? 'currentColor' : 'none'" />
              </button>
            </div>
            <div class="asset-card-body">
              <b>{{ item.title || item.altText || '未命名素材' }}</b>
              <small
                >{{ item.collection || item.source
                }}<template v-if="item.articleTitle"> · {{ item.articleTitle }}</template></small
              >
              <footer v-if="articleId">
                <button @click.stop="attach(item, 'BODY')">正文</button>
                <button @click.stop="attach(item, 'COVER')">封面</button>
              </footer>
            </div>
          </article>
        </div>
        <EmptyState v-else title="当前筛选下没有素材">
          <template #icon><Image :size="26" /></template>
        </EmptyState>
      </main>

      <aside class="asset-detail">
        <template v-if="selectedAsset">
          <header>
            <b>素材信息</b><span>#{{ selectedAsset.id }}</span>
          </header>
          <img :src="selectedAsset.thumbnailUrl" :alt="selectedAsset.altText" />
          <el-form label-position="top" size="small">
            <el-form-item label="名称"><el-input v-model="metadata.title" /></el-form-item>
            <el-form-item label="集合"
              ><el-input v-model="metadata.collection" placeholder="例如：品牌图库"
            /></el-form-item>
            <el-form-item label="标签">
              <el-select
                v-model="metadata.tags"
                multiple
                filterable
                allow-create
                default-first-option
                class="w-full"
              />
            </el-form-item>
            <el-form-item label="Alt 文本"><el-input v-model="metadata.altText" /></el-form-item>
            <div class="grid grid-cols-2 gap-2">
              <el-form-item label="版权类型"
                ><el-input v-model="metadata.licenseType" placeholder="CC / 授权"
              /></el-form-item>
              <el-form-item label="收藏"><el-switch v-model="metadata.favorite" /></el-form-item>
            </div>
            <el-form-item label="版权备注">
              <el-input
                v-model="metadata.licenseNote"
                type="textarea"
                :rows="2"
                placeholder="来源、使用范围或到期时间"
              />
            </el-form-item>
          </el-form>
          <div class="asset-source-note">
            <Info :size="13" />
            <span
              >{{ selectedAsset.photographerName || selectedAsset.source
              }}<template v-if="selectedAsset.articleTitle">
                · 已用于 {{ selectedAsset.articleTitle }}</template
              ></span
            >
          </div>
          <el-button type="primary" class="w-full" :loading="saving" @click="saveMetadata">
            <Check :size="14" class="mr-1" />保存信息
          </el-button>
        </template>
        <EmptyState v-else title="选择素材查看详情">
          <template #icon><Info :size="24" /></template>
        </EmptyState>
      </aside>
    </section>

    <section v-else class="online-media-workspace">
      <aside>
        <span>内容关键词</span>
        <button
          v-for="item in keywords"
          :key="item.en"
          :class="{ active: activeKeyword === item.en }"
          @click="chooseKeyword(item.en)"
        >
          {{ item.zh }}<small>{{ item.en }}</small>
        </button>
        <p v-if="!articleId">选择关联内容后，系统会提取适合搜索的双语关键词。</p>
      </aside>
      <main>
        <header>
          <div class="media-search">
            <Search :size="15" />
            <input
              v-model="activeKeyword"
              placeholder="输入图片关键词"
              @keyup.enter="manualSearch"
            />
            <button @click="manualSearch">搜索</button>
          </div>
          <span
            >{{ notice
            }}<template v-if="resultsKeyword"> · 结果关键词：{{ resultsKeyword }}</template></span
          >
        </header>
        <div v-if="images.length" class="media-masonry">
          <article v-for="item in images" :key="String(item.id)">
            <img :src="String(item.thumbnailUrl)" :alt="String(item.altText)" />
            <div>
              <p>{{ item.altText }}</p>
              <small>{{ item.photographerName }} · {{ item.source }}</small>
              <button @click="selectOnline(item, 'BODY')">加入正文</button>
              <button @click="selectOnline(item, 'COVER')">设为封面</button>
            </div>
          </article>
        </div>
        <EmptyState v-else title="选择内容并输入关键词开始搜索">
          <template #icon><Search :size="26" /></template>
        </EmptyState>
      </main>
    </section>
  </div>
</template>
