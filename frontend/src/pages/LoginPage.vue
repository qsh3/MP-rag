<template>
  <div class="login-container">
    <a-card class="login-card" :bordered="false">
      <h2 style="text-align: center; margin-bottom: 24px;">知识库智能问答系统</h2>
      <a-tabs v-model:activeKey="tab" centered>
        <a-tab-pane key="login" tab="登录">
          <a-form :model="loginForm" @finish="handleLogin" layout="vertical" size="large">
            <a-form-item name="username" :rules="[{ required: true, message: '请输入用户名' }]">
              <a-input v-model:value="loginForm.username" placeholder="用户名" />
            </a-form-item>
            <a-form-item name="password" :rules="[{ required: true, message: '请输入密码' }]">
              <a-input-password v-model:value="loginForm.password" placeholder="密码" />
            </a-form-item>
            <a-form-item>
              <a-button type="primary" html-type="submit" block :loading="loading">登录</a-button>
            </a-form-item>
          </a-form>
        </a-tab-pane>
        <a-tab-pane key="register" tab="注册">
          <a-form :model="regForm" @finish="handleRegister" layout="vertical" size="large">
            <a-form-item name="username" :rules="[{ required: true, message: '请输入用户名' }]">
              <a-input v-model:value="regForm.username" placeholder="用户名" />
            </a-form-item>
            <a-form-item name="password" :rules="[{ required: true, min: 4, message: '密码至少4位' }]">
              <a-input-password v-model:value="regForm.password" placeholder="密码" />
            </a-form-item>
            <a-form-item name="tags">
              <a-select
                v-model:value="regForm.tagsList"
                mode="multiple"
                placeholder="选择权限标签（可选）"
                style="width: 100%;"
                :options="tagOptions"
              />
            </a-form-item>
            <a-form-item>
              <a-button type="primary" html-type="submit" block :loading="loading">注册</a-button>
            </a-form-item>
          </a-form>
        </a-tab-pane>
      </a-tabs>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '../stores/authStore'
import { register as apiRegister } from '../api/auth'
import { listTags } from '../api/tags'

const router = useRouter()
const authStore = useAuthStore()
const tab = ref('login')
const loading = ref(false)

const loginForm = ref({ username: '', password: '' })
const regForm = ref({ username: '', password: '', tagsList: [] as string[] })
const tagOptions = ref<{ label: string; value: string }[]>([])

onMounted(async () => {
  if (authStore.isLoggedIn) {
    router.push('/')
  }
  try {
    const tags = await listTags()
    tagOptions.value = tags.map(t => ({ label: t.name, value: t.name }))
  } catch { /* 标签加载失败不影响登录 */ }
})

async function handleLogin() {
  loading.value = true
  try {
    await authStore.login(loginForm.value.username, loginForm.value.password)
    message.success('登录成功')
    router.push('/')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  loading.value = true
  try {
    const tags = regForm.value.tagsList.join(',') || ''
    const res = await apiRegister(regForm.value.username, regForm.value.password, tags)
    console.log('[注册] API 返回:', res)
    authStore.setAuth(res.access_token, res.user)
    console.log('[注册] setAuth 完成，token 已设置')
    message.success('注册成功')
    await router.push('/')
    console.log('[注册] 跳转完成')
  } catch (e: any) {
    console.error('[注册] 异常:', e)
    if (e.response) {
      console.error('[注册] HTTP 错误:', e.response.status, e.response.data)
    }
    message.error(e.response?.data?.detail || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 64px);
  background: #f0f2f5;
}
.login-card {
  width: 400px;
  box-shadow: 0 2px 8px rgba(0,0,0,.1);
}
</style>
