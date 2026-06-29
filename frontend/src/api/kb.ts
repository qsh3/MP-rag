import api from './client'
import type { KnowledgeBase } from '../types'

export async function createKB(name: string, description: string): Promise<KnowledgeBase> {
  const { data } = await api.post('/kb', { name, description })
  return data
}

export async function listKBs(): Promise<{ total: number; items: KnowledgeBase[] }> {
  const { data } = await api.get('/kb')
  return data
}

export async function getKB(id: string): Promise<KnowledgeBase> {
  const { data } = await api.get(`/kb/${id}`)
  return data
}

export async function deleteKB(id: string): Promise<void> {
  await api.delete(`/kb/${id}`)
}
