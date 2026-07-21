<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Clipboard, FilePenLine, RefreshCw, Save } from 'lucide-vue-next'

import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import type { Article, Platform, Variant } from '@/types/business'
import { platformNames } from '@/types/business'

const route = useRoute()
const articles = ref<Article[]>([])
const selectedArticleId = ref<number>()
const article = ref<Article>()
const variants = ref<Variant[]>([])
const activePlatform = ref<Platform>('WEIBO')
const generating = ref(false)
const options = reactive({
  platforms: ['WEIBO', 'XIAOHONGSHU', 'WECHAT_OFFICIAL'] as Platform[],
  style: '专业自然',
  length: 'MEDIUM',
  include_emoji: true,
  include_hashtags: true,
  preserve_meaning: 90,
})
const editing = reactive({ title: '', content_text: '', hashtags: [] as string[] })
const current = computed(
  () =>
    variants.value
      .filter((x) => x.platform === activePlatform.value)
      .sort((a, b) => b.versionNo - a.versionNo)[0],
)

async function loadArticles() {
  const data = await workflowApi.articles({ page_size: 100 })
  articles.value = data.items
  const queryId = Number(route.query.article)
  selectedArticleId.value = queryId || data.items[0]?.id
  if (selectedArticleId.value) await loadArticle()
}
async function loadArticle() {
  if (!selectedArticleId.value) return
  article.value = await workflowApi.article(selectedArticleId.value)
  variants.value = article.value.variants || (await workflowApi.variants(selectedArticleId.value))
  syncEditor()
}
function syncEditor() {
  editing.title = current.value?.title || ''
  editing.content_text = current.value?.contentText || ''
  editing.hashtags = current.value?.hashtagsJson || []
}
watch(current, syncEditor)
async function generate() {
  if (!selectedArticleId.value || !options.platforms.length)
    return ElMessage.warning('请选择原文和目标平台')
  generating.value = true
  try {
    const task = await workflowApi.generate({ article_id: selectedArticleId.value, ...options })
    const result = await workflowApi.task(task.taskId)
    variants.value = result.variants || (await workflowApi.variants(selectedArticleId.value))
    activePlatform.value = options.platforms[0]
    ElMessage.success('三个平台版本已生成')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '生成失败'))
  } finally {
    generating.value = false
  }
}
async function save() {
  if (!current.value) return
  const value = await workflowApi.updateVariant(current.value.id, editing)
  variants.value = variants.value.map((x) => (x.id === value.id ? value : x))
  ElMessage.success('修改已保存')
}
async function approve() {
  if (!current.value) return
  const value = await workflowApi.approveVariant(current.value.id)
  variants.value = variants.value.map((x) => (x.id === value.id ? value : x))
  ElMessage.success('已审核通过')
}
async function regenerate() {
  if (!current.value) return
  generating.value = true
  try {
    const task = await workflowApi.regenerate(current.value.id)
    const result = await workflowApi.task(task.taskId)
    variants.value = [...(result.variants || []), ...variants.value]
    ElMessage.success('已生成新版本')
  } finally {
    generating.value = false
  }
}
async function copy() {
  await navigator.clipboard.writeText(
    `${editing.title}\n\n${editing.content_text}\n\n${editing.hashtags.join(' ')}`,
  )
  ElMessage.success('已复制')
}
onMounted(() => loadArticles().catch((e) => ElMessage.error(getApiErrorMessage(e))))
</script>

<template>
  <div>
    <PageHeader
      title="平台内容适配"
      description="基于原文生成不同平台版本，所有结果须经人工审核后才能排期。"
    />
    <section class="studio-grid">
      <aside class="workspace-panel p-5">
        <p class="section-label">01 · 选择原文</p>
        <el-select
          v-model="selectedArticleId"
          filterable
          class="mt-3 w-full"
          placeholder="选择文章"
          @change="loadArticle"
          ><el-option v-for="item in articles" :key="item.id" :label="item.title" :value="item.id"
        /></el-select>
        <template v-if="article"
          ><h2 class="mt-6 text-base font-semibold text-ink">{{ article.title }}</h2>
          <div class="mt-3 flex gap-2">
            <StatusBadge :status="article.status" /><span class="meta-chip">{{
              article.topic || '未分类'
            }}</span>
          </div>
          <p class="source-preview">{{ article.sourceText }}</p>
          <dl class="info-list">
            <div>
              <dt>受众</dt>
              <dd>{{ article.targetAudience || '未设置' }}</dd>
            </div>
            <div>
              <dt>语气</dt>
              <dd>{{ article.tone || '专业自然' }}</dd>
            </div>
          </dl></template
        >
      </aside>
      <section class="workspace-panel p-5">
        <p class="section-label">02 · 生成配置</p>
        <el-form label-position="top" class="mt-4"
          ><el-form-item label="目标平台"
            ><el-checkbox-group v-model="options.platforms" class="platform-options"
              ><el-checkbox-button v-for="(name, key) in platformNames" :key="key" :value="key">{{
                name
              }}</el-checkbox-button></el-checkbox-group
            ></el-form-item
          ><el-form-item label="内容风格"
            ><el-select v-model="options.style" class="w-full"
              ><el-option label="专业自然" value="专业自然" /><el-option
                label="轻松亲切"
                value="轻松亲切" /><el-option
                label="简洁有力"
                value="简洁有力" /></el-select></el-form-item
          ><el-form-item label="保留原意程度"
            ><el-slider v-model="options.preserve_meaning" :min="50" :max="100" show-input
          /></el-form-item>
          <div class="space-y-3">
            <el-switch
              v-model="options.include_emoji"
              active-text="生成适量 Emoji"
            /><br /><el-switch v-model="options.include_hashtags" active-text="生成平台标签" /></div
        ></el-form>
        <el-button type="primary" class="mt-7 !h-11 !w-full" :loading="generating" @click="generate"
          ><FilePenLine :size="17" class="mr-2" />{{
            generating ? '正在生成…' : '生成平台版本'
          }}</el-button
        >
        <p class="mt-3 text-xs leading-5 text-muted">
          需要管理员先在系统设置中配置真实模型接口；未配置时系统不会生成占位内容。
        </p>
      </section>
      <section class="workspace-panel min-w-0 overflow-hidden">
        <div class="flex items-center justify-between border-b border-line px-5 py-3">
          <el-tabs v-model="activePlatform" class="compact-tabs"
            ><el-tab-pane v-for="(name, key) in platformNames" :key="key" :label="name" :name="key"
          /></el-tabs>
          <div v-if="current" class="flex gap-1">
            <el-button link @click="copy"><Clipboard :size="15" /></el-button
            ><el-button link :loading="generating" @click="regenerate"
              ><RefreshCw :size="15"
            /></el-button>
          </div>
        </div>
        <div v-if="current" class="p-5">
          <div class="mb-4 flex flex-wrap items-center gap-2">
            <StatusBadge :status="current.reviewStatus" /><span class="meta-chip"
              >v{{ current.versionNo }}</span
            ><span class="meta-chip">质量 {{ current.qualityScore }}</span
            ><span class="meta-chip">修改 {{ current.manualEditRatio }}%</span
            ><span class="meta-chip"
              >{{ current.generationDurationMs }}ms · {{ current.tokenUsage }} tokens</span
            >
          </div>
          <el-input v-model="editing.title" class="title-input" /><el-input
            v-model="editing.content_text"
            type="textarea"
            :autosize="{ minRows: 13, maxRows: 24 }"
            class="mt-3 content-editor"
          /><el-select
            v-model="editing.hashtags"
            multiple
            allow-create
            filterable
            class="mt-3 w-full"
            placeholder="标签"
          />
          <div class="mt-4 flex justify-between">
            <span class="text-xs text-muted"
              >{{ editing.content_text.length }} 字 · Prompt {{ current.promptVersion }}</span
            >
            <div>
              <el-button @click="save"><Save :size="15" class="mr-1" />保存</el-button
              ><el-button type="success" plain @click="approve"
                ><Check :size="15" class="mr-1" />审核通过</el-button
              >
            </div>
          </div>
        </div>
        <div v-else class="empty-state min-h-[500px]">
          <FilePenLine :size="30" />
          <p>等待生成平台版本</p>
          <span>选择左侧原文并配置目标平台，然后开始生成。</span>
        </div>
      </section>
    </section>
  </div>
</template>
