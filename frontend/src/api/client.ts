import axios from 'axios'
import { useAuthStore } from '../stores/auth'
import router from '../router'

// axios インスタンスを作成（baseURL は /api）
const apiClient = axios.create({
  baseURL: '/api',
})

// リクエストインターセプター: Authorization ヘッダーを自動付与
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// レスポンスインターセプター: 401 エラー時に自動ログアウト
apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      // 認証エラー: ストアをリセットしてログイン画面へ遷移
      const auth = useAuthStore()
      auth.logout()
      void router.push('/login')
    }
    return Promise.reject(error)
  },
)

// ============================================================
// 型定義
// ============================================================

export interface LoginResponse {
  access_token: string
  token_type: string
}

export interface UserResponse {
  username: string
  email: string
  default_cli: string
  default_model: string
  role: string
  is_active: boolean
  system_mcp_enabled: boolean
  user_mcp_config: unknown
  f4_prompt_template: string | null
  virtual_key_masked: string | null
  created_at: string
  updated_at: string
}

export interface UserListResponse {
  items: UserResponse[]
  total: number
  page: number
  per_page: number
}

export interface UserCreateData {
  username: string
  email: string
  password: string
  virtual_key: string
  default_cli: string
  default_model: string
  role: string
}

export interface UserUpdateData {
  email?: string
  virtual_key?: string
  default_cli?: string
  default_model?: string
  role?: string
  is_active?: boolean
  system_mcp_enabled?: boolean
  user_mcp_config?: unknown
  f4_prompt_template?: string | null
}

export interface UserUpdateSelfData {
  email?: string
  password?: string
  current_password?: string
  default_cli?: string
  default_model?: string
  system_mcp_enabled?: boolean
  user_mcp_config?: unknown
  f4_prompt_template?: string | null
}

export interface TaskResponse {
  task_uuid: string
  task_type: string
  gitlab_project_id: number
  source_iid: number
  username: string
  status: string
  cli_type: string | null
  model: string | null
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface TaskListResponse {
  items: TaskResponse[]
  total: number
  page: number
  per_page: number
}

export interface CLIAdapterResponse {
  cli_id: string
  container_image: string
  start_command_template: string
  env_mappings: Record<string, unknown>
  config_content_env: string | null
  is_builtin: boolean
  created_at: string
  updated_at: string
}

export interface CLIAdapterCreateData {
  cli_id: string
  container_image: string
  start_command_template: string
  env_mappings: Record<string, unknown>
  config_content_env?: string
  is_builtin?: boolean
}

export interface CLIAdapterUpdateData {
  container_image?: string
  start_command_template?: string
  env_mappings?: Record<string, unknown>
  config_content_env?: string
}

export interface SystemSettingsResponse {
  f3_prompt_template: string | null
  f4_prompt_template: string | null
  system_mcp_config: unknown
}

export interface SystemSettingsUpdateData {
  f3_prompt_template?: string | null
  f4_prompt_template?: string | null
  system_mcp_config?: unknown
}

// ============================================================
// API 関数
// ============================================================

// --- 認証 ---

/**
 * ログイン API
 * @param username ユーザー名
 * @param password パスワード
 */
export async function apiLogin(username: string, password: string): Promise<LoginResponse> {
  const response = await apiClient.post<LoginResponse>('/auth/login', { username, password })
  return response.data
}

// --- ユーザー管理 ---

/**
 * ユーザー一覧を取得する
 * @param search 前方一致検索文字列（省略可）
 * @param page ページ番号（省略可）
 */
export async function getUsers(search?: string, page?: number): Promise<UserListResponse> {
  const params: Record<string, unknown> = {}
  if (search) params.search = search
  if (page) params.page = page
  const response = await apiClient.get<UserListResponse>('/users', { params })
  return response.data
}

/**
 * ユーザーを新規作成する
 * @param data 作成データ
 */
export async function createUser(data: UserCreateData): Promise<UserResponse> {
  const response = await apiClient.post<UserResponse>('/users', data)
  return response.data
}

/**
 * 特定ユーザーの情報を取得する
 * @param username ユーザー名
 */
export async function getUser(username: string): Promise<UserResponse> {
  const response = await apiClient.get<UserResponse>(`/users/${username}`)
  return response.data
}

/**
 * admin がユーザー情報を更新する（全項目）
 * @param username ユーザー名
 * @param data 更新データ
 */
export async function updateUser(username: string, data: UserUpdateData): Promise<UserResponse> {
  const response = await apiClient.put<UserResponse>(`/users/${username}`, data)
  return response.data
}

/**
 * 一般ユーザーが自分の情報を更新する（制限項目のみ）
 * @param username ユーザー名
 * @param data 更新データ
 */
export async function updateUserSelf(
  username: string,
  data: UserUpdateSelfData,
): Promise<UserResponse> {
  const response = await apiClient.put<UserResponse>(`/users/${username}/me`, data)
  return response.data
}

/**
 * ユーザーを削除する
 * @param username ユーザー名
 */
export async function deleteUser(username: string): Promise<void> {
  await apiClient.delete(`/users/${username}`)
}

/**
 * 対象ユーザーの Virtual Key から利用可能なモデル候補一覧を取得する
 * @param username ユーザー名
 * @returns モデル候補の文字列配列。取得失敗時は空配列
 */
export async function getModelCandidates(username: string): Promise<string[]> {
  try {
    const response = await apiClient.get<string[]>(`/users/${username}/model-candidates`)
    return response.data
  } catch {
    // 取得失敗時は空配列を返す（サジェスト非表示で継続）
    return []
  }
}

// --- タスク管理 ---

/**
 * タスク一覧を取得する
 * @param params フィルタパラメータ
 */
export async function getTasks(params?: {
  username?: string
  status?: string
  task_type?: string
  page?: number
}): Promise<TaskListResponse> {
  const response = await apiClient.get<TaskListResponse>('/tasks', { params })
  return response.data
}

// --- CLI アダプタ管理 ---

/**
 * CLI アダプタ一覧を取得する
 */
export async function getAdapters(): Promise<CLIAdapterResponse[]> {
  const response = await apiClient.get<CLIAdapterResponse[]>('/cli-adapters')
  return response.data
}

/**
 * CLI アダプタを新規作成する
 * @param data 作成データ
 */
export async function createAdapter(data: CLIAdapterCreateData): Promise<CLIAdapterResponse> {
  const response = await apiClient.post<CLIAdapterResponse>('/cli-adapters', data)
  return response.data
}

/**
 * CLI アダプタを更新する
 * @param id アダプタID
 * @param data 更新データ
 */
export async function updateAdapter(
  id: string,
  data: CLIAdapterUpdateData,
): Promise<CLIAdapterResponse> {
  const response = await apiClient.put<CLIAdapterResponse>(`/cli-adapters/${id}`, data)
  return response.data
}

/**
 * CLI アダプタを削除する
 * @param id アダプタID
 */
export async function deleteAdapter(id: string): Promise<void> {
  await apiClient.delete(`/cli-adapters/${id}`)
}

// --- システム設定 ---

/**
 * システム設定を取得する
 */
export async function getSettings(): Promise<SystemSettingsResponse> {
  const response = await apiClient.get<SystemSettingsResponse>('/settings')
  return response.data
}

/**
 * システム設定を更新する
 * @param data 更新データ
 */
export async function updateSettings(
  data: SystemSettingsUpdateData,
): Promise<SystemSettingsResponse> {
  const response = await apiClient.put<SystemSettingsResponse>('/settings', data)
  return response.data
}

export default apiClient
