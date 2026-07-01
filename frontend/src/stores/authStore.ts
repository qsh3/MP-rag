import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { login as apiLogin, getMe } from '../api/auth'
import type { UserInfo } from '../types'

const TOKEN_KEY = 'mp_auth_token'
const USER_KEY = 'mp_auth_user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const currentUser = ref<UserInfo | null>(
    JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  )

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => currentUser.value?.role === 'admin')

  function setAuth(t: string, user: UserInfo) {
    token.value = t
    currentUser.value = user
    localStorage.setItem(TOKEN_KEY, t)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  }

  function clearAuth() {
    token.value = null
    currentUser.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  async function login(username: string, password: string) {
    const res = await apiLogin(username, password)
    setAuth(res.access_token, res.user)
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const user = await getMe()
      currentUser.value = user
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    } catch {
      clearAuth()
    }
  }

  function logout() {
    clearAuth()
    window.location.href = '/login'
  }

  return { token, currentUser, isLoggedIn, isAdmin, login, fetchMe, logout, clearAuth }
})
