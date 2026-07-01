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
              <a-input v-model:value="regForm.tags" placeholder="权限标签（逗号分隔，如 技术部,公开）" />
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

const router = useRouter()
const authStore = useAuthStore()
const tab = ref('login')
const loading = ref(false)

const loginForm = ref({ username: '', password: '' })
const regForm = ref({ username: '', password: '', tags: '' })

onMounted(() => {
  if (authStore.isLoggedIn) {
    router.push('/')
  }
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
    const res = await apiRegister(regForm.value.username, regForm.value.password, regForm.value.tags)
    authStore.setAuth(res.access_token, res.user)
    message.success('注册成功')
    router.push('/')
  } catch (e: any) {
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
