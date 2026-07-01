import api from './client'
import type { TokenResponse, UserInfo } from '../types'

export async function login(username: string, password: string): Promise<TokenResponse> {
  const { data } = await api.post('/auth/login', { username, password })
  return data
}

export async function register(username: string, password: string, tags?: string, tag_pwd?: string): Promise<TokenResponse> {
  const { data } = await api.post('/auth/register', { username, password, tags: tags || '', tag_pwd: tag_pwd || '' })
  return data
}

export async function getMe(): Promise<UserInfo> {
  const { data } = await api.get('/auth/me')
  return data
}
