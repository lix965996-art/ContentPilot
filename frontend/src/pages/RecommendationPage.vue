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
      areaStyle: { color: 'rgba(49,92,77,.12)' },
      lineStyle: { color: '#315c4d', width: 2 },
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
    <PageHeader
      title="发布时间推荐"
      description="根据人工维护的规则和账号历史数据，计算 30 分钟候选时段。"
      ><el-button type="primary" :loading="loading" @click="calculate"
        ><Gauge :size="16" class="mr-2" />计算推荐时间</el-button
      ></PageHeader
    >
    <section class="panel rounded-xl p-5">
      <div class="grid gap-4 md:grid-cols-2">
        <label class="field-label"
          >文章<el-select v-model="articleId" filterable class="mt-2 w-full" @change="loadVariants"
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
      </div>
    </section>
    <template v-if="result"
      ><section class="mt-4 grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <article class="panel rounded-xl p-5">
          <div class="flex items-center justify-between">
            <div>
              <p class="section-label">24 小时活跃曲线</p>
              <h2 class="section-title mt-1">{{ platformNames[platform] }} 平台先验得分</h2>
            </div>
            <span class="meta-chip">实际数据计算</span>
          </div>
          <ChartPanel class="mt-3" :option="option" height="310px" />
        </article>
        <aside class="panel rounded-xl p-5">
          <p class="section-label">最佳时段</p>
          <div class="mt-5 flex items-center gap-3">
            <span class="icon-tile"><Clock3 :size="21" /></span>
            <div>
              <p class="text-2xl font-semibold text-ink">
                {{
                  new Date(result.recommendedAt).toLocaleString('zh-CN', {
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                }}
              </p>
              <p class="mt-1 text-sm text-muted">
                综合得分 {{ result.score }} · 置信度 {{ result.confidence }}
              </p>
            </div>
          </div>
          <div class="mt-6 space-y-3">
            <div v-for="reason in result.reasonJson" :key="reason.type" class="reason-card">
              <Lightbulb :size="16" />
              <div>
                <p>{{ reason.description }}</p>
                <small>贡献 {{ reason.contribution }} 分</small>
              </div>
            </div>
          </div>
          <div class="mt-6 border-t border-line pt-4">
            <p class="text-xs font-medium text-muted">备选时段</p>
            <div class="mt-2 flex flex-wrap gap-2">
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
    <div v-else class="empty-state panel mt-4 min-h-96 rounded-xl">
      <CalendarPlus :size="30" />
      <p>选择内容并计算最佳时段</p>
      <span>需要先录入平台历史数据或由管理员维护时段规则。</span>
    </div>
  </div>
</template>
