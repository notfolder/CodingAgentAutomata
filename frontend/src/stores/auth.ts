import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiLogin } from '../api/client'

// 認証済みユーザー情報の型定義
interface AuthUser {
  username: string
  role: string
}

// 認証ストア: トークンとユーザー情報を管理する
export const useAuthStore = defineStore('auth', () => {
  // localStorage からトークンを初期化
  const token = ref<string | null>(localStorage.getItem('auth_token'))
  const user = ref<AuthUser | null>(null)

  // localStorage からユーザー情報を復元
  const savedUser = localStorage.getItem('auth_user')
  if (savedUser) {
    try {
      user.value = JSON.parse(savedUser) as AuthUser
    } catch {
      // パース失敗時は無視
    }
  }

  // 認証済みかどうかの判定
  const isAuthenticated = computed(() => token.value !== null && user.value !== null)

  // adminロールかどうかの判定
  const isAdmin = computed(() => user.value?.role === 'admin')

  // 現在のユーザー名
  const currentUsername = computed(() => user.value?.username ?? '')

  /**
   * ログイン処理
   * @param username ユーザー名
   * @param password パスワード
   */
  async function login(username: string, password: string): Promise<void> {
    const data = await apiLogin(username, password)
    token.value = data.access_token

    // JWTペイロードからユーザー情報を取得
    const payload = parseJwt(data.access_token)
    user.value = {
      username: payload.sub as string,
      role: payload.role as string,
    }

    // localStorage に永続化
    localStorage.setItem('auth_token', data.access_token)
    localStorage.setItem('auth_user', JSON.stringify(user.value))
  }

  /**
   * ログアウト処理: トークンとユーザー情報をクリアする
   */
  function logout(): void {
    token.value = null
    user.value = null
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
  }

  return {
    token,
    user,
    isAuthenticated,
    isAdmin,
    currentUsername,
    login,
    logout,
  }
})

/**
 * JWT トークンのペイロードをデコードする
 * @param token JWT文字列
 * @returns ペイロードオブジェクト
 */
function parseJwt(token: string): Record<string, unknown> {
  const base64 = token.split('.')[1]
  const decoded = atob(base64.replace(/-/g, '+').replace(/_/g, '/'))
  return JSON.parse(decoded) as Record<string, unknown>
}
