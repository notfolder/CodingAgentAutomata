<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getUser, deleteUser, type UserResponse } from '../api/client'
import { useAuthStore } from '../stores/auth'
import axios from 'axios'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// 対象ユーザー名
const username = route.params.username as string

// 状態管理
const user = ref<UserResponse | null>(null)
const loading = ref(false)
const errorMessage = ref('')
const deleteDialog = ref(false)
const deleteLoading = ref(false)

/**
 * ユーザー情報を取得する
 */
async function fetchUser(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    user.value = await getUser(username)
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      errorMessage.value = 'ユーザーが見つかりません。'
    } else {
      errorMessage.value = 'ユーザー情報の取得に失敗しました。'
    }
  } finally {
    loading.value = false
  }
}

/**
 * ユーザーを削除する
 */
async function handleDelete(): Promise<void> {
  deleteLoading.value = true
  try {
    await deleteUser(username)
    deleteDialog.value = false
    await router.push('/users')
  } catch {
    errorMessage.value = 'ユーザーの削除に失敗しました。'
    deleteDialog.value = false
  } finally {
    deleteLoading.value = false
  }
}

/**
 * 日時文字列をフォーマットする
 */
function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('ja-JP')
}

/**
 * Virtual Key のマスク表示（末尾4文字のみ）
 */
function maskedKey(masked: string | null): string {
  if (!masked) return '未設定'
  return `****${masked}`
}

// コンポーネントマウント時にユーザー情報を取得
onMounted(() => {
  void fetchUser()
})
</script>

<template>
  <!-- SC-03: ユーザー詳細画面 -->
  <v-container class="pa-6" max-width="800">
    <!-- ページヘッダー -->
    <v-row class="mb-4" align="center">
      <v-col>
        <v-btn
          variant="text"
          prepend-icon="mdi-arrow-left"
          @click="router.back()"
        >
          戻る
        </v-btn>
        <h1 class="text-h5 mt-2">
          <v-icon class="mr-2">mdi-account</v-icon>
          ユーザー詳細
        </h1>
      </v-col>
    </v-row>

    <!-- エラーアラート -->
    <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-4">
      {{ errorMessage }}
    </v-alert>

    <!-- ローディング -->
    <v-progress-circular v-if="loading" indeterminate color="primary" class="d-block mx-auto" />

    <!-- ユーザー情報カード -->
    <v-card v-if="user" variant="outlined">
      <v-card-title class="pa-6">
        <v-avatar color="primary" size="48" class="mr-3">
          <v-icon>mdi-account</v-icon>
        </v-avatar>
        {{ user.username }}
        <v-chip
          :color="user.role === 'admin' ? 'error' : 'primary'"
          size="small"
          variant="tonal"
          class="ml-2"
        >
          {{ user.role === 'admin' ? '管理者' : '一般ユーザー' }}
        </v-chip>
        <v-chip
          :color="user.is_active ? 'success' : 'default'"
          size="small"
          variant="tonal"
          class="ml-2"
        >
          {{ user.is_active ? '有効' : '無効' }}
        </v-chip>
      </v-card-title>

      <v-divider />

      <v-card-text>
        <v-list>
          <v-list-item>
            <template #prepend><v-icon>mdi-email</v-icon></template>
            <v-list-item-title>メールアドレス</v-list-item-title>
            <v-list-item-subtitle>{{ user.email }}</v-list-item-subtitle>
          </v-list-item>

          <v-list-item>
            <template #prepend><v-icon>mdi-key</v-icon></template>
            <v-list-item-title>Virtual Key</v-list-item-title>
            <!-- Virtual Key は末尾4文字のみ表示 -->
            <v-list-item-subtitle>{{ maskedKey(user.virtual_key_masked) }}</v-list-item-subtitle>
          </v-list-item>

          <v-list-item>
            <template #prepend><v-icon>mdi-console</v-icon></template>
            <v-list-item-title>デフォルト CLI</v-list-item-title>
            <v-list-item-subtitle>{{ user.default_cli || '未設定' }}</v-list-item-subtitle>
          </v-list-item>

          <v-list-item>
            <template #prepend><v-icon>mdi-brain</v-icon></template>
            <v-list-item-title>デフォルトモデル</v-list-item-title>
            <v-list-item-subtitle>{{ user.default_model || '未設定' }}</v-list-item-subtitle>
          </v-list-item>

          <v-list-item>
            <template #prepend><v-icon>mdi-server</v-icon></template>
            <v-list-item-title>システム MCP 設定</v-list-item-title>
            <v-list-item-subtitle>{{ user.system_mcp_enabled ? '有効' : '無効' }}</v-list-item-subtitle>
          </v-list-item>

          <v-list-item>
            <template #prepend><v-icon>mdi-calendar</v-icon></template>
            <v-list-item-title>登録日時</v-list-item-title>
            <v-list-item-subtitle>{{ formatDate(user.created_at) }}</v-list-item-subtitle>
          </v-list-item>

          <v-list-item>
            <template #prepend><v-icon>mdi-calendar-edit</v-icon></template>
            <v-list-item-title>最終更新日時</v-list-item-title>
            <v-list-item-subtitle>{{ formatDate(user.updated_at) }}</v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-card-text>

      <v-divider />

      <!-- アクションボタン -->
      <v-card-actions class="pa-4">
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-pencil"
          :to="`/users/${username}/edit`"
        >
          編集
        </v-btn>
        <!-- 削除ボタン（admin のみ表示） -->
        <v-btn
          v-if="auth.isAdmin"
          color="error"
          variant="tonal"
          prepend-icon="mdi-delete"
          class="ml-2"
          @click="deleteDialog = true"
        >
          削除
        </v-btn>
      </v-card-actions>
    </v-card>

    <!-- 削除確認ダイアログ -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="text-h6">ユーザー削除の確認</v-card-title>
        <v-card-text>
          ユーザー「{{ username }}」を削除しますか？この操作は取り消せません。
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">キャンセル</v-btn>
          <v-btn
            color="error"
            variant="tonal"
            :loading="deleteLoading"
            @click="handleDelete"
          >
            削除する
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
