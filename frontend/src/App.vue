<template>
  <div>
    <!-- 顶部导航栏 -->
    <nav class="app-navbar">
      <div class="navbar-brand">
        <span class="brand-icon">📚</span>
        <span>企业知识库智能问答系统</span>
      </div>
      <div class="navbar-right">
        <span style="font-size: 12px; opacity: 0.75;">
          <span class="status-dot" :class="store.healthRAGFlow === 'connected' ? 'connected' : 'disconnected'" />
          RAGFlow {{ store.healthRAGFlow === 'connected' ? '已连接' : store.healthRAGFlow === 'checking' ? '检测中' : '未连接' }}
        </span>
        <a-button type="link" style="color: rgba(255,255,255,0.75); padding: 0;" @click="$router.push('/')">
          首页
        </a-button>
      </div>
    </nav>

    <!-- 页面内容 -->
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from './stores/appStore'

const store = useAppStore()

onMounted(() => {
  store.checkHealth()
})
</script>
