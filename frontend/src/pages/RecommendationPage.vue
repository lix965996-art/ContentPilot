<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CalendarPlus, Clock3, Gauge, Lightbulb } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import ChartPanel from '@/components/ChartPanel.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import type { Article, Platform, Variant } from '@/types/business'
import { platformNames } from '@/types/business'

const articles = ref<Article[]>([])
const articleId = ref<number>()
const variants = ref<Variant[]>([])
const platform = ref<Platform>('WEIBO')
const result = ref<Record<string, any>>()
const loading = ref(false)
const variant = computed(() => variants.value.find((x) => x.platform === platform.value))
const option = computed(() => ({
  grid: { left: 40, right: 18, top: 22, bottom: 30 },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: (result.value?.curve || []).map((x: any) => x.time),
    axisLabel: { interval: 2 },
  },
  yAxis: { type: 'value', min: 0, max: 100 },
  series: [
    {
      type: 'line',
      smooth: true,
      symbol: 'none',
      areaStyle: { color: 'rgba(0,122,255,.06)' },
      lineStyle: { color: '#007aff', width: 2 },
      data: (result.value?.curve || []).map((x: any) => x.platformPrior),
    },
  ],
}))
async function loadArticles() {
  const data = await workflowApi.articles({ page_size: 100 })
  articles.value = data.items
  articleId.value = data.items[0]?.id
  await loadVariants()
}
async function loadVariants() {
  if (!articleId.value) return
  variants.value = await workflowApi.variants(articleId.value)
  result.value = undefined
}
async function calculate() {
  if (!articleId.value || !variant.value)
    return ElMessage.warning('该文章还没有当前平台版本，请先生成平台版本')
  loading.value = true
  try {
    result.value = await workflowApi.recommend({
      article_id: articleId.value,
      variant_id: variant.value.id,
      platform: platform.value,
    })
    ElMessage.success('推荐时间已计算')
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  } finally {
    loading.value = false
  }
}
onMounted(loadArticles)
</script>
<template>
  <div>
    <PageHeader title="发布时间推荐"
      ><el-button type="primary" :loading="loading" @click="calculate"
        ><Gauge :size="16" class="mr-2" />计算推荐时间</el-button
      ></PageHeader
    >
    <section class="recommendation-toolbar">
      <label class="field-label"
        >内容<el-select v-model="articleId" filterable class="mt-2 w-full" @change="loadVariants"
          ><el-option
            v-for="item in articles"
            :key="item.id"
            :label="item.title"
            :value="item.id" /></el-select></label
      ><label class="field-label"
        >平台<el-segmented
          v-model="platform"
          :options="Object.entries(platformNames).map(([value, label]) => ({ value, label }))"
          class="mt-2 w-full"
      /></label>
    </section>
    <template v-if="result"
      ><section class="recommendation-layout">
        <article class="recommendation-curve">
          <header>
            <h2>24 小时活跃曲线</h2>
            <span>{{
              new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
            }}</span>
          </header>
          <ChartPanel :option="option" height="360px" />
        </article>
        <aside class="recommendation-result">
          <p>最佳时间</p>
          <div class="best-time">
            <span class="icon-tile"><Clock3 :size="21" /></span>
            <div>
              <strong>
                {{
                  new Date(result.recommendedAt).toLocaleString('zh-CN', {
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                }}
              </strong>
              <span>推荐得分 {{ result.score }} · 置信度 {{ result.confidence }}</span>
            </div>
          </div>
          <div class="recommendation-reasons">
            <h3>推荐理由</h3>
            <div v-for="reason in result.reasonJson" :key="reason.type" class="reason-card">
              <Lightbulb :size="16" />
              <div>
                <p>{{ reason.description }}</p>
                <small>贡献 {{ reason.contribution }} 分</small>
              </div>
            </div>
          </div>
          <div class="alternative-times">
            <p>备选时间</p>
            <div>
              <span
                v-for="item in result.alternativeTimesJson"
                :key="item.recommendedAt"
                class="meta-chip"
                >{{
                  new Date(item.recommendedAt).toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                }}
                · {{ item.score }}</span
              >
            </div>
          </div>
        </aside>
      </section></template
    >
    <div v-else class="empty-state recommendation-empty">
      <CalendarPlus :size="24" />
      <p>选择内容，计算发布时间</p>
    </div>
  </div>
</template>
