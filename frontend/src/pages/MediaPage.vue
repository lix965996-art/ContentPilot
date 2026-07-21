<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Image, Search, Upload } from 'lucide-vue-next'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import PageHeader from '@/components/PageHeader.vue'
import type { Article } from '@/types/business'

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
  articleId.value = data.items[0]?.id
  if (articleId.value) await extract()
}
async function extract() {
  if (!articleId.value) return
  loading.value = true
  try {
    const data = await workflowApi.keywords(articleId.value)
    keywords.value = data.keywords
    activeKeyword.value = data.keywords[0]?.en || 'creative editorial'
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
    ElMessage.success('素材已上传并关联到文章')
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e, '上传失败'))
  } finally {
    uploading.value = false
  }
}
async function chooseKeyword(keyword: string) {
  activeKeyword.value = keyword
  await search()
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
  ElMessage.success(usage === 'COVER' ? '已设为封面' : '已加入正文配图')
  selected.value = await workflowApi.articleMedia(articleId.value)
}
onMounted(init)
</script>
<template>
  <div>
    <PageHeader
      title="素材管理"
      description="上传自己的图片，或配置 Unsplash 后按文章关键词检索公开素材。"
      ><el-upload
        :show-file-list="false"
        :http-request="upload"
        accept="image/jpeg,image/png,image/webp,image/gif"
        ><el-button type="primary" :loading="uploading"
          ><Upload :size="15" class="mr-2" />上传图片</el-button
        ></el-upload
      ></PageHeader
    >
    <section class="panel rounded-xl p-5">
      <div class="flex flex-wrap items-end gap-3">
        <label class="field-label"
          >关联文章<el-select v-model="articleId" filterable class="mt-2 !w-80" @change="extract"
            ><el-option
              v-for="item in articles"
              :key="item.id"
              :label="item.title"
              :value="item.id" /></el-select></label
        ><el-button :loading="loading" @click="extract"
          ><Search :size="15" class="mr-2" />提取并搜索</el-button
        >
        <div class="ml-auto text-xs text-muted">已选 {{ selected.length }} 张</div>
      </div>
      <div class="mt-5 flex flex-wrap gap-2">
        <button
          v-for="item in keywords"
          :key="item.en"
          class="keyword-pill"
          :class="{ active: activeKeyword === item.en }"
          @click="chooseKeyword(item.en)"
        >
          <span>{{ item.zh }}</span
          ><small>{{ item.en }}</small>
        </button>
      </div>
    </section>
    <section class="mt-4">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="section-title">推荐图片</h2>
        <span class="text-xs text-muted">{{ notice }}</span>
      </div>
      <div class="media-grid">
        <article v-for="item in images" :key="String(item.id)" class="media-card">
          <img :src="String(item.thumbnailUrl)" :alt="String(item.altText)" />
          <div class="p-3">
            <p class="truncate text-sm font-medium text-ink">{{ item.altText }}</p>
            <p class="mt-1 text-xs text-muted">{{ item.photographerName }} · {{ item.source }}</p>
            <div class="mt-3 grid grid-cols-2 gap-2">
              <el-button size="small" @click="select(item, 'BODY')">加入正文</el-button
              ><el-button size="small" type="primary" plain @click="select(item, 'COVER')"
                >设为封面</el-button
              >
            </div>
          </div>
        </article>
      </div>
      <div v-if="!images.length" class="empty-state panel min-h-80 rounded-xl">
        <Image :size="30" />
        <p>暂无推荐图片</p>
        <span>可直接上传本地图片；在线检索需要管理员配置 Unsplash Access Key。</span>
      </div>
    </section>
  </div>
</template>
