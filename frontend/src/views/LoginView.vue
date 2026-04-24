<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import axios from 'axios'

const router = useRouter()
const auth = useAuthStore()

// フォーム入力値
const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMessage = ref('')
const showPassword = ref(false)

// フォームバリデーションルール
const rules = {
  required: (v: string) => !!v || 'このフィールドは必須です',
}

/**
 * ログインボタン押下時の処理
 * 認証成功後: admin → /users、user → /tasks へ遷移
 */
async function handleLogin(): Promise<void> {
  if (!username.value || !password.value) {
    errorMessage.value = 'ユーザー名とパスワードを入力してください。'
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    await auth.login(username.value, password.value)
    // ロールに応じてリダイレクト先を分岐
    if (auth.isAdmin) {
      await router.push('/users')
    } else {
      await router.push('/tasks')
    }
  } catch (error: unknown) {
    // 認証エラーメッセージを表示
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      errorMessage.value = 'ユーザー名またはパスワードが正しくありません。'
    } else {
      errorMessage.value = 'ログインに失敗しました。しばらく経ってから再試行してください。'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <!-- SC-01: ログイン画面 -->
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" sm="8" md="4">
        <v-card elevation="4" rounded="lg">
          <v-card-title class="text-h5 pa-6 pb-2 text-center">
            <v-icon size="32" color="primary" class="mr-2">mdi-robot</v-icon>
            CodingAgentAutomata
          </v-card-title>
          <v-card-subtitle class="text-center pb-4">管理画面ログイン</v-card-subtitle>

          <v-card-text>
            <!-- エラーアラート -->
            <v-alert
              v-if="errorMessage"
              type="error"
              variant="tonal"
              class="mb-4"
              closable
              data-testid="error-message"
              @click:close="errorMessage = ''"
            >
              {{ errorMessage }}
            </v-alert>

            <v-form @submit.prevent="handleLogin">
              <!-- ユーザー名入力 -->
              <v-text-field
                v-model="username"
                label="ユーザー名"
                prepend-inner-icon="mdi-account"
                variant="outlined"
                :rules="[rules.required]"
                class="mb-3"
                autocomplete="username"
                :input-attrs="{ 'data-testid': 'username' }"
              />

              <!-- パスワード入力 -->
              <v-text-field
                v-model="password"
                label="パスワード"
                prepend-inner-icon="mdi-lock"
                :type="showPassword ? 'text' : 'password'"
                :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
                variant="outlined"
                :rules="[rules.required]"
                class="mb-4"
                autocomplete="current-password"
                @click:append-inner="showPassword = !showPassword"
                :input-attrs="{ 'data-testid': 'password' }"
              />

              <!-- ログインボタン -->
              <v-btn
                type="submit"
                color="primary"
                size="large"
                block
                :loading="loading"
                data-testid="login-button"
              >
                ログイン
              </v-btn>
            </v-form>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>
