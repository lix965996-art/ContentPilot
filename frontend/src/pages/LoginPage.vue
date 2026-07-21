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
</script>

<template>
  <main class="login-shell">
    <section class="login-intro">
      <BrandMark />
      <div class="login-copy">
        <p>内容运营，从原文开始</p>
        <h1>把写作、审核、排期和复盘放在一个工作台里。</h1>
        <span>面向校园媒体与内容团队的日常运营系统。</span>
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
        <p class="login-help">
          账号由系统管理员创建和分配。首次部署请使用初始化管理员账号登录后完成服务配置。
        </p>
      </div>
    </section>
  </main>
</template>
