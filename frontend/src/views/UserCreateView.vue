<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { createUser, getAdapters, type CLIAdapterResponse } from '../api/client'
import axios from 'axios'

const router = useRouter()

// CLIアダプタ一覧
const adapters = ref<CLIAdapterResponse[]>([])

// フォーム入力値
const username = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const virtualKey = ref('')
const defaultCli = ref('')
const defaultModel = ref('')
const role = ref('user')
const showPassword = ref(false)
const showConfirmPassword = ref(false)

// 状態管理
const loading = ref(false)
const formRef = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
const errorMessage = ref('')

// ロール選択肢
const roleOptions = [
  { title: '一般ユーザー', value: 'user' },
  { title: '管理者', value: 'admin' },
]

// バリデーションルール
const rules = {
  required: (v: string) => !!v || 'このフィールドは必須です',
  email: (v: string) => /.+@.+\..+/.test(v) || '有効なメールアドレスを入力してください',
  passwordStrength: (v: string) =>
    v.length >= 8 || 'パスワードは8文字以上で入力してください',
  confirmPassword: (v: string) => v === password.value || 'パスワードが一致しません',
}

/**
 * CLIアダプタ一覧を取得する
 */
async function fetchAdapters(): Promise<void> {
  try {
    adapters.value = await getAdapters()
    if (adapters.value.length > 0) {
      defaultCli.value = adapters.value[0].cli_id
    }
  } catch {
    // アダプタ取得失敗は致命的エラーではない
  }
}

/**
 * ユーザー作成処理
 */
async function handleCreate(): Promise<void> {
  if (!formRef.value) return
  const { valid } = await formRef.value.validate()
  if (!valid) return

  loading.value = true
  errorMessage.value = ''

  try {
    await createUser({
      username: username.value,
      email: email.value,
      password: password.value,
      virtual_key: virtualKey.value,
      default_cli: defaultCli.value,
      default_model: defaultModel.value,
      role: role.value,
    })
    // 作成成功後はユーザー一覧へ遷移
    await router.push('/users')
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 409) {
      errorMessage.value = 'このユーザー名は既に使用されています。'
    } else if (axios.isAxiosError(error) && error.response?.data) {
      errorMessage.value = 'ユーザーの作成に失敗しました。入力内容を確認してください。'
    } else {
      errorMessage.value = 'ユーザーの作成に失敗しました。'
    }
  } finally {
    loading.value = false
  }
}

// コンポーネントマウント時にアダプタ一覧を取得
onMounted(() => {
  void fetchAdapters()
})
</script>

<template>
  <!-- SC-04: ユーザー作成画面（admin のみ） -->
  <v-container class="pa-6" max-width="700">
    <!-- ページヘッダー -->
    <v-row class="mb-4" align="center">
      <v-col>
        <v-btn variant="text" prepend-icon="mdi-arrow-left" to="/users">戻る</v-btn>
        <h1 class="text-h5 mt-2">
          <v-icon class="mr-2">mdi-account-plus</v-icon>
          ユーザー作成
        </h1>
      </v-col>
    </v-row>

    <!-- エラーアラート -->
    <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-4" closable>
      {{ errorMessage }}
    </v-alert>

    <v-card variant="outlined">
      <v-card-text class="pa-6">
        <v-form ref="formRef" @submit.prevent="handleCreate">
          <v-row>
            <!-- ユーザー名 -->
            <v-col cols="12" md="6">
              <v-text-field
                v-model="username"
                label="ユーザー名 *"
                variant="outlined"
                :rules="[rules.required]"
                prepend-inner-icon="mdi-account"
              />
            </v-col>

            <!-- メールアドレス -->
            <v-col cols="12" md="6">
              <v-text-field
                v-model="email"
                label="メールアドレス *"
                variant="outlined"
                :rules="[rules.required, rules.email]"
                prepend-inner-icon="mdi-email"
                type="email"
              />
            </v-col>

            <!-- パスワード -->
            <v-col cols="12" md="6">
              <v-text-field
                v-model="password"
                label="パスワード *"
                variant="outlined"
                :type="showPassword ? 'text' : 'password'"
                :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
                :rules="[rules.required, rules.passwordStrength]"
                prepend-inner-icon="mdi-lock"
                @click:append-inner="showPassword = !showPassword"
              />
            </v-col>

            <!-- パスワード確認 -->
            <v-col cols="12" md="6">
              <v-text-field
                v-model="confirmPassword"
                label="パスワード確認 *"
                variant="outlined"
                :type="showConfirmPassword ? 'text' : 'password'"
                :append-inner-icon="showConfirmPassword ? 'mdi-eye-off' : 'mdi-eye'"
                :rules="[rules.required, rules.confirmPassword]"
                prepend-inner-icon="mdi-lock-check"
                @click:append-inner="showConfirmPassword = !showConfirmPassword"
              />
            </v-col>

            <!-- Virtual Key -->
            <v-col cols="12">
              <v-text-field
                v-model="virtualKey"
                label="Virtual Key *"
                variant="outlined"
                :rules="[rules.required]"
                prepend-inner-icon="mdi-key"
                hint="LiteLLM Proxy の Virtual Key を入力してください"
                persistent-hint
              />
            </v-col>

            <!-- デフォルト CLI -->
            <v-col cols="12" md="6">
              <v-select
                v-model="defaultCli"
                label="デフォルト CLI *"
                variant="outlined"
                :items="adapters.map(a => ({ title: a.cli_id, value: a.cli_id }))"
                :rules="[rules.required]"
                prepend-inner-icon="mdi-console"
              />
            </v-col>

            <!-- デフォルトモデル -->
            <v-col cols="12" md="6">
              <v-text-field
                v-model="defaultModel"
                label="デフォルトモデル *"
                variant="outlined"
                :rules="[rules.required]"
                prepend-inner-icon="mdi-brain"
                hint="例: claude-3-5-sonnet-20241022"
                persistent-hint
              />
            </v-col>

            <!-- ロール -->
            <v-col cols="12" md="6">
              <v-select
                v-model="role"
                label="ロール *"
                variant="outlined"
                :items="roleOptions"
                prepend-inner-icon="mdi-shield-account"
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
                作成する
              </v-btn>
              <v-btn
                variant="text"
                class="ml-2"
                to="/users"
              >
                キャンセル
              </v-btn>
            </v-col>
          </v-row>
        </v-form>
      </v-card-text>
    </v-card>
  </v-container>
</template>
