<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { ArrowRight, LockKeyhole } from 'lucide-vue-next'

import BrandMark from '@/components/BrandMark.vue'
import { getApiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const formRef = ref<FormInstance>()
const showPassword = ref(false)
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
    await auth.signIn(form)
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
  <main class="login-shell">
    <section class="login-intro">
      <BrandMark />
      <div class="login-copy">
        <p>内容运营工作流</p>
        <h1>从原文到发布，一处完成。</h1>
        <ol>
          <li><b>01</b><span>整理原文与素材</span></li>
          <li><b>02</b><span>编辑多个平台版本</span></li>
          <li><b>03</b><span>审核、排期与复盘</span></li>
        </ol>
      </div>
      <small>SocialFlow · 内容运营系统</small>
    </section>
    <section class="login-form-wrap">
      <div class="login-card">
        <BrandMark class="mb-10 lg:hidden" />
        <h2>登录</h2>
        <p>使用分配给你的工作台账号。</p>
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
            />
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
              <template #suffix
                ><button
                  type="button"
                  class="text-xs text-muted"
                  @click="showPassword = !showPassword"
                >
                  {{ showPassword ? '隐藏' : '显示' }}
                </button></template
              >
            </el-input>
          </el-form-item>
          <el-button
            type="primary"
            class="mt-2 !h-12 !w-full !font-semibold"
            :loading="auth.loading"
            data-testid="login-button"
            @click="submit"
          >
            进入工作台<ArrowRight v-if="!auth.loading" :size="17" class="ml-2" />
          </el-button>
        </el-form>
        <div class="account-shortcuts">
          <span>演示账号</span>
          <div>
            <button
              v-for="account in accounts"
              :key="account.username"
              type="button"
              :data-testid="`demo-${account.username}`"
              @click="fill(account)"
            >
              <b>{{ account.label }}</b
              ><small>{{ account.username }}</small>
            </button>
          </div>
        </div>
        <p class="login-help">
          账号由系统管理员创建和分配。首次部署请使用初始化管理员账号登录后完成服务配置。
        </p>
      </div>
    </section>
  </main>
</template>
