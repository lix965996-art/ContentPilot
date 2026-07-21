<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { KeyRound, Save, ShieldCheck } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
const settings = ref<Array<Record<string, any>>>([])
const users = ref<Array<Record<string, any>>>([])
const logs = ref<Array<Record<string, any>>>([])
const tab = ref('config')
const saving = ref('')
async function load() {
  ;[settings.value, users.value, logs.value] = await Promise.all([
    workflowApi.settings(),
    workflowApi.users(),
    workflowApi.auditLogs(),
  ])
}
async function save(item: any) {
  saving.value = item.settingKey
  try {
    await workflowApi.updateSetting(item.settingKey, item.settingValue)
    ElMessage.success('配置已保存')
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  } finally {
    saving.value = ''
  }
}
onMounted(() => load().catch((e) => ElMessage.error(getApiErrorMessage(e))))
</script>
<template>
  <div>
    <PageHeader title="系统设置" description="集中管理模型、媒体、发布模式、用户权限和审计记录。"
      ><span class="security-chip"><ShieldCheck :size="15" />密钥脱敏显示</span></PageHeader
    ><el-tabs v-model="tab" class="settings-tabs"
      ><el-tab-pane label="服务配置" name="config"
        ><div class="settings-list panel">
          <div v-for="item in settings" :key="item.settingKey" class="setting-row">
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
            /><el-button :loading="saving === item.settingKey" @click="save(item)"
              ><Save :size="14" class="mr-1" />保存</el-button
            >
          </div>
        </div></el-tab-pane
      ><el-tab-pane label="用户与角色" name="users"
        ><section class="overflow-hidden rounded-xl border border-line bg-white">
          <el-table :data="users"
            ><el-table-column label="用户" min-width="220"
              ><template #default="{ row }"
                ><div class="flex items-center gap-3">
                  <span class="avatar-small">{{
                    String(row.display_name || row.username).slice(0, 1)
                  }}</span>
                  <div>
                    <p class="font-medium">{{ row.display_name }}</p>
                    <p class="text-xs text-muted">{{ row.username }}</p>
                  </div>
                </div></template
              ></el-table-column
            ><el-table-column label="邮箱" prop="email" min-width="220" /><el-table-column
              label="角色"
              min-width="180"
              ><template #default="{ row }"
                ><span v-for="role in row.roles" :key="role.code" class="meta-chip mr-1">{{
                  role.name
                }}</span></template
              ></el-table-column
            ><el-table-column label="状态" width="120"
              ><template #default="{ row }"
                ><StatusBadge :status="row.status" /></template></el-table-column
          ></el-table></section></el-tab-pane
      ><el-tab-pane label="审计日志" name="audit"
        ><section class="overflow-hidden rounded-xl border border-line bg-white">
          <el-table :data="logs"
            ><el-table-column label="时间" width="180"
              ><template #default="{ row }">{{
                new Date(row.createdAt).toLocaleString('zh-CN')
              }}</template></el-table-column
            ><el-table-column label="模块" prop="module" width="130" /><el-table-column
              label="动作"
              prop="action"
              width="150"
            /><el-table-column label="对象" min-width="160"
              ><template #default="{ row }"
                >{{ row.targetType || '—' }} #{{ row.targetId || '—' }}</template
              ></el-table-column
            ><el-table-column label="请求" min-width="260"
              ><template #default="{ row }"
                ><code>{{ row.requestMethod }} {{ row.requestPath }}</code></template
              ></el-table-column
            ></el-table
          >
        </section></el-tab-pane
      ></el-tabs
    >
  </div>
</template>
