<template>
  <div>
    <!-- 顶部导航栏 -->
    <nav class="app-navbar">
      <div class="navbar-brand">
        <span class="brand-icon">📚</span>
        <span>知识库智能问答系统</span>
      </div>
      <div class="navbar-right">
        <span style="font-size: 12px; opacity: 0.75;">
          <span class="status-dot" :class="store.healthRAGFlow === 'connected' ? 'connected' : 'disconnected'" />
          RAGFlow {{ store.healthRAGFlow === 'connected' ? '已连接' : store.healthRAGFlow === 'checking' ? '检测中' : '未连接' }}
        </span>
        <template v-if="authStore.isLoggedIn">
          <span style="color: rgba(255,255,255,0.85); font-size: 13px;">
            {{ authStore.currentUser?.username }}
            <a-tag v-if="authStore.isAdmin" color="gold" style="font-size: 10px; margin-left: 4px;">管理员</a-tag>
          </span>
          <a-button type="link" style="color: rgba(255,255,255,0.75); padding: 0;" @click="$router.push('/')">
            首页
          </a-button>
          <a-button type="link" style="color: rgba(255,255,255,0.6); padding: 0;" @click="authStore.logout()">
            退出
          </a-button>
        </template>
        <template v-else>
          <a-button type="link" style="color: rgba(255,255,255,0.75); padding: 0;" @click="$router.push('/login')">
            登录
          </a-button>
        </template>
      </div>
    </nav>

    <!-- 页面内容 -->
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from './stores/appStore'
import { useAuthStore } from './stores/authStore'

const store = useAppStore()
const authStore = useAuthStore()

onMounted(() => {
  store.checkHealth()
})
</script>
