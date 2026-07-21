<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import {
  ArrowRight,
  CalendarDays,
  Eye,
  EyeOff,
  LockKeyhole,
  PenLine,
  PieChart,
  ShieldCheck,
  Sun,
  UserRound,
} from 'lucide-vue-next'

import BrandMark from '@/components/BrandMark.vue'
import PlatformIcon from '@/components/PlatformIcon.vue'
import { getApiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const formRef = ref<FormInstance>()
const showPassword = ref(false)
const rememberMe = ref(true)
const dimMode = ref(false)
const form = reactive({ username: '', password: '' })
const accounts = [
  { label: '管理员', username: 'admin', password: 'Admin@123456' },
  { label: '运营者', username: 'operator', password: 'Operator@123456' },
  { label: '查看者', username: 'viewer', password: 'Viewer@123456' },
]
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}
const redirectPath = computed(() => {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/'
})
async function submit(): Promise<void> {
  if (!(await formRef.value?.validate().catch(() => false))) return
  try {
    await auth.signIn(form, rememberMe.value)
    await router.replace(redirectPath.value)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '登录失败'))
  }
}
function fill(account: (typeof accounts)[number]) {
  form.username = account.username
  form.password = account.password
}
</script>

<template>
  <main class="login-shell" :class="{ 'login-dim': dimMode }">
    <section class="login-intro">
      <BrandMark show-subtitle />
      <div class="login-copy">
        <h1>内容创作 <i /> 智能排期 <i /> 数据复盘</h1>
        <p>统一管理多平台内容，从创作到发布一站完成。</p>
        <ul class="login-features">
          <li>
            <span class="is-blue"><PenLine :size="21" /></span>
            <div><b>内容创作</b><small>多平台适配，让表达更高效。</small></div>
          </li>
          <li>
            <span class="is-green"><CalendarDays :size="21" /></span>
            <div><b>排期发布</b><small>可视化日历排期，清晰跟踪状态。</small></div>
          </li>
          <li>
            <span class="is-purple"><PieChart :size="21" /></span>
            <div><b>数据复盘</b><small>多维度数据洞察，持续优化内容。</small></div>
          </li>
        </ul>
        <div class="login-product-preview" aria-hidden="true">
          <div class="preview-sidebar"><i /><i /><i /><i /><i /></div>
          <div class="preview-board">
            <header><b>内容表现</b><span>2026 年 7 月</span></header>
            <div class="preview-kpis">
              <span>互动率<strong>4.8%</strong></span
              ><span>增长<strong>12.5%</strong></span>
            </div>
            <div class="preview-chart"><i /><i /><i /><i /><i /><i /><i /></div>
            <div class="preview-platforms">
              <span><PlatformIcon platform="WEIBO" /><b>微博</b></span>
              <span><PlatformIcon platform="XIAOHONGSHU" /><b>小红书</b></span>
              <span><PlatformIcon platform="WECHAT_OFFICIAL" /><b>微信</b></span>
            </div>
          </div>
        </div>
      </div>
      <small>© 2026 ContentPilot. 保留所有权利。</small>
    </section>
    <section class="login-form-wrap">
      <div class="login-utilities">
        <button type="button" aria-label="切换显示模式" @click="dimMode = !dimMode">
          <Sun :size="17" />
        </button>
        <span class="login-language">简体中文</span>
      </div>
      <div class="login-card">
        <BrandMark class="login-form-brand" />
        <h2>欢迎回来 <span>👋</span></h2>
        <p>登录你的工作账号，继续内容运营之旅</p>
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          size="large"
          class="mt-8"
          @keyup.enter="submit"
        >
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="form.username"
              autocomplete="username"
              placeholder="请输入用户名"
              data-testid="username-input"
            >
              <template #prefix><UserRound :size="17" /></template>
            </el-input>
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              placeholder="请输入密码"
              data-testid="password-input"
            >
              <template #prefix><LockKeyhole :size="16" /></template>
              <template #suffix>
                <button
                  type="button"
                  class="password-toggle"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  @click="showPassword = !showPassword"
                >
                  <EyeOff v-if="showPassword" :size="17" />
                  <Eye v-else :size="17" />
                </button>
              </template>
            </el-input>
          </el-form-item>
          <div class="login-options">
            <el-checkbox v-model="rememberMe">记住我</el-checkbox>
          </div>
          <el-button
            type="primary"
            class="login-submit"
            :loading="auth.loading"
            data-testid="login-button"
            @click="submit"
          >
            进入 ContentPilot<ArrowRight v-if="!auth.loading" :size="17" class="ml-2" />
          </el-button>
        </el-form>
        <div class="account-shortcuts">
          <span>或使用演示账号登录</span>
          <div>
            <button
              v-for="account in accounts"
              :key="account.username"
              type="button"
              :data-testid="`demo-${account.username}`"
              @click="fill(account)"
            >
              <span :class="`role-${account.username}`">
                <ShieldCheck v-if="account.username === 'admin'" :size="18" />
                <UserRound v-else-if="account.username === 'operator'" :size="18" />
                <Eye v-else :size="18" />
              </span>
              <div>
                <b>{{ account.label }}</b
                ><small>{{ account.username }}</small>
              </div>
            </button>
          </div>
        </div>
        <p class="login-security">
          <ShieldCheck :size="16" />数据加密传输，接口通过 JWT 与角色权限校验保护
        </p>
      </div>
    </section>
  </main>
</template>
