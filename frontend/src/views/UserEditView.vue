<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getUser,
  updateUser,
  updateUserSelf,
  getAdapters,
  type UserResponse,
  type CLIAdapterResponse,
} from '../api/client'
import { useAuthStore } from '../stores/auth'
import axios from 'axios'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// 対象ユーザー名
const username = route.params.username as string

// admin が編集しているかどうか
const isAdminEdit = computed(() => auth.isAdmin)
// 自分自身を編集しているかどうか
const isSelfEdit = computed(() => auth.currentUsername === username)

// CLIアダプタ一覧
const adapters = ref<CLIAdapterResponse[]>([])

// フォーム入力値
const email = ref('')
const password = ref('')
const currentPassword = ref('')
const confirmPassword = ref('')
const virtualKey = ref('')
const defaultCli = ref('')
const defaultModel = ref('')
const role = ref('user')
const isActive = ref(true)
const systemMcpEnabled = ref(false)
const userMcpConfig = ref('')
const f4PromptTemplate = ref('')

// F-4テンプレートクリア確認ダイアログ
const clearF4Dialog = ref(false)

// 状態管理
const loading = ref(false)
const formRef = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const errorMessage = ref('')
const successMessage = ref('')
const showPassword = ref(false)
const showConfirmPassword = ref(false)

// ロール選択肢
const roleOptions = [
  { title: '一般ユーザー', value: 'user' },
  { title: '管理者', value: 'admin' },
]

// バリデーションルール
const rules = {
  email: (v: string) => !v || /.+@.+\..+/.test(v) || '有効なメールアドレスを入力してください',
  passwordStrength: (v: string) => !v || v.length >= 8 || 'パスワードは8文字以上で入力してください',
  confirmPassword: (v: string) =>
    !password.value || v === password.value || 'パスワードが一致しません',
}

/**
 * ユーザー情報を取得してフォームに設定する
 */
async function fetchUser(): Promise<void> {
  loading.value = true
  try {
    const user: UserResponse = await getUser(username)
    email.value = user.email
    defaultCli.value = user.default_cli
    defaultModel.value = user.default_model
    role.value = user.role
    isActive.value = user.is_active
    systemMcpEnabled.value = user.system_mcp_enabled
    userMcpConfig.value = user.user_mcp_config
      ? JSON.stringify(user.user_mcp_config, null, 2)
      : ''
    f4PromptTemplate.value = user.f4_prompt_template ?? ''
  } catch {
    errorMessage.value = 'ユーザー情報の取得に失敗しました。'
  } finally {
    loading.value = false
  }
}

/**
 * CLIアダプタ一覧を取得する
 */
async function fetchAdapters(): Promise<void> {
  try {
    adapters.value = await getAdapters()
  } catch {
    // アダプタ取得失敗は致命的エラーではない
  }
}

/**
 * 保存処理
 * admin は PUT /users/{username} を、一般ユーザーは PUT /users/{username}/me を呼ぶ
 */
async function handleSave(): Promise<void> {
  if (!formRef.value) return
  const { valid } = await formRef.value.validate()
  if (!valid) return

  loading.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    // MCP設定のJSON検証
    let parsedMcpConfig: unknown = null
    if (userMcpConfig.value.trim()) {
      try {
        parsedMcpConfig = JSON.parse(userMcpConfig.value)
      } catch {
        errorMessage.value = 'ユーザー個別MCP設定のJSON形式が不正です。'
        loading.value = false
        return
      }
    }

    if (isAdminEdit.value) {
      // admin 用更新API（全項目変更可）
      await updateUser(username, {
        email: email.value || undefined,
        virtual_key: virtualKey.value || undefined,
        default_cli: defaultCli.value || undefined,
        default_model: defaultModel.value || undefined,
        role: role.value,
        is_active: isActive.value,
        system_mcp_enabled: systemMcpEnabled.value,
        user_mcp_config: parsedMcpConfig,
        f4_prompt_template: f4PromptTemplate.value || null,
      })
    } else {
      // 一般ユーザー自身用更新API（制限項目のみ）
      await updateUserSelf(username, {
        email: email.value || undefined,
        password: password.value || undefined,
        current_password: currentPassword.value || undefined,
        default_cli: defaultCli.value || undefined,
        default_model: defaultModel.value || undefined,
        system_mcp_enabled: systemMcpEnabled.value,
        user_mcp_config: parsedMcpConfig,
        f4_prompt_template: f4PromptTemplate.value || null,
      })
    }

    successMessage.value = '保存しました。'
    // 保存成功後はユーザー詳細画面へ遷移
    await router.push(`/users/${username}`)
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 403) {
      errorMessage.value = '更新権限がありません。'
    } else if (axios.isAxiosError(error) && error.response?.status === 400) {
      errorMessage.value = '入力内容に誤りがあります。現在のパスワードを確認してください。'
    } else {
      errorMessage.value = '保存に失敗しました。'
    }
  } finally {
    loading.value = false
  }
}

/**
 * F-4テンプレートをクリアする
 */
function clearF4Template(): void {
  f4PromptTemplate.value = ''
  clearF4Dialog.value = false
}

// コンポーネントマウント時にデータ取得
onMounted(async () => {
  await Promise.all([fetchUser(), isAdminEdit.value ? fetchAdapters() : Promise.resolve()])
})
</script>

<template>
  <!-- SC-05: ユーザー編集画面 -->
  <v-container class="pa-6" max-width="800">
    <!-- ページヘッダー -->
    <v-row class="mb-4" align="center">
      <v-col>
        <v-btn variant="text" prepend-icon="mdi-arrow-left" :to="`/users/${username}`">
          戻る
        </v-btn>
        <h1 class="text-h5 mt-2">
          <v-icon class="mr-2">mdi-account-edit</v-icon>
          ユーザー編集: {{ username }}
        </h1>
      </v-col>
    </v-row>

    <!-- エラーアラート -->
    <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-4" closable>
      {{ errorMessage }}
    </v-alert>

    <!-- 成功アラート -->
    <v-alert v-if="successMessage" type="success" variant="tonal" class="mb-4">
      {{ successMessage }}
    </v-alert>

    <v-card variant="outlined">
      <v-card-text class="pa-6">
        <v-form ref="formRef" @submit.prevent="handleSave">
          <v-row>
            <!-- メールアドレス -->
            <v-col cols="12" md="6">
              <v-text-field
                v-model="email"
                label="メールアドレス"
                variant="outlined"
                :rules="[rules.email]"
                prepend-inner-icon="mdi-email"
                type="email"
              />
            </v-col>

            <!-- パスワード（一般ユーザー自身のみ表示） -->
            <template v-if="!isAdminEdit && isSelfEdit">
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="currentPassword"
                  label="現在のパスワード"
                  variant="outlined"
                  :type="showPassword ? 'text' : 'password'"
                  :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
                  prepend-inner-icon="mdi-lock"
                  hint="パスワード変更時に入力してください"
                  persistent-hint
                  @click:append-inner="showPassword = !showPassword"
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="password"
                  label="新しいパスワード"
                  variant="outlined"
                  :type="showConfirmPassword ? 'text' : 'password'"
                  :append-inner-icon="showConfirmPassword ? 'mdi-eye-off' : 'mdi-eye'"
                  :rules="[rules.passwordStrength]"
                  prepend-inner-icon="mdi-lock-reset"
                  hint="8文字以上で入力してください"
                  persistent-hint
                  @click:append-inner="showConfirmPassword = !showConfirmPassword"
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="confirmPassword"
                  label="新しいパスワード確認"
                  variant="outlined"
                  :type="showConfirmPassword ? 'text' : 'password'"
                  :rules="[rules.confirmPassword]"
                  prepend-inner-icon="mdi-lock-check"
                  @click:append-inner="showConfirmPassword = !showConfirmPassword"
                />
              </v-col>
            </template>

            <!-- Virtual Key（admin のみ表示） -->
            <v-col v-if="isAdminEdit" cols="12">
              <v-text-field
                v-model="virtualKey"
                label="Virtual Key（変更する場合のみ入力）"
                variant="outlined"
                prepend-inner-icon="mdi-key"
                hint="空のままにすると変更されません"
                persistent-hint
              />
            </v-col>

            <!-- デフォルト CLI -->
            <v-col cols="12" md="6">
              <v-select
                v-if="adapters.length > 0"
                v-model="defaultCli"
                label="デフォルト CLI"
                variant="outlined"
                :items="adapters.map(a => ({ title: a.cli_id, value: a.cli_id }))"
                prepend-inner-icon="mdi-console"
              />
              <v-text-field
                v-else
                v-model="defaultCli"
                label="デフォルト CLI"
                variant="outlined"
                prepend-inner-icon="mdi-console"
              />
            </v-col>

            <!-- デフォルトモデル -->
            <v-col cols="12" md="6">
              <v-text-field
                v-model="defaultModel"
                label="デフォルトモデル"
                variant="outlined"
                prepend-inner-icon="mdi-brain"
                hint="例: claude-3-5-sonnet-20241022"
                persistent-hint
              />
            </v-col>

            <!-- ロール（admin のみ表示） -->
            <v-col v-if="isAdminEdit" cols="12" md="6">
              <v-select
                v-model="role"
                label="ロール"
                variant="outlined"
                :items="roleOptions"
                prepend-inner-icon="mdi-shield-account"
              />
            </v-col>

            <!-- ステータス（admin のみ表示） -->
            <v-col v-if="isAdminEdit" cols="12" md="6">
              <v-switch
                v-model="isActive"
                label="アカウント有効"
                color="success"
                inset
              />
            </v-col>

            <!-- システム MCP 設定 -->
            <v-col cols="12" md="6">
              <v-switch
                v-model="systemMcpEnabled"
                label="システム MCP 設定を使用する"
                color="primary"
                inset
              />
            </v-col>

            <!-- ユーザー個別 MCP 設定（JSON） -->
            <v-col cols="12">
              <v-textarea
                v-model="userMcpConfig"
                label="ユーザー個別 MCP 設定（JSON）"
                variant="outlined"
                rows="6"
                prepend-inner-icon="mdi-code-json"
                hint="JSON形式で入力してください。空白の場合は設定なしとなります"
                persistent-hint
                font-family="monospace"
              />
            </v-col>

            <!-- F-4プロンプトテンプレート -->
            <v-col cols="12">
              <v-row align="center" class="mb-1">
                <v-col>
                  <span class="text-subtitle-2">F-4 プロンプトテンプレート（ユーザー個別）</span>
                </v-col>
                <v-col cols="auto">
                  <!-- クリアボタン（確認ダイアログ付き） -->
                  <v-btn
                    size="small"
                    color="error"
                    variant="tonal"
                    prepend-icon="mdi-delete"
                    @click="clearF4Dialog = true"
                  >
                    クリア
                  </v-btn>
                </v-col>
              </v-row>
              <!-- 使用可能な変数のヘルプテキスト -->
              <v-alert type="info" variant="tonal" density="compact" class="mb-2">
                <strong>使用可能な変数:</strong>
                <code>{mr_description}</code>（MRの説明）、
                <code>{mr_comments}</code>（MRのコメント一覧）、
                <code>{branch_name}</code>（ブランチ名）、
                <code>{repository_url}</code>（リポジトリURL）
              </v-alert>
              <v-textarea
                v-model="f4PromptTemplate"
                variant="outlined"
                rows="8"
                placeholder="空白の場合はシステムデフォルトのテンプレートが使用されます"
                font-family="monospace"
              />
            </v-col>
          </v-row>

          <!-- アクションボタン -->
          <v-row class="mt-4">
            <v-col>
              <v-btn
                type="submit"
                color="primary"
                size="large"
                :loading="loading"
              >
                保存する
              </v-btn>
              <v-btn
                variant="text"
                class="ml-2"
                :to="`/users/${username}`"
              >
                キャンセル
              </v-btn>
            </v-col>
          </v-row>
        </v-form>
      </v-card-text>
    </v-card>

    <!-- F-4テンプレートクリア確認ダイアログ -->
    <v-dialog v-model="clearF4Dialog" max-width="400">
      <v-card>
        <v-card-title class="text-h6">テンプレートのクリア確認</v-card-title>
        <v-card-text>
          F-4プロンプトテンプレートをクリアしますか？クリア後はシステムデフォルトが使用されます。
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="clearF4Dialog = false">キャンセル</v-btn>
          <v-btn color="error" variant="tonal" @click="clearF4Template">クリアする</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
