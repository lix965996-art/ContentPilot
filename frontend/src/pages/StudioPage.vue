<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Check,
  Clipboard,
  FilePlus2,
  FileText,
  ImagePlus,
  RefreshCw,
  Save,
  Send,
  Type,
} from 'lucide-vue-next'
import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import PlatformIcon from '@/components/PlatformIcon.vue'
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
const saved = ref(true)
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
const previewText = computed(
  () => editing.content_text || '生成或编辑内容后，平台预览会显示在这里。',
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
  saved.value = true
}
watch(current, syncEditor)
watch(
  editing,
  () => {
    saved.value = false
  },
  { deep: true },
)
async function generate() {
  if (!selectedArticleId.value || !options.platforms.length)
    return ElMessage.warning('请选择原文和目标平台')
  generating.value = true
  try {
    const task = await workflowApi.generate({ article_id: selectedArticleId.value, ...options })
    const result = await workflowApi.task(task.taskId)
    variants.value = result.variants || (await workflowApi.variants(selectedArticleId.value))
    activePlatform.value = options.platforms[0]
    ElMessage.success('平台版本已生成')
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
  saved.value = true
  ElMessage.success('已保存')
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
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
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
  <div class="studio-page">
    <PageHeader title="内容工作室" description="基于同一篇原文编辑多个平台版本，审核后再进入排期。">
      <span class="save-state">{{ saved ? '已保存' : '有未保存修改' }}</span
      ><el-button :disabled="!current" @click="save"><Save :size="15" class="mr-1" />保存</el-button
      ><el-button type="primary" :loading="generating" @click="generate"
        ><Send :size="15" class="mr-1" />生成平台版本</el-button
      >
    </PageHeader>
    <div v-if="articles.length" class="composer-shell">
      <aside class="composer-settings">
        <div class="composer-section">
          <label>原文</label
          ><el-select
            v-model="selectedArticleId"
            filterable
            class="w-full"
            placeholder="选择文章"
            @change="loadArticle"
            ><el-option
              v-for="item in articles"
              :key="item.id"
              :label="item.title"
              :value="item.id"
          /></el-select>
          <p v-if="article" class="source-excerpt">{{ article.sourceText }}</p>
        </div>
        <div class="composer-section">
          <label>目标平台</label>
          <div class="platform-checks">
            <label v-for="(name, key) in platformNames" :key="key"
              ><el-checkbox v-model="options.platforms" :value="key" /><PlatformIcon
                :platform="key"
                size="sm"
              /><span>{{ name }}</span></label
            >
          </div>
        </div>
        <div class="composer-section">
          <label>内容语气</label
          ><el-select v-model="options.style" class="w-full"
            ><el-option label="专业自然" value="专业自然" /><el-option
              label="轻松亲切"
              value="轻松亲切" /><el-option label="简洁有力" value="简洁有力"
          /></el-select>
        </div>
        <div class="composer-section">
          <label>目标受众</label>
          <p class="setting-value">{{ article?.targetAudience || '未设置' }}</p>
        </div>
        <div class="composer-section">
          <label>生成选项</label
          ><el-switch v-model="options.include_emoji" active-text="适量 Emoji" /><br /><el-switch
            v-model="options.include_hashtags"
            active-text="平台标签"
          />
        </div>
      </aside>
      <main class="composer-editor">
        <div class="editor-toolbar">
          <button title="正文"><Type :size="16" /></button
          ><button title="插入图片"><ImagePlus :size="16" /></button><span /><small
            >{{ editing.content_text.length }} 字</small
          >
        </div>
        <div v-if="current" class="editor-body">
          <input v-model="editing.title" class="editor-title" placeholder="标题" /><textarea
            v-model="editing.content_text"
            class="editor-content"
            placeholder="在这里编辑平台内容…"
          /><el-select
            v-model="editing.hashtags"
            multiple
            allow-create
            filterable
            class="editor-tags"
            placeholder="添加标签"
          />
          <div class="editor-footer">
            <div>
              <StatusBadge :status="current.reviewStatus" /><span>版本 {{ current.versionNo }}</span
              ><span>适配评分 {{ current.qualityScore }}</span>
            </div>
            <div>
              <button @click="copy"><Clipboard :size="15" /></button
              ><button :disabled="generating" @click="regenerate"><RefreshCw :size="15" /></button
              ><el-button type="success" plain size="small" @click="approve"
                ><Check :size="14" class="mr-1" />审核通过</el-button
              >
            </div>
          </div>
        </div>
        <EmptyState
          v-else
          title="还没有平台版本"
          description="选择目标平台后生成版本，或从已有版本继续编辑。"
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
              <div><b>账号名称</b><span>刚刚</span></div>
            </div>
            <h3 v-if="editing.title">{{ editing.title }}</h3>
            <p>{{ previewText }}</p>
            <div v-if="editing.hashtags.length" class="preview-tags">
              {{ editing.hashtags.join(' ') }}
            </div>
            <div class="preview-placeholder">图片预览区域</div>
            <footer><span>喜欢</span><span>评论</span><span>分享</span></footer>
          </div>
        </div>
      </aside>
    </div>
    <EmptyState
      v-else
      title="先创建一篇原文"
      description="内容工作室不会使用示例数据，请从内容库创建或导入真实文稿。"
      ><template #icon><FilePlus2 /></template
    ></EmptyState>
  </div>
</template>
