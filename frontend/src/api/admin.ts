import api from './client'
import type { UserInfo } from '../types'

export async function listUsers(): Promise<UserInfo[]> {
  const { data } = await api.get('/admin/users')
  return data
}

export async function updateUser(id: string, body: { tags?: string; role?: string; is_active?: number }): Promise<UserInfo> {
  const { data } = await api.put(`/admin/users/${id}`, body)
  return data
}

export async function deleteUser(id: string): Promise<void> {
  await api.delete(`/admin/users/${id}`)
}
