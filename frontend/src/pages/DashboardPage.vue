<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import AdminDashboardPage from '@/pages/AdminDashboardPage.vue'
import OperatorDashboardPage from '@/pages/OperatorDashboardPage.vue'

const auth = useAuthStore()
</script>

<template>
  <AdminDashboardPage v-if="auth.isSystemAdminOnly" />
  <OperatorDashboardPage v-else />
</template>
