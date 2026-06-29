import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { KnowledgeBase } from '../types'
import { listKBs } from '../api/kb'

export const useAppStore = defineStore('app', () => {
  const knowledgeBases = ref<KnowledgeBase[]>([])
  const loading = ref(false)
  const healthRAGFlow = ref<string>('checking')

  async function fetchKBs() {
    loading.value = true
    try {
      const res = await listKBs()
      knowledgeBases.value = res.items
    } finally {
      loading.value = false
    }
  }

  async function checkHealth() {
    try {
      const { default: api } = await import('../api/client')
      const { data } = await api.get('/health')
      healthRAGFlow.value = data.ragflow
    } catch {
      healthRAGFlow.value = 'unknown'
    }
  }

  return { knowledgeBases, loading, healthRAGFlow, fetchKBs, checkHealth }
})
