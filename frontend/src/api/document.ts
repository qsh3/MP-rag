import api from './client'
import type { Document } from '../types'

export async function uploadDocs(kbId: string, files: File[]): Promise<Document> {
  const formData = new FormData()
  files.forEach(f => formData.append('files', f))
  const { data } = await api.post(`/kb/${kbId}/docs`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function listDocs(kbId: string): Promise<{ total: number; items: Document[] }> {
  const { data } = await api.get(`/kb/${kbId}/docs`)
  return data
}

export async function getDoc(kbId: string, docId: string): Promise<Document> {
  const { data } = await api.get(`/kb/${kbId}/docs/${docId}`)
  return data
}

export async function deleteDoc(kbId: string, docId: string): Promise<void> {
  await api.delete(`/kb/${kbId}/docs/${docId}`)
}
