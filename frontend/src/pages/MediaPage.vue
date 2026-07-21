<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Image, Search, Upload } from 'lucide-vue-next'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import type { Article } from '@/types/business'
const route = useRoute()
const articles = ref<Article[]>([])
const articleId = ref<number>()
const keywords = ref<Array<{ zh: string; en: string; reason: string }>>([])
const activeKeyword = ref('')
const images = ref<Array<Record<string, unknown>>>([])
const selected = ref<Array<Record<string, unknown>>>([])
const loading = ref(false)
const uploading = ref(false)
const notice = ref('')
async function init() {
  const data = await workflowApi.articles({ page_size: 100 })
  articles.value = data.items
  const queryId = Number(route.query.article)
  articleId.value = data.items.some((item) => item.id === queryId) ? queryId : data.items[0]?.id
  if (articleId.value) await extract()
}
async function extract() {
  if (!articleId.value) return
  loading.value = true
  try {
    const data = await workflowApi.keywords(articleId.value)
    keywords.value = data.keywords
    activeKeyword.value = data.keywords[0]?.en || 'editorial'
    await search()
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  } finally {
    loading.value = false
  }
}
async function search() {
  if (!activeKeyword.value) return
  const data = await workflowApi.searchMedia(activeKeyword.value)
  images.value = data.items
  notice.value = data.notice
  selected.value = await workflowApi.articleMedia(articleId.value!)
}
function chooseKeyword(value: string) {
  activeKeyword.value = value
  void search()
}
async function upload(options: any) {
  if (!articleId.value) return ElMessage.warning('请先选择关联文章')
  const body = new FormData()
  body.append('article_id', String(articleId.value))
  body.append('usage_type', 'BODY')
  body.append('file', options.file)
  uploading.value = true
  try {
    await workflowApi.uploadMedia(body)
    selected.value = await workflowApi.articleMedia(articleId.value)
    ElMessage.success('素材已上传')
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e, '上传失败'))
  } finally {
    uploading.value = false
  }
}
async function select(image: Record<string, unknown>, usage: 'COVER' | 'BODY') {
  if (!articleId.value) return
  await workflowApi.selectMedia({
    article_id: articleId.value,
    source: image.source,
    source_id: image.id,
    image_url: image.imageUrl,
    thumbnail_url: image.thumbnailUrl,
    photographer_name: image.photographerName,
    photographer_url: image.photographerUrl,
    alt_text: image.altText,
    search_keyword: activeKeyword.value,
    usage_type: usage,
  })
  selected.value = await workflowApi.articleMedia(articleId.value)
  ElMessage.success(usage === 'COVER' ? '已设为封面' : '已加入正文')
}
onMounted(init)
</script>
<template>
  <div>
    <PageHeader title="媒体库" description="检索、上传并管理内容使用的封面和正文图片。"
      ><el-upload
        :show-file-list="false"
        :http-request="upload"
        accept="image/jpeg,image/png,image/webp,image/gif"
        ><el-button type="primary" :loading="uploading"
          ><Upload :size="15" class="mr-2" />上传图片</el-button
        ></el-upload
      ></PageHeader
    >
    <div class="media-workspace">
      <aside class="media-filters">
        <div>
          <label>关联内容</label
          ><el-select v-model="articleId" filterable class="w-full" @change="extract"
            ><el-option
              v-for="item in articles"
              :key="item.id"
              :label="item.title"
              :value="item.id"
          /></el-select>
        </div>
        <div>
          <label>关键词</label>
          <div class="keyword-list">
            <button
              v-for="item in keywords"
              :key="item.en"
              :class="{ active: activeKeyword === item.en }"
              @click="chooseKeyword(item.en)"
            >
              {{ item.zh }}<small>{{ item.en }}</small>
            </button>
          </div>
        </div>
      </aside>
      <main class="media-results">
        <div class="media-results-head">
          <div class="media-search">
            <Search :size="15" /><input
              v-model="activeKeyword"
              placeholder="输入图片关键词"
              @keyup.enter="search"
            /><button @click="search">搜索</button>
          </div>
          <span>{{ notice || `${images.length} 张图片` }}</span>
        </div>
        <div v-if="images.length" class="media-masonry">
          <article v-for="item in images" :key="String(item.id)">
            <img :src="String(item.thumbnailUrl)" :alt="String(item.altText)" />
            <div>
              <p>{{ item.altText }}</p>
              <small>{{ item.photographerName }} · {{ item.source }}</small
              ><button @click="select(item, 'BODY')">加入正文</button
              ><button @click="select(item, 'COVER')">设为封面</button>
            </div>
          </article>
        </div>
        <EmptyState v-else title="没有可显示的在线素材"
          ><template #icon><Image :size="28" /></template
        ></EmptyState>
      </main>
      <aside class="selected-media">
        <header>
          <strong>已选图片</strong><span>{{ selected.length }}</span>
        </header>
        <div v-if="selected.length" class="selected-list">
          <article v-for="item in selected" :key="String(item.id)">
            <img :src="String(item.thumbnailUrl)" />
            <div>
              <b>{{ item.usageType === 'COVER' ? '封面' : '正文插图' }}</b
              ><span>{{ item.altText || '未填写 Alt 文本' }}</span>
            </div>
          </article>
        </div>
        <EmptyState v-else title="尚未选择图片"
          ><template #icon><Image :size="24" /></template
        ></EmptyState>
      </aside>
    </div>
  </div>
</template>
