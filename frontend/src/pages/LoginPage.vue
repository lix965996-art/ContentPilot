<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import {
  ArrowRight,
  CalendarDays,
  Check,
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
const showConfirmPassword = ref(false)
const rememberMe = ref(true)
const dimMode = ref(false)
const form = reactive({
  display_name: '',
  username: '',
  email: '',
  password: '',
  confirm_password: '',
})
const accounts = [
  { label: '管理员', username: 'admin', password: 'Admin@123456' },
  { label: '运营者', username: 'operator', password: 'Operator@123456' },
  { label: '查看者', username: 'viewer', password: 'Viewer@123456' },
]
const isRegister = computed(() => route.name === 'register')
const passwordChecks = computed(() => [
  { label: '至少 8 位', passed: form.password.length >= 8 },
  { label: '包含字母', passed: /[A-Za-z]/.test(form.password) },
  { label: '包含数字', passed: /\d/.test(form.password) },
  { label: '包含特殊字符（建议）', passed: /[^A-Za-z0-9]/.test(form.password) },
])
const passwordStrength = computed(() => passwordChecks.value.filter((item) => item.passed).length)
const passwordStrengthLabel = computed(() => {
  if (!form.password) return '等待输入'
  if (passwordStrength.value <= 1) return '较弱'
  if (passwordStrength.value === 2) return '一般'
  if (passwordStrength.value === 3) return '符合要求'
  return '强'
})
const rules: FormRules = {
  display_name: [
    { required: true, message: '请输入显示名称', trigger: 'blur' },
    { min: 1, max: 100, message: '显示名称最多 100 个字符', trigger: 'blur' },
  ],
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_.-]{3,50}$/,
      message: '用户名需为 3–50 位字母、数字、点、横线或下划线',
      trigger: 'blur',
    },
  ],
  email: [
    { required: true, message: '请输入邮箱地址', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱地址', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, max: 128, message: '密码长度需为 8–128 位', trigger: 'blur' },
    {
      validator: (_rule: unknown, value: string, callback: (error?: Error) => void) => {
        if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
          callback(new Error('密码必须同时包含字母和数字'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
  confirm_password: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule: unknown, value: string, callback: (error?: Error) => void) => {
        if (value !== form.password) {
          callback(new Error('两次输入的密码不一致'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
}
const redirectPath = computed(() => {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/'
})
async function submit(): Promise<void> {
  if (!(await formRef.value?.validate().catch(() => false))) return
  try {
    if (isRegister.value) {
      await auth.signUp(
        {
          display_name: form.display_name.trim(),
          username: form.username.trim(),
          email: form.email.trim(),
          password: form.password,
        },
        rememberMe.value,
      )
      ElMessage.success('注册成功，已为你创建运营者账号')
    } else {
      await auth.signIn(
        { username: form.username.trim(), password: form.password },
        rememberMe.value,
      )
    }
    await router.replace(redirectPath.value)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, isRegister.value ? '注册失败' : '登录失败'))
  }
}
function fill(account: (typeof accounts)[number]) {
  form.username = account.username
  form.password = account.password
}
watch(isRegister, async () => {
  form.display_name = ''
  form.username = ''
  form.email = ''
  form.password = ''
  form.confirm_password = ''
  showPassword.value = false
  showConfirmPassword.value = false
  await nextTick()
  formRef.value?.clearValidate()
})
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
              <span><PlatformIcon platform="X" /><b>X</b></span>
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
      <div class="login-card" :class="{ 'is-register': isRegister }">
        <BrandMark class="login-form-brand" />
        <h2>
          {{ isRegister ? '创建账号' : '欢迎回来' }} <span>{{ isRegister ? '✨' : '👋' }}</span>
        </h2>
        <p>
          {{
            isRegister
              ? '注册后即可使用内容创作、排期与发布功能'
              : '登录你的工作账号，继续内容运营之旅'
          }}
        </p>
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          size="large"
          class="mt-8"
          @keyup.enter="submit"
        >
          <el-form-item v-if="isRegister" label="显示名称" prop="display_name">
            <el-input
              v-model="form.display_name"
              autocomplete="name"
              placeholder="别人将如何称呼你"
              data-testid="display-name-input"
            >
              <template #prefix><UserRound :size="17" /></template>
            </el-input>
          </el-form-item>
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="form.username"
              autocomplete="username"
              placeholder="请输入用户名"
              data-testid="username-input"
              @blur="form.username = form.username.trim().toLowerCase()"
            >
              <template #prefix><UserRound :size="17" /></template>
            </el-input>
          </el-form-item>
          <el-form-item v-if="isRegister" label="邮箱" prop="email">
            <el-input
              v-model="form.email"
              autocomplete="email"
              placeholder="用于识别账号和后续安全验证"
              data-testid="email-input"
            />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              :autocomplete="isRegister ? 'new-password' : 'current-password'"
              :placeholder="isRegister ? '至少 8 位，同时包含字母和数字' : '请输入密码'"
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
          <div
            v-if="isRegister"
            class="password-strength"
            :data-strength="passwordStrength"
            data-testid="password-strength"
          >
            <div class="password-strength-heading">
              <span>密码强度</span>
              <b>{{ passwordStrengthLabel }}</b>
            </div>
            <div class="password-strength-bars" aria-hidden="true">
              <i v-for="index in 4" :key="index" :class="{ active: passwordStrength >= index }" />
            </div>
            <ul>
              <li v-for="item in passwordChecks" :key="item.label" :class="{ passed: item.passed }">
                <Check :size="12" />
                {{ item.label }}
              </li>
            </ul>
          </div>
          <el-form-item v-if="isRegister" label="确认密码" prop="confirm_password">
            <el-input
              v-model="form.confirm_password"
              :type="showConfirmPassword ? 'text' : 'password'"
              autocomplete="new-password"
              placeholder="请再次输入密码"
              data-testid="confirm-password-input"
            >
              <template #prefix><LockKeyhole :size="16" /></template>
              <template #suffix>
                <button
                  type="button"
                  class="password-toggle"
                  :aria-label="showConfirmPassword ? '隐藏确认密码' : '显示确认密码'"
                  @click="showConfirmPassword = !showConfirmPassword"
                >
                  <EyeOff v-if="showConfirmPassword" :size="17" />
                  <Eye v-else :size="17" />
                </button>
              </template>
            </el-input>
          </el-form-item>
          <div v-if="isRegister" class="register-role-notice">
            <ShieldCheck :size="17" />
            <span>
              <b>新账号默认是运营者</b>
              可进行创作、排期和发布；系统设置与用户管理仍由管理员负责。
            </span>
          </div>
          <div class="login-options">
            <el-checkbox v-model="rememberMe">{{
              isRegister ? '注册后保持登录' : '记住我'
            }}</el-checkbox>
          </div>
          <el-button
            type="primary"
            class="login-submit"
            :loading="auth.loading"
            :data-testid="isRegister ? 'register-button' : 'login-button'"
            @click="submit"
          >
            {{ isRegister ? '注册并进入 ContentPilot' : '进入 ContentPilot' }}
            <ArrowRight v-if="!auth.loading" :size="17" class="ml-2" />
          </el-button>
        </el-form>
        <p class="auth-mode-switch">
          {{ isRegister ? '已经有账号？' : '还没有账号？' }}
          <router-link
            :to="{
              name: isRegister ? 'login' : 'register',
              query: route.query,
            }"
            data-testid="auth-mode-switch"
          >
            {{ isRegister ? '返回登录' : '立即注册' }}
          </router-link>
        </p>
        <details v-if="!isRegister" class="account-shortcuts">
          <summary>使用演示账号</summary>
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
        </details>
        <p class="login-security">
          <ShieldCheck :size="16" />数据加密传输，接口通过 JWT 与角色权限校验保护
        </p>
      </div>
    </section>
  </main>
</template>
