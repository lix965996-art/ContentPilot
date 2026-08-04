<script setup lang="ts">
import { computed } from 'vue'
import { Shield } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { ROLE_SCOPES } from '@/config/roles'

const auth = useAuthStore()
const show = computed(() => auth.primaryRoleCode && auth.primaryRoleCode !== 'ADMIN')
const scope = computed(() => {
  const code = auth.primaryRoleCode
  return code ? ROLE_SCOPES[code] : null
})
</script>

<template>
  <div v-if="show && scope" class="role-scope-notice">
    <Shield :size="15" />
    <span
      ><b>{{ scope.label }}</b> · {{ scope.summary }}</span
    >
  </div>
</template>

<style scoped>
.role-scope-notice {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  padding: 10px 14px;
  color: #475467;
  font-size: 12px;
  line-height: 1.6;
}
.role-scope-notice b {
  color: #172033;
  font-weight: 600;
}
.role-scope-notice svg {
  flex: none;
  margin-top: 2px;
  color: #667085;
}
</style>
