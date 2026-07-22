<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Activity,
  CheckCircle2,
  CircleDollarSign,
  KeyRound,
  RefreshCw,
  Save,
  Server,
  ShieldCheck,
  Unplug,
} from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import type { LlmConfig, LlmUsage } from '@/types/business'

const EMPTY_USAGE: LlmUsage = {
  days: 30,
  generations: 0,
  promptTokens: 0,
  completionTokens: 0,
  totalTokens: 0,
  estimatedCost: 0,
  averageTokens: 0,
  currency: 'CNY',
  byModel: [],
  daily: [],
}

const providerOptions = [
  { value: 'openai', label: 'OpenAI', url: 'https://api.openai.com/v1' },
  { value: 'siliconflow', label: '硅基流动', url: 'https://api.siliconflow.cn/v1' },
  { value: 'deepseek', label: 'DeepSeek', url: 'https://api.deepseek.com/v1' },
  { value: 'moonshot', label: 'Moonshot', url: 'https://api.moonshot.cn/v1' },
  { value: 'openai-compatible', label: '自定义 OpenAI 兼容服务', url: '' },
]
const llm = reactive<LlmConfig>({
  provider: 'openai-compatible',
  baseUrl: '',
  apiKey: '',
  apiKeyConfigured: false,
  model: '',
  inputPricePerMillion: 0,
  outputPricePerMillion: 0,
  currency: 'CNY',
})
const settings = ref<Array<Record<string, any>>>([])
const users = ref<Array<Record<string, any>>>([])
const logs = ref<Array<Record<string, any>>>([])
const models = ref<string[]>([])
const usage = ref<LlmUsage>({ ...EMPTY_USAGE })
const usageDays = ref(30)
const tab = ref('model')
const saving = ref('')
const testing = ref(false)
const loadingUsage = ref(false)
const connection = ref<{ ok: boolean; text: string; latency?: number } | null>(null)

const generalSettings = computed(() =>
  settings.value.filter((item) => !String(item.settingKey).startsWith('llm.')),
)
const currencySymbol = computed(() => (usage.value.currency === 'USD' ? '$' : '¥'))
const maxDailyTokens = computed(() => Math.max(1, ...usage.value.daily.map((item) => item.tokens)))
const apiKeyState = computed(() => {
  if (llm.apiKeyConfigured) return '已配置'
  if (llm.apiKey.trim()) return '待保存'
  return '未配置'
})

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value || 0)
}

function changeProvider(value: string) {
  const preset = providerOptions.find((item) => item.value === value)
  if (preset?.url) llm.baseUrl = preset.url
  connection.value = null
}

async function loadUsage() {
  loadingUsage.value = true
  try {
    usage.value = await workflowApi.llmUsage(usageDays.value)
  } finally {
    loadingUsage.value = false
  }
}

async function load() {
  const [config, rawSettings, userRows, logRows] = await Promise.all([
    workflowApi.llmConfig(),
    workflowApi.settings(),
    workflowApi.users(),
    workflowApi.auditLogs(),
  ])
  Object.assign(llm, config)
  if (config.model) models.value = [config.model]
  settings.value = rawSettings
  users.value = userRows
  logs.value = logRows
  await loadUsage()
}

async function saveModel() {
  saving.value = 'model-service'
  try {
    Object.assign(llm, await workflowApi.saveLlmConfig({ ...llm }))
    ElMessage.success('模型服务配置已保存')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    saving.value = ''
  }
}

async function testConnection() {
  testing.value = true
  connection.value = null
  try {
    const result = await workflowApi.testLlmConnection({ ...llm })
    models.value = result.models
    if (!llm.model && result.models.length) llm.model = result.models[0] || ''
    connection.value = { ok: true, text: result.message, latency: result.latencyMs }
    ElMessage.success(result.message)
  } catch (error) {
    const message = getApiErrorMessage(error)
    connection.value = { ok: false, text: message }
    ElMessage.error(message)
  } finally {
    testing.value = false
  }
}

async function save(item: any) {
  saving.value = item.settingKey
  try {
    await workflowApi.updateSetting(item.settingKey, item.settingValue)
    ElMessage.success('配置已保存')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    saving.value = ''
  }
}

onMounted(() => load().catch((error) => ElMessage.error(getApiErrorMessage(error))))
</script>

<template>
  <div>
    <PageHeader title="设置" />
    <el-tabs v-model="tab" class="settings-tabs">
      <el-tab-pane label="模型服务" name="model">
        <div class="model-service-layout">
          <section class="model-config-panel">
            <header class="model-section-heading">
              <div>
                <h2>模型服务</h2>
                <p>选择常用服务商预设，或自定义任意 OpenAI 兼容接口。</p>
              </div>
              <span class="secret-note"><ShieldCheck :size="14" />密钥加密保存</span>
            </header>

            <el-form label-position="top" class="model-form">
              <div class="model-form-grid">
                <el-form-item label="服务商">
                  <el-select
                    v-model="llm.provider"
                    class="w-full"
                    data-testid="model-provider"
                    @change="changeProvider"
                  >
                    <el-option
                      v-for="item in providerOptions"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="API Base URL">
                  <el-input
                    v-model="llm.baseUrl"
                    data-testid="model-base-url"
                    placeholder="https://api.example.com/v1"
                  />
                </el-form-item>
              </div>
              <el-form-item label="API Key">
                <el-input
                  v-model="llm.apiKey"
                  type="password"
                  show-password
                  autocomplete="new-password"
                  data-testid="model-api-key"
                  placeholder="输入服务商提供的密钥"
                >
                  <template #prefix><KeyRound :size="16" /></template>
                </el-input>
              </el-form-item>
              <el-form-item label="可用模型">
                <el-select
                  v-model="llm.model"
                  class="w-full"
                  data-testid="model-name"
                  filterable
                  allow-create
                  default-first-option
                  placeholder="测试连接后选择，或手动输入模型名称"
                >
                  <el-option v-for="model in models" :key="model" :label="model" :value="model" />
                </el-select>
              </el-form-item>

              <div class="pricing-heading">
                <div>
                  <h3>Token 价格</h3>
                  <p>按服务商价格填写，系统会记录每次生成的预估费用。</p>
                </div>
              </div>
              <div class="pricing-grid">
                <el-form-item label="输入 / 百万 Token">
                  <el-input-number
                    v-model="llm.inputPricePerMillion"
                    :min="0"
                    :precision="4"
                    :controls="false"
                    class="!w-full"
                  />
                </el-form-item>
                <el-form-item label="输出 / 百万 Token">
                  <el-input-number
                    v-model="llm.outputPricePerMillion"
                    :min="0"
                    :precision="4"
                    :controls="false"
                    class="!w-full"
                  />
                </el-form-item>
                <el-form-item label="币种">
                  <el-select v-model="llm.currency" class="w-full">
                    <el-option label="人民币 CNY" value="CNY" />
                    <el-option label="美元 USD" value="USD" />
                  </el-select>
                </el-form-item>
              </div>

              <div class="model-actions">
                <el-button
                  data-testid="test-model-connection"
                  :loading="testing"
                  @click="testConnection"
                >
                  <Activity :size="15" />测试连接
                </el-button>
                <el-button
                  type="primary"
                  data-testid="save-model-config"
                  :loading="saving === 'model-service'"
                  @click="saveModel"
                >
                  <Save :size="15" />保存配置
                </el-button>
              </div>
            </el-form>
          </section>

          <aside class="connection-panel">
            <Server :size="22" />
            <h3>连接状态</h3>
            <template v-if="connection">
              <div :class="['connection-result', connection.ok ? 'is-success' : 'is-error']">
                <CheckCircle2 v-if="connection.ok" :size="17" />
                <Unplug v-else :size="17" />
                <span>{{ connection.text }}</span>
              </div>
              <p v-if="connection.ok && connection.latency !== undefined">
                响应时间 {{ connection.latency }} ms
              </p>
            </template>
            <p v-else>填写连接信息后测试，模型列表会自动同步。</p>
            <dl>
              <div>
                <dt>服务商</dt>
                <dd>{{ providerOptions.find((x) => x.value === llm.provider)?.label }}</dd>
              </div>
              <div>
                <dt>模型</dt>
                <dd>{{ llm.model || '未选择' }}</dd>
              </div>
              <div>
                <dt>密钥</dt>
                <dd>{{ apiKeyState }}</dd>
              </div>
            </dl>
          </aside>
        </div>
      </el-tab-pane>

      <el-tab-pane label="用量与费用" name="usage">
        <section v-loading="loadingUsage" class="usage-panel">
          <header class="usage-toolbar">
            <div>
              <h2>模型用量</h2>
              <p>根据模型接口返回的 Token 数量计算。</p>
            </div>
            <div>
              <el-select v-model="usageDays" class="!w-28" @change="loadUsage">
                <el-option label="近 7 天" :value="7" />
                <el-option label="近 30 天" :value="30" />
                <el-option label="近 90 天" :value="90" />
              </el-select>
              <el-button circle aria-label="刷新用量" @click="loadUsage"
                ><RefreshCw :size="15"
              /></el-button>
            </div>
          </header>
          <div class="usage-metrics">
            <div>
              <span>生成次数</span><strong>{{ formatNumber(usage.generations) }}</strong>
            </div>
            <div>
              <span>输入 Token</span><strong>{{ formatNumber(usage.promptTokens) }}</strong>
            </div>
            <div>
              <span>输出 Token</span><strong>{{ formatNumber(usage.completionTokens) }}</strong>
            </div>
            <div class="is-cost">
              <span>预估费用</span
              ><strong>{{ currencySymbol }}{{ usage.estimatedCost.toFixed(4) }}</strong>
            </div>
          </div>
          <div class="usage-content-grid">
            <div class="usage-trend">
              <h3>每日用量</h3>
              <div v-if="usage.daily.length" class="token-bars">
                <div v-for="item in usage.daily" :key="item.date">
                  <span
                    :style="{ height: `${Math.max(8, (item.tokens / maxDailyTokens) * 100)}%` }"
                  />
                  <small>{{ item.date.slice(5) }}</small>
                </div>
              </div>
              <div v-else class="compact-empty">还没有生成用量</div>
            </div>
            <div class="model-usage-list">
              <h3>按模型</h3>
              <div v-if="usage.byModel.length">
                <article v-for="item in usage.byModel" :key="item.model">
                  <div>
                    <b>{{ item.model }}</b
                    ><small>{{ item.generations }} 次生成</small>
                  </div>
                  <div>
                    <strong>{{ formatNumber(item.tokens) }}</strong
                    ><small>Token</small>
                  </div>
                  <span>{{ currencySymbol }}{{ item.cost.toFixed(4) }}</span>
                </article>
              </div>
              <div v-else class="compact-empty">暂无模型用量</div>
            </div>
          </div>
          <p class="usage-disclaimer">
            <CircleDollarSign :size="14" />费用按当前填写的单价估算，最终账单以模型服务商为准。
          </p>
        </section>
      </el-tab-pane>

      <el-tab-pane label="通用设置" name="general">
        <div class="settings-list panel">
          <div v-for="item in generalSettings" :key="item.settingKey" class="setting-row">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <KeyRound v-if="item.isSecret" :size="15" class="text-amber-600" />
                <p class="font-medium text-ink">{{ item.description }}</p>
              </div>
              <code>{{ item.settingKey }}</code>
            </div>
            <el-input
              v-model="item.settingValue"
              :type="item.isSecret ? 'password' : 'text'"
              :show-password="item.isSecret"
              class="!w-80"
            />
            <el-button :loading="saving === item.settingKey" @click="save(item)">
              <Save :size="14" />保存
            </el-button>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="用户与角色" name="users">
        <section class="overflow-hidden rounded-xl border border-line bg-white">
          <el-table :data="users">
            <el-table-column label="用户" min-width="220">
              <template #default="{ row }">
                <div class="flex items-center gap-3">
                  <UserAvatar
                    :src="row.avatar_url"
                    :alt="`${row.display_name || row.username}的头像`"
                    :size="34"
                  />
                  <div>
                    <p class="font-medium">{{ row.display_name }}</p>
                    <p class="text-xs text-muted">{{ row.username }}</p>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="邮箱" prop="email" min-width="220" />
            <el-table-column label="角色" min-width="180">
              <template #default="{ row }"
                ><span v-for="role in row.roles" :key="role.code" class="meta-chip mr-1">{{
                  role.name
                }}</span></template
              >
            </el-table-column>
            <el-table-column label="状态" width="120"
              ><template #default="{ row }"><StatusBadge :status="row.status" /></template
            ></el-table-column>
          </el-table>
        </section>
      </el-tab-pane>

      <el-tab-pane label="审计日志" name="audit">
        <section class="overflow-hidden rounded-xl border border-line bg-white">
          <el-table :data="logs">
            <el-table-column label="时间" width="180"
              ><template #default="{ row }">{{
                new Date(row.createdAt).toLocaleString('zh-CN')
              }}</template></el-table-column
            >
            <el-table-column label="模块" prop="module" width="130" />
            <el-table-column label="动作" prop="action" width="150" />
            <el-table-column label="对象" min-width="160"
              ><template #default="{ row }"
                >{{ row.targetType || '—' }} #{{ row.targetId || '—' }}</template
              ></el-table-column
            >
            <el-table-column label="请求" min-width="260"
              ><template #default="{ row }"
                ><code>{{ row.requestMethod }} {{ row.requestPath }}</code></template
              ></el-table-column
            >
          </el-table>
        </section>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
