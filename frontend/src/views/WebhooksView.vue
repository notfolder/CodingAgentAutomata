<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  getGroupsWithWebhookStatus,
  registerWebhook,
  deleteWebhook,
  type GroupWithWebhookStatus,
} from '../api/client'
import axios from 'axios'

// ローディング状態
const loading = ref(false)
// エラーメッセージ
const errorMessage = ref('')
// スナックバー表示
const snackbar = ref(false)
const snackbarMessage = ref('')
const snackbarColor = ref<'success' | 'error'>('success')

// グループ一覧
const groups = ref<GroupWithWebhookStatus[]>([])

// テキスト検索文字列
const searchText = ref('')

// 絞り込み後のグループ一覧
const filteredGroups = computed(() => {
  const q = searchText.value.trim().toLowerCase()
  if (!q) return groups.value
  return groups.value.filter(
    (g) =>
      g.group_name.toLowerCase().includes(q) || g.group_path.toLowerCase().includes(q),
  )
})

// ダイアログ制御
const registerDialog = ref(false)
const deleteDialog = ref(false)
const selectedGroup = ref<GroupWithWebhookStatus | null>(null)

// 操作中フラグ
const actionLoading = ref(false)

// テーブルヘッダー
const headers = [
  { title: 'グループ名', key: 'group_name', sortable: true },
  { title: '状態', key: 'is_registered', sortable: true },
  { title: '操作', key: 'actions', sortable: false },
]

/**
 * グループ一覧とWebhook状況を取得する
 */
async function fetchGroups(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    groups.value = await getGroupsWithWebhookStatus()
  } catch (err: unknown) {
    if (axios.isAxiosError(err)) {
      errorMessage.value =
        err.response?.data?.detail ?? 'グループ一覧の取得に失敗しました。'
    } else {
      errorMessage.value = 'グループ一覧の取得に失敗しました。'
    }
  } finally {
    loading.value = false
  }
}

/**
 * 登録確認ダイアログを開く
 */
function openRegisterDialog(group: GroupWithWebhookStatus): void {
  selectedGroup.value = group
  registerDialog.value = true
}

/**
 * 削除確認ダイアログを開く
 */
function openDeleteDialog(group: GroupWithWebhookStatus): void {
  selectedGroup.value = group
  deleteDialog.value = true
}

/**
 * Webhook を登録する
 */
async function handleRegister(): Promise<void> {
  if (!selectedGroup.value) return
  actionLoading.value = true
  try {
    await registerWebhook(selectedGroup.value.group_id)
    registerDialog.value = false
    snackbarMessage.value = `グループ「${selectedGroup.value.group_name}」にWebhookを登録しました。`
    snackbarColor.value = 'success'
    snackbar.value = true
    await fetchGroups()
  } catch (err: unknown) {
    let detail = 'Webhook登録に失敗しました。'
    if (axios.isAxiosError(err)) {
      detail = err.response?.data?.detail ?? detail
    }
    snackbarMessage.value = detail
    snackbarColor.value = 'error'
    snackbar.value = true
    registerDialog.value = false
  } finally {
    actionLoading.value = false
  }
}

/**
 * Webhook を削除する
 */
async function handleDelete(): Promise<void> {
  if (!selectedGroup.value || selectedGroup.value.webhook_id === null) return
  actionLoading.value = true
  try {
    await deleteWebhook(selectedGroup.value.group_id, selectedGroup.value.webhook_id)
    deleteDialog.value = false
    snackbarMessage.value = `グループ「${selectedGroup.value.group_name}」のWebhookを削除しました。`
    snackbarColor.value = 'success'
    snackbar.value = true
    await fetchGroups()
  } catch (err: unknown) {
    let detail = 'Webhook削除に失敗しました。'
    if (axios.isAxiosError(err)) {
      detail = err.response?.data?.detail ?? detail
    }
    snackbarMessage.value = detail
    snackbarColor.value = 'error'
    snackbar.value = true
    deleteDialog.value = false
  } finally {
    actionLoading.value = false
  }
}

// コンポーネントマウント時にデータ取得
onMounted(async () => {
  await fetchGroups()
})
</script>

<template>
  <!-- SC-08: Group Webhook管理画面 -->
  <v-container fluid class="pa-6">
    <!-- ページヘッダー -->
    <v-row class="mb-4" align="center">
      <v-col>
        <h1 class="text-h5">
          <v-icon class="mr-2">mdi-webhook</v-icon>
          Group Webhook管理
        </h1>
      </v-col>
      <v-col cols="auto">
        <v-btn
          variant="text"
          prepend-icon="mdi-refresh"
          :loading="loading"
          @click="fetchGroups"
        >
          更新
        </v-btn>
      </v-col>
    </v-row>

    <!-- エラーアラート -->
    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      class="mb-4"
      closable
      @click:close="errorMessage = ''"
    >
      {{ errorMessage }}
    </v-alert>

    <!-- テキスト検索フィールド -->
    <v-text-field
      v-model="searchText"
      prepend-inner-icon="mdi-magnify"
      label="グループ名で検索"
      variant="outlined"
      clearable
      density="compact"
      class="mb-4"
      style="max-width: 400px"
    />

    <!-- グループ一覧テーブル -->
    <v-card variant="outlined">
      <v-data-table
        :headers="headers"
        :items="filteredGroups"
        :loading="loading"
        loading-text="グループ一覧を読み込み中..."
        no-data-text="表示するグループがありません"
        item-value="group_id"
      >
        <!-- 状態バッジ -->
        <template #item.is_registered="{ item }">
          <v-chip
            v-if="item.is_registered"
            color="success"
            size="small"
            variant="tonal"
          >
            登録済み
          </v-chip>
          <v-chip
            v-else
            color="default"
            size="small"
            variant="tonal"
          >
            未登録
          </v-chip>
        </template>

        <!-- 操作ボタン -->
        <template #item.actions="{ item }">
          <!-- 登録ボタン（未登録グループ） -->
          <v-btn
            v-if="!item.is_registered"
            size="small"
            color="primary"
            variant="tonal"
            @click="openRegisterDialog(item)"
          >
            登録
          </v-btn>
          <!-- 削除ボタン（登録済みグループ） -->
          <v-btn
            v-else
            size="small"
            color="error"
            variant="tonal"
            @click="openDeleteDialog(item)"
          >
            削除
          </v-btn>
        </template>
      </v-data-table>
    </v-card>

    <!-- 登録確認ダイアログ -->
    <v-dialog v-model="registerDialog" max-width="480" persistent>
      <v-card v-if="selectedGroup">
        <v-card-title class="text-h6 pa-6">Webhook 登録の確認</v-card-title>
        <v-divider />
        <v-card-text class="pa-6">
          <p class="mb-2">以下のグループに Webhook を登録します</p>
          <v-list density="compact">
            <v-list-item>
              <template #prepend>
                <strong>グループ:</strong>
              </template>
              <v-list-item-title class="ml-2">{{ selectedGroup.group_name }}</v-list-item-title>
            </v-list-item>
          </v-list>
          <p class="text-caption text-medium-emphasis mt-2">
            ※ Webhook受信URLは登録時にシステム設定から自動取得されます。
          </p>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" :disabled="actionLoading" @click="registerDialog = false">
            キャンセル
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="actionLoading"
            @click="handleRegister"
          >
            登録する
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 削除確認ダイアログ -->
    <v-dialog v-model="deleteDialog" max-width="480" persistent>
      <v-card v-if="selectedGroup">
        <v-card-title class="text-h6 pa-6">Webhook 削除の確認</v-card-title>
        <v-divider />
        <v-card-text class="pa-6">
          <p class="mb-2">以下の Webhook を削除します</p>
          <v-list density="compact">
            <v-list-item>
              <template #prepend>
                <strong>グループ:</strong>
              </template>
              <v-list-item-title class="ml-2">{{ selectedGroup.group_name }}</v-list-item-title>
            </v-list-item>
            <v-list-item v-if="selectedGroup.webhook_url">
              <template #prepend>
                <strong>Webhook URL:</strong>
              </template>
              <v-list-item-title class="ml-2">{{ selectedGroup.webhook_url }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" :disabled="actionLoading" @click="deleteDialog = false">
            キャンセル
          </v-btn>
          <v-btn
            color="error"
            variant="tonal"
            :loading="actionLoading"
            @click="handleDelete"
          >
            削除する
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- スナックバー（操作結果通知） -->
    <v-snackbar v-model="snackbar" :color="snackbarColor" timeout="4000">
      {{ snackbarMessage }}
    </v-snackbar>
  </v-container>
</template>
